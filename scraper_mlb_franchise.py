"""
Scrapes MLB The Show 26 franchise/Play-Now player ratings from showdd.io
and upserts into ratingscheck.db.

Franchise OVRs are the base player ratings used in Play Now, Franchise,
and RTTS modes — not the inflated Diamond Dynasty card overalls.

Usage:
    python scraper_mlb_franchise.py              # full scrape
    python scraper_mlb_franchise.py --dry-run    # print without writing
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

DATA_URL = "https://showdd.io/play-now/players/__data.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://showdd.io/play-now/players",
    "Origin": "https://showdd.io",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

TEAM_SLUG_MAP = {
    "angels": "LAA", "astros": "HOU", "athletics": "OAK", "blue-jays": "TOR",
    "braves": "ATL", "brewers": "MIL", "cardinals": "STL", "cubs": "CHC",
    "diamondbacks": "ARI", "dodgers": "LAD", "giants": "SF", "guardians": "CLE",
    "mariners": "SEA", "marlins": "MIA", "mets": "NYM", "nationals": "WSH",
    "orioles": "BAL", "padres": "SD", "phillies": "PHI", "pirates": "PIT",
    "rangers": "TEX", "rays": "TB", "red-sox": "BOS", "reds": "CIN",
    "rockies": "COL", "royals": "KC", "tigers": "DET", "twins": "MIN",
    "white-sox": "CWS", "yankees": "NYY",
}

_POS_MAP = {
    "SP": "SP", "RP": "RP", "CP": "CP",
    "C": "C", "1B": "1B", "2B": "2B", "3B": "3B",
    "SS": "SS", "LF": "LF", "CF": "CF", "RF": "RF",
    "DH": "DH", "OF": "OF", "IF": "IF",
}

_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)


def _decode_svelte(raw: dict) -> tuple[list[dict], int]:
    """Decode SvelteKit flat-indexed data format into a list of player dicts."""
    node = next(
        (n for n in raw.get("nodes", [])
         if n and n.get("type") == "data" and len(n.get("data", [])) > 10),
        None,
    )
    if not node:
        return [], 0

    data = node["data"]
    top = data[0]
    player_indices = data[top["players"]]
    players = []
    for start in player_indices:
        shape = data[start]
        obj = {}
        for field, offset in shape.items():
            try:
                obj[field] = data[offset]
            except (IndexError, TypeError):
                pass
        players.append(obj)

    try:
        total = data[top.get("total_player_count", top.get("total_count", 0))]
    except (IndexError, TypeError):
        total = 0
    return players, int(total) if isinstance(total, (int, float)) else 0


_VERIFY_SSL = True  # set to False via --no-verify flag


def _fetch_page(page: int) -> tuple[list[dict], int]:
    url = f"{DATA_URL}?page={page}"
    try:
        r = _SESSION.get(url, timeout=30, verify=_VERIFY_SSL)
        r.raise_for_status()
        return _decode_svelte(r.json())
    except Exception as exc:
        log.error("fetch page %d: %s", page, exc)
        return [], 0


def _parse_player(raw: dict) -> dict | None:
    name = (raw.get("playerName") or "").strip()
    if not name:
        return None

    team_slug = raw.get("teamSlug") or ""
    team = TEAM_SLUG_MAP.get(team_slug, team_slug.upper() if team_slug else "FA")

    pos_raw = (raw.get("playerPosition") or "").strip().upper()
    position = _POS_MAP.get(pos_raw, pos_raw)

    overall = int(raw.get("overall") or 0)

    def _int(val):
        try:
            return int(val) if val is not None else 0
        except (ValueError, TypeError):
            return 0

    attrs = {k: 0 for k in MLB_ATTR_KEYS}

    # Hitting
    attrs["contactLeft"]      = _int(raw.get("contact_left"))
    attrs["contactRight"]     = _int(raw.get("contact_right"))
    attrs["powerLeft"]        = _int(raw.get("power_left"))
    attrs["powerRight"]       = _int(raw.get("power_right"))
    attrs["plateVision"]      = _int(raw.get("vision"))
    attrs["plateDiscipline"]  = _int(raw.get("discipline"))
    attrs["battingClutch"]    = _int(raw.get("batting_clutch"))
    # Speed / Baserunning
    attrs["speed"]            = _int(raw.get("speed"))
    attrs["baserunningAbility"] = _int(raw.get("stealing"))
    attrs["baserunningAggr"]  = _int(raw.get("baserunning_aggression"))
    # Fielding
    attrs["armStrength"]      = _int(raw.get("arm_strength"))
    attrs["armAccuracy"]      = _int(raw.get("arm_accuracy"))
    attrs["fieldingAbility"]  = _int(raw.get("fielding"))
    attrs["blocking"]         = _int(raw.get("blocking"))
    # Pitching
    attrs["stamina"]          = _int(raw.get("stamina"))
    attrs["pitchingClutch"]   = _int(raw.get("pitch_clutch"))
    attrs["pitchControl"]     = _int(raw.get("pitch_control"))
    attrs["k9Left"]           = _int(raw.get("k9_left"))
    attrs["k9Right"]          = _int(raw.get("k9_right"))
    attrs["h9Left"]           = _int(raw.get("h9_left"))
    attrs["hr9"]              = _int(raw.get("hr9"))
    # Bunting
    attrs["buntingAbility"]   = _int(raw.get("bunt"))
    attrs["dragBuntAbility"]  = _int(raw.get("drag_bunt"))
    # General
    attrs["hittingDurability"] = _int(raw.get("durability"))

    return {
        "name": name,
        "team": team,
        "position": position,
        "overall": overall,
        "attrs": attrs,
    }


def scrape_all(dry_run: bool = False) -> dict:
    # First page to get total
    first_page, total = _fetch_page(1)
    if not first_page:
        log.error("Failed to fetch page 1 — check network/headers")
        return {"inserted": 0, "updated": 0, "errors": 1}

    total_pages = (total + 19) // 20
    log.info("Total franchise players: %d  (~%d pages)", total, total_pages)

    all_raw = list(first_page)
    for page in range(2, total_pages + 1):
        players_page, _ = _fetch_page(page)
        if not players_page:
            log.warning("Empty response on page %d — stopping", page)
            break
        all_raw.extend(players_page)
        if page % 20 == 0:
            log.info("  Page %d/%d — collected %d", page, total_pages, len(all_raw))
        time.sleep(0.25)

    log.info("Fetched %d raw franchise players, parsing...", len(all_raw))

    # Deduplicate by name: for duplicates, keep higher OVR
    seen: dict[str, dict] = {}
    for raw in all_raw:
        p = _parse_player(raw)
        if not p:
            continue
        key = p["name"].lower()
        if key not in seen or p["overall"] > seen[key]["overall"]:
            seen[key] = p

    log.info("Unique players after dedup: %d", len(seen))

    inserted = updated = errors = 0
    for p in seen.values():
        if dry_run:
            log.info("DRY RUN: %-28s OVR=%-3d %s %s",
                     p["name"], p["overall"], p["position"], p["team"])
        else:
            try:
                was_existing = upsert_player(
                    name=p["name"], team=p["team"],
                    position=p["position"], attrs=p["attrs"],
                    overall=p["overall"], sport="mlb",
                )
                updated += was_existing
                inserted += not was_existing
            except Exception as exc:
                log.error("upsert_player(%s): %s", p["name"], exc)
                errors += 1

    return {"inserted": inserted, "updated": updated, "errors": errors}


if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    if "--no-verify" in args:
        import warnings
        warnings.filterwarnings("ignore")
        _VERIFY_SSL = False

    if not dry_run:
        init_db()

    start = datetime.now(timezone.utc)
    result = scrape_all(dry_run=dry_run)
    elapsed = (datetime.now(timezone.utc) - start).seconds
    log.info(
        "Franchise scrape done in %ds — inserted=%d updated=%d errors=%d",
        elapsed, result["inserted"], result["updated"], result["errors"],
    )
