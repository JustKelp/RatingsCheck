"""
Scrapes NHL 26 player ratings from nhlratings.net and upserts into ratingscheck.db.

Two-pass strategy for maximum coverage:
  Pass 1 — Attribute list pages (/lists/<attr>): each page ranks the top ~700 players
            by a single attribute. Scraping all attr lists gives us every player's
            value for each stat they appear on.
  Pass 2 — Team pages (/teams/<slug>): fills in any players not captured via lists,
            and ensures OVR/team/position are accurate for the full 32-team roster.

Individual player detail pages are only fetched for players still missing key attrs
after both passes.

Usage:
    python scraper_nhl.py                          # full scrape (both passes)
    python scraper_nhl.py --dry-run                # print without writing to DB
    python scraper_nhl.py --team boston-bruins     # one team only (pass 2)
    python scraper_nhl.py --dump-html boston-bruins
    python scraper_nhl.py --dump-player auston-matthews
"""

import logging
import re
import sys
import time
from datetime import datetime, timezone

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from models import init_db, upsert_player, NHL_ATTR_KEYS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BASE_URL = "https://www.nhlratings.net"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

NHL_TEAM_SLUGS = [
    "anaheim-ducks", "boston-bruins", "buffalo-sabres", "calgary-flames",
    "carolina-hurricanes", "chicago-blackhawks", "colorado-avalanche",
    "columbus-blue-jackets", "dallas-stars", "detroit-red-wings",
    "edmonton-oilers", "florida-panthers", "los-angeles-kings",
    "minnesota-wild", "montreal-canadiens", "nashville-predators",
    "new-jersey-devils", "new-york-islanders", "new-york-rangers",
    "ottawa-senators", "philadelphia-flyers", "pittsburgh-penguins",
    "san-jose-sharks", "seattle-kraken", "st-louis-blues",
    "tampa-bay-lightning", "toronto-maple-leafs", "utah-mammoth",
    "vancouver-canucks", "vegas-golden-knights", "washington-capitals",
    "winnipeg-jets",
]

TEAM_ABBR = {
    "anaheim-ducks": "ANA", "boston-bruins": "BOS", "buffalo-sabres": "BUF",
    "calgary-flames": "CGY", "carolina-hurricanes": "CAR", "chicago-blackhawks": "CHI",
    "colorado-avalanche": "COL", "columbus-blue-jackets": "CBJ", "dallas-stars": "DAL",
    "detroit-red-wings": "DET", "edmonton-oilers": "EDM", "florida-panthers": "FLA",
    "los-angeles-kings": "LAK", "minnesota-wild": "MIN", "montreal-canadiens": "MTL",
    "nashville-predators": "NSH", "new-jersey-devils": "NJD", "new-york-islanders": "NYI",
    "new-york-rangers": "NYR", "ottawa-senators": "OTT", "philadelphia-flyers": "PHI",
    "pittsburgh-penguins": "PIT", "san-jose-sharks": "SJS", "seattle-kraken": "SEA",
    "st-louis-blues": "STL", "tampa-bay-lightning": "TBL", "toronto-maple-leafs": "TOR",
    "utah-mammoth": "UTA", "vancouver-canucks": "VAN", "vegas-golden-knights": "VGK",
    "washington-capitals": "WSH", "winnipeg-jets": "WPG",
}

# Maps site attribute labels (lowercase) → our camelCase keys
ATTR_LABEL_MAP = {
    "speed": "speed", "acceleration": "acceleration", "agility": "agility",
    "balance": "balance", "endurance": "endurance", "strength": "strength",
    "slap shot power": "slapShotPow", "slap shot accuracy": "slapShotAcc",
    "wrist shot power": "wristShotPow", "wrist shot accuracy": "wristShotAcc",
    "slap shot": "slapShotPow", "wrist shot": "wristShotPow",
    "pass accuracy": "passAcc", "passing": "passAcc",
    "puck control": "puckControl",
    "hand eye": "handEye", "hand-eye": "handEye", "deking": "deking",
    "offensive awareness": "offAwareness", "defensive awareness": "defAwareness",
    "body checking": "bodyChecking", "shot blocking": "shotBlocking",
    "stick checking": "stickChecking",
    "faceoffs": "faceoffs", "durability": "durability",
    "fighting": "fighting", "fighting skill": "fighting",
    "discipline": "discipline", "aggression": "aggression",
    "toughness": "toughness", "poise": "poise",
    "breakaway": "gBreakaway", "aggressiveness": "gAggressiveness",
    "angles": "gAngles", "crease": "gCrease",
    "dexterity": "gDexterity", "rebound control": "gReboundControl",
    "poke check": "gPokeCheck", "reflexes": "gReflexes",
    "recovery": "gRecovery", "vision": "gVision",
    "goalie durability": "gDurability",
}

