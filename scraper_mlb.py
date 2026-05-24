"""
Scrapes MLB The Show 26 player ratings from the official API and upserts into ratingscheck.db.

The API is open JSON — no auth, no JS rendering needed.
Endpoint: https://mlb26.theshow.com/apis/items.json?type=mlb_card&page=N

Usage:
    python scraper_mlb.py                  # scrape all pages (~97 pages)
    python scraper_mlb.py --dry-run        # print without writing to DB
    python scraper_mlb.py --pages 1-5      # scrape only pages 1–5
    python scraper_mlb.py --dump-json 1    # dump page 1 JSON for inspecti
    on
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone

import requests

from models import init_db, upsert_player, MLB_ATTR_KEYS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)





log = logging.getLogger(__name__)


BASE_URL = "https://mlb26.theshow.com"
ITEMS_URL = f"{BASE_URL}/apis/items.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Maps API snake_case field names → our camelCase keys
API_FIELD_MAP = {
    # Hitting
    "contact_left":            "contactLeft",
    "contact_right":           "contactRight",
    "power_left":              "powerLeft",
    "power_right":             "powerRight",
    "plate_vision":            "plateVision",
    "plate_discipline":        "plateDiscipline",
    "batting_clutch":          "battingClutch",
    # Speed / Baserunning
    "speed":                   "speed",
    "baserunning_ability":     "baserunningAbility",
    "baserunning_aggression":  "baserunningAggr",
    # Fielding
    "arm_strength":            "armStrength",
    "arm_accuracy":            "armAccuracy",
    "fielding_ability":        "fieldingAbility",
    "blocking":                "blocking",
    # Pitching
    "stamina":                 "stamina",
    "pitching_clutch":         "pitchingClutch",
    "bb_per_bf":               "bbPerBf",
    "hr_per_bf":               "hrPerBf",
    "pitch_control":           "pitchControl",
    "pitch_velocity":          "pitchVelocity",
    "pitch_movement":          "pitchMovement",
    # Bunting
    "bunting_ability":         "buntingAbility",
    "drag_bunting_ability":    "dragBuntAbility",
    # General
    "hitting_durability":      "hittingDurability",
}

# Position normalization
_POS_MAP = {
    "SP": "SP", "RP": "RP", "CP": "CP",
    "C": "C", "1B": "1B", "2B": "2B", "3B": "3B",
    "SS": "SS", "LF": "LF", "CF": "CF", "RF": "RF",
    "DH": "DH", "OF": "OF", "IF": "IF",
}

_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)


def fetch_page(page: int, series: str = "Live") -> dict | None:
    url = f"{ITEMS_URL}?type=mlb_card&series={series}&page={page}"
    try:
        r = _SESSION.get(url, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        log.error("fetch_page(%d): %s", page, exc)
        return None


def parse_item(item: dict) -> dict | None:
    """Convert a single API item into our player dict format."""
    name = item.get("name", "").strip()
    if not name:
        return None

    overall = 0
    for field in ["ovr", "ovr_rating", "overall"]:
        val = item.get(field)
        if val is not None:
            try:
                overall = int(val)
                break
            except (ValueError, TypeError):
                pass

    team = (item.get("team_short_name") or item.get("team") or "").strip()
    display_pos = (item.get("display_position") or item.get("position") or "").strip().upper()
    position = _POS_MAP.get(display_pos, display_pos)

    attrs = {k: 0 for k in MLB_ATTR_KEYS}
    for api_field, our_key in API_FIELD_MAP.items():
        val = item.get(api_field)
        if val is not None:
            try:
                attrs[our_key] = int(val)
            except (ValueError, TypeError):
                pass

    return {
        "name": name,
        "team": team,
        "position": position,
        "overall": overall,
        "attrs": attrs,
    }


def scrape_all_pages(
    page_start: int = 1, page_end: int = 120, dry_run: bool = False,
    series: str = "Live",
) -> dict:
    seen: dict[str, dict] = {}  # name → best card (highest OVR)
    inserted = updated = errors = 0

    for page_num in range(page_start, page_end + 1):
        log.info("Page %d", page_num)
        data = fetch_page(page_num, series=series)
        if not data:
            log.warning("  Empty response on page %d, stopping", page_num)
            break

        items = data.get("items", [])
        if not items:
            log.info("  No items on page %d — done", page_num)
            break

        for item in items:
            player = parse_item(item)
            if not player:
                continue
            key = player["name"].lower()
            if key not in seen or player["overall"] > seen[key]["overall"]:
                seen[key] = player

        total_pages = data.get("total_pages", page_end)
        log.info("  Parsed %d items (page %d / %d)", len(items), page_num, total_pages)
        if page_num >= total_pages:
            log.info("Reached last page (%d)", total_pages)
            break

        time.sleep(0.25)

    log.info("Scraped %d unique MLB players, upserting...", len(seen))
    for player in seen.values():
        if dry_run:
            log.info("DRY RUN: %-28s OVR=%-3d %s %s",
                     player["name"], player["overall"], player["position"], player["team"])
        else:
            try:
                was_existing = upsert_player(
                    name=player["name"], team=player["team"],
                    position=player["position"], attrs=player["attrs"],
                    overall=player["overall"], sport="mlb",
                )
                updated += was_existing
                inserted += not was_existing
            except Exception as exc:
                log.error("upsert_player(%s): %s", player["name"], exc)
                errors += 1

    return {"inserted": inserted, "updated": updated, "errors": errors}


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--dump-json" in args:
        idx = args.index("--dump-json")
        page = int(args[idx + 1]) if idx + 1 < len(args) else 1
        data = fetch_page(page)
        if not data:
            print("[failed]")
            sys.exit(1)
        out = f"dump_mlb_p{page}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        items = data.get("items", [])
        print(f"Saved to {out} — {len(items)} items, total_pages={data.get('total_pages')}")
        if items:
            print("First item keys:", list(items[0].keys()))
        sys.exit(0)

    dry_run = "--dry-run" in args
    page_start, page_end = 1, 120
    if "--pages" in args:
        idx = args.index("--pages")
        if idx + 1 < len(args):
            parts = args[idx + 1].split("-")
            try:
                page_start = int(parts[0])
                page_end = int(parts[1]) if len(parts) > 1 else page_start
            except ValueError:
                pass

    if not dry_run:
        init_db()

    start = datetime.now(timezone.utc)
    result = scrape_all_pages(page_start=page_start, page_end=page_end, dry_run=dry_run)
    elapsed = (datetime.now(timezone.utc) - start).seconds
    log.info(
        "MLB done in %ds — inserted=%d updated=%d errors=%d",
        elapsed, result["inserted"], result["updated"], result["errors"],
    )
