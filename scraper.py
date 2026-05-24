"""
Scrapes NBA 2K player ratings from 2kratings.com and upserts into ratingscheck.db.

All 10 attributes live as data-* attributes on each <tr> in table#lists-table.
The table is JavaScript-rendered, so we use undetected_chromedriver (real Chrome)
to wait for it to populate — same pattern as StatCheck's build_nfl_pfr.py.

Usage:
    python scraper.py                           # scrape all teams, write to DB
    python scraper.py --dry-run                 # print without writing to DB
    python scraper.py --team dallas-mavericks   # scrape one team only
    python scraper.py --dump-html atlanta-hawks # save rendered HTML to dump_<slug>.html
"""

import logging
import re
import sys
import time
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from models import init_db, upsert_player

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BASE_URL = "https://www.2kratings.com"

NBA_TEAM_SLUGS = [
    "atlanta-hawks", "boston-celtics", "brooklyn-nets", "charlotte-hornets",
    "chicago-bulls", "cleveland-cavaliers", "dallas-mavericks", "denver-nuggets",
    "detroit-pistons", "golden-state-warriors", "houston-rockets", "indiana-pacers",
    "los-angeles-clippers", "los-angeles-lakers", "memphis-grizzlies", "miami-heat",
    "milwaukee-bucks", "minnesota-timberwolves", "new-orleans-pelicans", "new-york-knicks",
    "oklahoma-city-thunder", "orlando-magic", "philadelphia-76ers", "phoenix-suns",
    "portland-trail-blazers", "sacramento-kings", "san-antonio-spurs", "toronto-raptors",
    "utah-jazz", "washington-wizards",
]

TEAM_ABBR = {
    "atlanta-hawks": "ATL", "boston-celtics": "BOS", "brooklyn-nets": "BKN",
    "charlotte-hornets": "CHA", "chicago-bulls": "CHI", "cleveland-cavaliers": "CLE",
    "dallas-mavericks": "DAL", "denver-nuggets": "DEN", "detroit-pistons": "DET",
    "golden-state-warriors": "GSW", "houston-rockets": "HOU", "indiana-pacers": "IND",
    "los-angeles-clippers": "LAC", "los-angeles-lakers": "LAL", "memphis-grizzlies": "MEM",
    "miami-heat": "MIA", "milwaukee-bucks": "MIL", "minnesota-timberwolves": "MIN",
    "new-orleans-pelicans": "NOP", "new-york-knicks": "NYK", "oklahoma-city-thunder": "OKC",
    "orlando-magic": "ORL", "philadelphia-76ers": "PHI", "phoenix-suns": "PHX",
    "portland-trail-blazers": "POR", "sacramento-kings": "SAC", "san-antonio-spurs": "SAS",
    "toronto-raptors": "TOR", "utah-jazz": "UTA", "washington-wizards": "WAS",
}

# All numerical data-* attrs on each <tbody><tr> in table#lists-table
TR_ATTR_MAP = {
    # Shooting
    "data-close-shot":             "closeShot",
    "data-free-throw":             "freeThrow",
    "data-shot-3pt":               "three",
    "data-mid-range-shot":         "midRange",
    "data-shot-iq":                "shotIQ",
    "data-offensive-consistency":  "offConsistency",
    # Inside scoring
    "data-layup":                  "layup",
    "data-driving-dunk":           "drivingDunk",
    "data-standing-dunk":          "standingDunk",
    "data-post-hook":              "postHook",
    "data-post-fade":              "postFade",
    "data-post-control":           "postControl",
    # Athleticism
    "data-speed":                  "speed",
    "data-agility":                "agility",
    "data-vertical":               "vertical",
    "data-strength":               "strength",
    "data-hustle":                 "hustle",
    "data-stamina":                "stamina",
    "data-draw-foul":              "drawFoul",
    "data-hands":                  "hands",
    # Ball handling
    "data-ball-handle":            "ballHandle",
    "data-speed-with-ball":        "speedWithBall",
    # Passing
    "data-pass-accuracy":          "passAcc",
    "data-pass-vision":            "passVision",
    "data-pass-iq":                "passIQ",
    # Defense
    "data-block":                  "block",
    "data-steal":                  "steal",
    "data-interior-defense":       "interiorD",
    "data-perimeter-defense":      "perimeterD",
    "data-defensive-consistency":  "defConsistency",
    "data-help-defense-iq":        "helpDefIQ",
    "data-pass-perception":        "passPerception",
    # Rebounding
    "data-defensive-rebound":      "defRebound",
    "data-offensive-rebound":      "offRebound",
    # Misc
    "data-overall-durability":     "durability",
    "data-intangibles":            "intangibles",
}