# nhlratings.net /lists/<slug> → our camelCase key
# These are the attribute list pages that rank ALL players by a single stat
LIST_SLUG_MAP = {
    "speed": "speed",
    "acceleration": "acceleration",
    "agility": "agility",
    "balance": "balance",
    "endurance": "endurance",
    "strength": "strength",
    "slap-shot-power": "slapShotPow",
    "slap-shot-accuracy": "slapShotAcc",
    "wrist-shot-power": "wristShotPow",
    "wrist-shot-accuracy": "wristShotAcc",
    "passing": "passAcc",
    "puck-control": "puckControl",
    "hand-eye": "handEye",
    "deking": "deking",
    "offensive-awareness": "offAwareness",
    "defensive-awareness": "defAwareness",
    "body-checking": "bodyChecking",
    "shot-blocking": "shotBlocking",
    "stick-checking": "stickChecking",
    "faceoffs": "faceoffs",
    "durability": "durability",
    "fighting": "fighting",
    "discipline": "discipline",
    "aggression": "aggression",
    "toughness": "toughness",
    "poise": "poise",
    # Goalie attrs
    "reflexes": "gReflexes",
    "angles": "gAngles",
    "rebound-control": "gReboundControl",
    "poke-check": "gPokeCheck",
    "recovery": "gRecovery",
    "breakaway": "gBreakaway",
    "dexterity": "gDexterity",
    "vision": "gVision",
    "aggressiveness": "gAggressiveness",
    "crease": "gCrease",
}

_POS_MAP = {
    "center": "C", "left wing": "LW", "right wing": "RW",
    "defense": "D", "defenseman": "D", "goalie": "G", "goaltender": "G",
    "c": "C", "lw": "LW", "rw": "RW", "d": "D", "g": "G",
    "f": "F", "forward": "F",
}

_SKIP_PATHS = frozenset([
    "", "teams", "lists", "countries", "about", "contact",
    "privacy-policy", "terms", "sitemap", "search",
    "nhl-27-release-date", "abilities-meanings",
])

_ATTR_ROW_RE = re.compile(r"^(\d{1,3})\s+([A-Za-z][A-Za-z0-9\s\-]{1,40})$")

_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)
_SESSION.verify = False