# ── Browser setup (undetected_chromedriver — same approach as build_nfl_pfr.py) ──

_driver = None  # reused across all team pages; closed at end of run


def _get_driver():
    global _driver
    if _driver is not None:
        return _driver
    try:
        import undetected_chromedriver as uc
        log.info("Launching headless Chrome via undetected_chromedriver...")
        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1280,900")
        # Explicit chromedriver path avoids SSL download on systems with cert issues
        import os
        driver_path = os.path.join(os.path.dirname(__file__), "chromedriver.exe")
        if not os.path.exists(driver_path):
            driver_path = None
        _driver = uc.Chrome(options=options, driver_executable_path=driver_path)
        log.info("Chrome ready.")
        return _driver
    except Exception as exc:
        log.error("Failed to launch Chrome: %s", exc)
        log.error("Make sure Chrome is installed and undetected-chromedriver is up to date.")
        return None


def _close_driver():
    global _driver
    if _driver:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None


def fetch(url: str) -> str | None:
    """Fetch a page using real Chrome, waiting for table#lists-table to populate."""
    driver = _get_driver()
    if not driver:
        return None
    try:
        driver.get(url)
        # Wait up to 15s for the JS-rendered table to appear
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        try:
            # Wait for a row that actually has data-* attrs populated (not just empty rows)
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "table#lists-table tbody tr[data-shot-3pt]")
                )
            )
        except Exception:
            log.warning("  Timed out waiting for table#lists-table — grabbing page anyway")
            time.sleep(5)
        return driver.page_source
    except Exception as exc:
        log.error("Chrome fetch error (%s): %s", url, exc)
        return None


_POSITION_TITLE_MAP = {
    "power forward": "PF", "small forward": "SF", "point guard": "PG",
    "shooting guard": "SG", "center": "C",
}


def parse_team_page(html: str, team_slug: str) -> list[dict]:
    """
    Parse the team roster page. All attributes are data-* attrs on each <tr>
    in table#lists-table.
    - Name: <a class="player-name" data-full="..."> inside the player cell
    - Position: first position link (<a title="Power Forward">) in the row
    - Overall: column with data-original-title="Overall"
    """
    soup = BeautifulSoup(html, "html.parser")
    team = TEAM_ABBR.get(team_slug, team_slug[:3].upper())
    players = []

    table = soup.select_one("table#lists-table")
    if not table:
        log.warning("  table#lists-table not found for %s", team_slug)
        return players

    # Find which column index holds the overall rating
    headers = table.select("thead th")
    overall_col_idx = None
    for i, th in enumerate(headers):
        if th.get("data-original-title", "").lower() == "overall" or "overall" in th.get_text(strip=True).lower():
            overall_col_idx = i
            break

    for tr in table.select("tbody tr"):
        try:
            # Read all 10 attributes from data-* on the <tr>
            attrs = {}
            for data_attr, col in TR_ATTR_MAP.items():
                raw = tr.get(data_attr, "")
                try:
                    attrs[col] = int(raw)
                except (ValueError, TypeError):
                    attrs[col] = 0

            tds = tr.select("td")
            if not tds:
                continue

            # Player name: <a class="player-name"> with data-full attr
            name = ""
            player_url = ""
            a_name = tr.select_one("a.player-name")
            if a_name:
                name = a_name.get("data-full") or a_name.get_text(strip=True)
                href = a_name.get("href", "")
                player_url = (BASE_URL + href) if href.startswith("/") else href

            if not name:
                continue

            # Overall rating: OVR cell uses span.attribute-box[data-order] to avoid
            # picking up the diff-minus change indicator (+/-N) in get_text
            overall = 0
            if overall_col_idx is not None and overall_col_idx < len(tds):
                span = tds[overall_col_idx].select_one("span.attribute-box[data-order]")
                if span:
                    try:
                        overall = int(float(span.get("data-order", "0")))
                    except (ValueError, TypeError):
                        pass
                if not overall:
                    try:
                        overall = int(tds[overall_col_idx].select_one("span.attribute-box").get_text(strip=True))
                    except Exception:
                        pass
            if not overall:
                for td in tds:
                    span = td.select_one("span.attribute-box[data-order]")
                    if span:
                        try:
                            val = int(float(span.get("data-order", "0")))
                            if 60 <= val <= 99:
                                overall = val
                                break
                        except (ValueError, TypeError):
                            pass

            # Position: first link whose title maps to a position abbreviation
            position = ""
            for a in tr.select("a[title]"):
                pos = _POSITION_TITLE_MAP.get(a.get("title", "").lower())
                if pos:
                    position = pos
                    break

            players.append({
                "name": name,
                "team": team,
                "position": position,
                "overall": overall,
                "attrs": attrs,
            })

        except Exception as exc:
            log.warning("  Row parse error on %s: %s", team_slug, exc)

    return players


def scrape_team(team_slug: str, dry_run: bool = False) -> dict:
    url = f"{BASE_URL}/teams/{team_slug}"
    log.info("Fetching %s", url)
    html = fetch(url)
    if not html:
        return {"inserted": 0, "updated": 0, "errors": 1}

    players = parse_team_page(html, team_slug)
    log.info("  Parsed %d players", len(players))

    inserted = updated = errors = 0
    for p in players:
        if dry_run:
            log.info("  DRY RUN: %-24s OVR=%-3d %s", p["name"], p["overall"], p["attrs"])
        else:
            try:
                was_existing = upsert_player(
                    name=p["name"],
                    team=p["team"],
                    position=p["position"],
                    attrs=p["attrs"],
                    overall=p["overall"],
                )
                if was_existing:
                    updated += 1
                else:
                    inserted += 1
            except Exception as exc:
                log.error("  upsert_player(%s): %s", p["name"], exc)
                errors += 1

    return {"inserted": inserted, "updated": updated, "errors": errors}


def scrape_all(dry_run: bool = False, team_filter: str | None = None) -> dict:
    slugs = [team_filter] if team_filter else NBA_TEAM_SLUGS
    total = {"inserted": 0, "updated": 0, "errors": 0}
    for i, slug in enumerate(slugs):
        result = scrape_team(slug, dry_run=dry_run)
        for k in total:
            total[k] += result[k]
        if i < len(slugs) - 1:
            time.sleep(2)
    return total


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--dump-html" in args:
        idx = args.index("--dump-html")
        slug = args[idx + 1] if idx + 1 < len(args) else "los-angeles-lakers"
        html = fetch(f"{BASE_URL}/teams/{slug}")
        if not html:
            print("[failed to fetch]")
            sys.exit(1)
        out = f"dump_{slug}.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Saved {len(html)} chars to {out}")
        # Quick sanity check
        soup = BeautifulSoup(html, "html.parser")
        table = soup.select_one("table#lists-table")
        if table:
            rows = table.select("tbody tr")
            print(f"Found table#lists-table with {len(rows)} player rows")
            if rows:
                print("First row data-* attrs:", {k: v for k, v in rows[0].attrs.items() if k.startswith("data-")})
        else:
            print("WARNING: table#lists-table not found — structure may have changed")
        sys.exit(0)

    dry_run = "--dry-run" in args
    team_filter = None
    if "--team" in args:
        idx = args.index("--team")
        team_filter = args[idx + 1] if idx + 1 < len(args) else None

    if not dry_run:
        init_db()

    if dry_run:
        log.info("DRY RUN — no writes to DB.")

    start = datetime.now(timezone.utc)
    result = scrape_all(dry_run=dry_run, team_filter=team_filter)
    elapsed = (datetime.now(timezone.utc) - start).seconds
    log.info(
        "Done in %ds — inserted=%d updated=%d errors=%d",
        elapsed, result["inserted"], result["updated"], result["errors"],
    )