def fetch(url: str) -> str | None:
    try:
        r = _SESSION.get(url, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as exc:
        log.error("fetch(%s): %s", url, exc)
        return None


# ── Pass 1: attribute list pages ───────────────────────────────────────────────

def parse_list_page(html: str, our_key: str) -> list[dict]:
    """
    Parse a /lists/<attr> page. Returns list of:
      {slug, name, team_full, position_raw, overall, attr_value}
    The table typically has columns: Rank | Player | Team | Position | OVR | Value
    but the layout varies; we use heuristics.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for row in soup.select("tr"):
        cells = [td.get_text(strip=True) for td in row.select("td")]
        if len(cells) < 3:
            continue

        # Find numeric value cell (the attribute score, typically last meaningful cell)
        # and a name cell (contains a link to a player slug)
        link_el = row.select_one("a[href]")
        if not link_el:
            continue
        href = link_el.get("href", "")
        # Extract slug from absolute or relative URL
        if href.startswith(BASE_URL + "/"):
            slug = href[len(BASE_URL) + 1:].strip("/")
        elif href.startswith("/"):
            slug = href[1:].strip("/")
        else:
            slug = href.strip("/")

        if not slug or "/" in slug or slug in _SKIP_PATHS:
            continue

        name = link_el.get_text(strip=True)
        if not name:
            continue

        # Find numeric values in cells
        nums = []
        for c in cells:
            try:
                nums.append(int(c))
            except ValueError:
                pass

        if len(nums) < 1:
            continue

        # Last number is the attribute value, second-to-last (if present) is OVR
        attr_val = nums[-1]
        overall = nums[-2] if len(nums) >= 2 else 0

        # Team and position from remaining text cells
        text_cells = [c for c in cells if c and not c.isdigit()]
        team_full = text_cells[1] if len(text_cells) > 1 else ""
        position_raw = text_cells[2] if len(text_cells) > 2 else ""

        results.append({
            "slug": slug,
            "name": name,
            "team_full": team_full,
            "position_raw": position_raw,
            "overall": overall,
            "attr_key": our_key,
            "attr_val": attr_val,
        })

    return results


# ── Pass 2: team roster pages ──────────────────────────────────────────────────

def parse_team_page(html: str, team_slug: str) -> list[dict]:
    """Return list of {slug, name, overall, position_raw} from a team roster page."""
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    players = []
    skip = _SKIP_PATHS | {team_slug}

    for row in soup.select("tr"):
        link_el = row.select_one("a[href]")
        if not link_el:
            continue
        href = link_el.get("href", "")
        if href.startswith(BASE_URL + "/"):
            path = href[len(BASE_URL) + 1:]
        elif href.startswith("/") and not href.startswith("//"):
            path = href[1:]
        else:
            continue
        slug = path.split("/")[0].split("?")[0].split("#")[0]
        if not slug or slug in skip:
            continue
        if not re.match(r"^[a-z0-9][a-z0-9\-]{1,60}$", slug):
            continue
        if slug in seen:
            continue
        seen.add(slug)

        name = link_el.get_text(strip=True)
        cells = [td.get_text(strip=True) for td in row.select("td")]
        nums = [int(c) for c in cells if c.isdigit()]
        overall = nums[0] if nums else 0
        text_cells = [c for c in cells if c and not c.isdigit()]
        position_raw = text_cells[-1] if text_cells else ""

        if name:
            players.append({
                "slug": slug,
                "name": name,
                "overall": overall,
                "position_raw": position_raw,
            })

    # Fallback: link-based extraction if table parse found nothing
    if not players:
        skip2 = _SKIP_PATHS | {team_slug}
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if href.startswith(BASE_URL + "/"):
                path = href[len(BASE_URL) + 1:]
            elif href.startswith("/") and not href.startswith("//"):
                path = href[1:]
            else:
                continue
            slug = path.split("/")[0].split("?")[0].split("#")[0]
            if not slug or slug in skip2:
                continue
            if not re.match(r"^[a-z0-9][a-z0-9\-]{1,60}$", slug):
                continue
            if slug in seen:
                continue
            seen.add(slug)
            name = a.get_text(strip=True)
            if name:
                players.append({"slug": slug, "name": name, "overall": 0, "position_raw": ""})

    return players


def parse_player_page(html: str, team_abbr: str) -> dict | None:
    """Full attribute parse from an individual player detail page."""
    soup = BeautifulSoup(html, "html.parser")

    name = ""
    for sel in ["h1", ".player-name", ".name"]:
        el = soup.select_one(sel)
        if el:
            name = el.get_text(strip=True)
            if name:
                break
    if not name:
        return None
    name = re.sub(r"\s+\d{2,3}$", "", name).strip()

    overall = 0
    page_text = soup.get_text(" ")
    m_ovr = re.search(r"Overall Rating of (\d+)", page_text)
    if m_ovr:
        overall = int(m_ovr.group(1))
    if not overall:
        for tr in soup.select("tr"):
            m2 = re.match(r"NHL\s*26\s+(\d+)", tr.get_text(" ", strip=True))
            if m2:
                overall = int(m2.group(1))
                break

    position = ""
    subtitle = soup.select_one(".header-subtitle")
    if subtitle:
        m_pos = re.search(r"Position:[^(]+\(([A-Z]+)\)", subtitle.get_text())
        if m_pos:
            position = m_pos.group(1)
    if not position:
        for el in soup.select(".player-info, .position, [class*='position']"):
            raw = el.get_text(strip=True)
            m_pos2 = re.search(r"Position:[^(]+\(([A-Z]+)\)", raw)
            if m_pos2:
                position = m_pos2.group(1)
                break

    attrs = {k: 0 for k in NHL_ATTR_KEYS}
    for tag in soup.find_all(["tr", "li", "div", "td", "span", "p"]):
        text = tag.get_text(" ", strip=True)
        m = _ATTR_ROW_RE.match(text)
        if not m:
            continue
        val_str, label = m.group(1), m.group(2).strip().lower()
        key = ATTR_LABEL_MAP.get(label)
        if key and key in attrs and attrs[key] == 0:
            try:
                attrs[key] = int(val_str)
            except ValueError:
                pass

    for row in soup.select("tr"):
        cells = row.select("td, th")
        if len(cells) >= 2:
            label = cells[0].get_text(strip=True).lower()
            val_text = cells[-1].get_text(strip=True)
            key = ATTR_LABEL_MAP.get(label)
            if key and key in attrs and attrs[key] == 0:
                try:
                    attrs[key] = int(val_text)
                except ValueError:
                    pass

    return {"name": name, "team": team_abbr, "position": position,
            "overall": overall, "attrs": attrs}


# ── Team full-name → abbreviation (for list pages) ────────────────────────────

_TEAM_NAME_ABBR = {
    "anaheim ducks": "ANA", "boston bruins": "BOS", "buffalo sabres": "BUF",
    "calgary flames": "CGY", "carolina hurricanes": "CAR", "chicago blackhawks": "CHI",
    "colorado avalanche": "COL", "columbus blue jackets": "CBJ", "dallas stars": "DAL",
    "detroit red wings": "DET", "edmonton oilers": "EDM", "florida panthers": "FLA",
    "los angeles kings": "LAK", "minnesota wild": "MIN", "montreal canadiens": "MTL",
    "nashville predators": "NSH", "new jersey devils": "NJD", "new york islanders": "NYI",
    "new york rangers": "NYR", "ottawa senators": "OTT", "philadelphia flyers": "PHI",
    "pittsburgh penguins": "PIT", "san jose sharks": "SJS", "seattle kraken": "SEA",
    "st. louis blues": "STL", "st louis blues": "STL",
    "tampa bay lightning": "TBL", "toronto maple leafs": "TOR", "utah mammoth": "UTA",
    "vancouver canucks": "VAN", "vegas golden knights": "VGK",
    "washington capitals": "WSH", "winnipeg jets": "WPG",
}


def _team_abbr_from_name(full_name: str) -> str:
    return _TEAM_NAME_ABBR.get(full_name.lower().strip(), full_name[:3].upper())


def _norm_pos(raw: str) -> str:
    return _POS_MAP.get(raw.lower().strip(), raw.upper()[:2])


# ── Main scrape orchestration ─────────────────────────────────────────────────

def scrape_all(dry_run: bool = False, team_filter: str | None = None) -> dict:
    # player data keyed by slug: {name, team, position, overall, attrs{}}
    players: dict[str, dict] = {}

    def _ensure(slug: str, name: str) -> dict:
        if slug not in players:
            players[slug] = {
                "name": name, "team": "", "position": "", "overall": 0,
                "attrs": {k: 0 for k in NHL_ATTR_KEYS},
            }
        return players[slug]

    # ── Pass 1: attribute list pages ──────────────────────────────────────────
    if not team_filter:
        log.info("Pass 1: scraping %d attribute list pages...", len(LIST_SLUG_MAP))
        for list_slug, our_key in LIST_SLUG_MAP.items():
            url = f"{BASE_URL}/lists/{list_slug}"
            log.info("  List: %s → %s", list_slug, our_key)
            html = fetch(url)
            if not html:
                continue
            entries = parse_list_page(html, our_key)
            log.info("    %d entries", len(entries))
            for e in entries:
                p = _ensure(e["slug"], e["name"])
                if e["overall"] and not p["overall"]:
                    p["overall"] = e["overall"]
                if e["team_full"] and not p["team"]:
                    p["team"] = _team_abbr_from_name(e["team_full"])
                if e["position_raw"] and not p["position"]:
                    p["position"] = _norm_pos(e["position_raw"])
                if e["attr_val"] and p["attrs"].get(our_key, 0) == 0:
                    p["attrs"][our_key] = e["attr_val"]
            time.sleep(0.5)

        log.info("Pass 1 complete: %d unique players", len(players))

    # ── Pass 2: team roster pages ─────────────────────────────────────────────
    slugs = [team_filter] if team_filter else NHL_TEAM_SLUGS
    log.info("Pass 2: scraping %d team pages...", len(slugs))

    for team_slug in slugs:
        team_abbr = TEAM_ABBR.get(team_slug, team_slug[:3].upper())
        url = f"{BASE_URL}/teams/{team_slug}"
        log.info("  Team: %s (%s)", team_slug, team_abbr)
        html = fetch(url)
        if not html:
            continue
        roster = parse_team_page(html, team_slug)
        log.info("    %d player links", len(roster))

        for stub in roster:
            p = _ensure(stub["slug"], stub["name"])
            # Team pages are authoritative for team/position/OVR
            p["team"] = team_abbr
            if stub["overall"]:
                p["overall"] = stub["overall"]
            if stub["position_raw"] and not p["position"]:
                p["position"] = _norm_pos(stub["position_raw"])

            # If this player still has no attrs, try their detail page
            has_attrs = any(v > 0 for v in p["attrs"].values())
            if not has_attrs:
                purl = f"{BASE_URL}/{stub['slug']}"
                phtml = fetch(purl)
                if phtml:
                    detail = parse_player_page(phtml, team_abbr)
                    if detail:
                        p["name"] = detail["name"] or p["name"]
                        if detail["position"]:
                            p["position"] = detail["position"]
                        if detail["overall"]:
                            p["overall"] = detail["overall"]
                        for k, v in detail["attrs"].items():
                            if v and p["attrs"].get(k, 0) == 0:
                                p["attrs"][k] = v
                time.sleep(0.4)
        time.sleep(1)

    log.info("Total unique players after both passes: %d", len(players))

    inserted = updated = errors = 0
    for p in players.values():
        if not p["name"]:
            continue
        if dry_run:
            has = sum(1 for v in p["attrs"].values() if v > 0)
            log.info("DRY RUN: %-28s OVR=%-3d %-4s %s (%d attrs)",
                     p["name"], p["overall"], p["position"], p["team"], has)
        else:
            try:
                was_existing = upsert_player(
                    name=p["name"], team=p["team"],
                    position=p["position"], attrs=p["attrs"],
                    overall=p["overall"], sport="nhl",
                )
                updated += was_existing
                inserted += not was_existing
            except Exception as exc:
                log.error("upsert_player(%s): %s", p["name"], exc)
                errors += 1

    return {"inserted": inserted, "updated": updated, "errors": errors}


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--dump-html" in args:
        idx = args.index("--dump-html")
        slug = args[idx + 1] if idx + 1 < len(args) else "toronto-maple-leafs"
        html = fetch(f"{BASE_URL}/teams/{slug}")
        if not html:
            print("[failed]")
            sys.exit(1)
        out = f"dump_nhl_{slug}.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Saved {len(html)} chars to {out}")
        roster = parse_team_page(html, slug)
        print(f"Found {len(roster)} players")
        for p in roster[:5]:
            print(f"  {p}")
        sys.exit(0)

    if "--dump-player" in args:
        idx = args.index("--dump-player")
        player_slug = args[idx + 1] if idx + 1 < len(args) else "auston-matthews"
        url = f"{BASE_URL}/{player_slug}"
        html = fetch(url)
        if not html:
            print("[failed]")
            sys.exit(1)
        out = f"dump_nhl_player_{player_slug}.html"
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Saved {len(html)} chars to {out}")
        player = parse_player_page(html, "???")
        if player:
            print(f"Name: {player['name']}  OVR: {player['overall']}  POS: {player['position']}")
            for k, v in player["attrs"].items():
                if v:
                    print(f"  {k}: {v}")
        else:
            print("[parse failed]")
        sys.exit(0)

    dry_run = "--dry-run" in args
    team_filter = None
    if "--team" in args:
        idx = args.index("--team")
        team_filter = args[idx + 1] if idx + 1 < len(args) else None

    if not dry_run:
        init_db()

    start = datetime.now(timezone.utc)
    result = scrape_all(dry_run=dry_run, team_filter=team_filter)
    elapsed = (datetime.now(timezone.utc) - start).seconds
    log.info(
        "NHL done in %ds — inserted=%d updated=%d errors=%d",
        elapsed, result["inserted"], result["updated"], result["errors"],
    )
