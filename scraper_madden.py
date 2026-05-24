"""
Imports Madden 26 player ratings from the official EA spreadsheet into ratingscheck.db.

Data source: "Madden 26 Ratings.xlsx" (two sheets: "Week 1 Ratings", "Launch Ratings").
Week 1 is the default (most current). The spreadsheet has 1,880 real NFL base-roster
players with all standard Madden attributes.

Usage:
    python scraper_madden.py                             # import Week 1 Ratings
    python scraper_madden.py --dry-run                   # print without writing to DB
    python scraper_madden.py --sheet "Launch Ratings"    # import a specific sheet
    python scraper_madden.py --file /path/to/other.xlsx  # use a different file
"""

import logging
import os
import sys
from datetime import datetime, timezone

from models import init_db, upsert_player, MADDEN_ATTR_KEYS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DEFAULT_FILE = os.path.join(os.path.dirname(__file__), "Madden 26 Ratings.xlsx")
DEFAULT_SHEET = "Week 1 Ratings"

# Spreadsheet attribute column name → our camelCase key
# Only entries that differ from the camelCase key need to be listed.
COL_MAP = {
    "awareness":            "awareness",
    "speed":                "speed",
    "acceleration":         "acceleration",
    "agility":              "agility",
    "jumping":              "jumping",
    "stamina":              "stamina",
    "strength":             "strength",
    "toughness":            "toughness",
    "injury":               "injury",
    "throwPower":           "throwPower",
    "throwAccuracyShort":   "throwAccShort",
    "throwAccuracyMid":     "throwAccMed",
    "throwAccuracyDeep":    "throwAccDeep",
    "throwOnTheRun":        "throwAccOnRun",
    "throwUnderPressure":   "throwUnderPressure",
    "playAction":           "playAction",
    "breakSack":            "breakSack",
    "trucking":             "trucking",
    "breakTackle":          "breakTackle",
    "bCVision":             "bcVision",
    "carrying":             "carrying",
    "stiffArm":             "stiffArm",
    "spinMove":             "spinMove",
    "jukeMove":             "jukeMoves",
    "changeOfDirection":    "changeDir",
    "catching":             "catching",
    "spectacularCatch":     "specCatch",
    "shortRouteRunning":    "shortRoute",
    "mediumRouteRunning":   "medRoute",
    "deepRouteRunning":     "deepRoute",
    "release":              "release",
    "catchInTraffic":       "cit",
    "runBlock":             "runBlock",
    "passBlock":            "passBlock",
    "runBlockPower":        "runBlockPow",
    "runBlockFinesse":      "runBlockFin",
    "passBlockPower":       "passBlockPow",
    "passBlockFinesse":     "passBlockFin",
    "impactBlocking":       "impactBlock",
    "leadBlock":            "leadBlock",
    "tackle":               "tackle",
    "hitPower":             "hitPower",
    "pursuit":              "pursuit",
    "playRecognition":      "playRecog",
    "manCoverage":          "manCoverage",
    "zoneCoverage":         "zoneCoverage",
    "press":                "pressing",
    "blockShedding":        "blockShed",
    "finesseMoves":         "finesseMoves",
    "powerMoves":           "powerMoves",
    "kickPower":            "kickPower",
    "kickAccuracy":         "kickAcc",
    "kickReturn":           "kickReturn",
}

# Full NFL team name → abbreviation
NFL_TEAM_ABBR = {
    "Arizona Cardinals":      "ARI",
    "Atlanta Falcons":        "ATL",
    "Baltimore Ravens":       "BAL",
    "Buffalo Bills":          "BUF",
    "Carolina Panthers":      "CAR",
    "Chicago Bears":          "CHI",
    "Cincinnati Bengals":     "CIN",
    "Cleveland Browns":       "CLE",
    "Dallas Cowboys":         "DAL",
    "Denver Broncos":         "DEN",
    "Detroit Lions":          "DET",
    "Green Bay Packers":      "GB",
    "Houston Texans":         "HOU",
    "Indianapolis Colts":     "IND",
    "Jacksonville Jaguars":   "JAX",
    "Kansas City Chiefs":     "KC",
    "Las Vegas Raiders":      "LV",
    "Los Angeles Chargers":   "LAC",
    "Los Angeles Rams":       "LAR",
    "Miami Dolphins":         "MIA",
    "Minnesota Vikings":      "MIN",
    "New England Patriots":   "NE",
    "New Orleans Saints":     "NO",
    "New York Giants":        "NYG",
    "New York Jets":          "NYJ",
    "Philadelphia Eagles":    "PHI",
    "Pittsburgh Steelers":    "PIT",
    "San Francisco 49ers":    "SF",
    "Seattle Seahawks":       "SEA",
    "Tampa Bay Buccaneers":   "TB",
    "Tennessee Titans":       "TEN",
    "Washington Commanders":  "WAS",
    # Free agent / no team
    "FA":                     "FA",
    "Free Agent":             "FA",
}


def _load_workbook(file_path: str):
    try:
        import openpyxl
    except ImportError:
        log.error("openpyxl not installed — run: pip install openpyxl")
        return None
    try:
        return openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    except Exception as exc:
        log.error("Failed to open %s: %s", file_path, exc)
        return None


def _parse_int(value) -> int:
    """Safely convert a cell value to int, returning 0 on failure."""
    if value is None:
        return 0
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return 0


def import_players(
    file_path: str = DEFAULT_FILE,
    sheet_name: str = DEFAULT_SHEET,
    dry_run: bool = False,
) -> dict:
    """Read the Excel spreadsheet and upsert all players into the madden DB."""
    wb = _load_workbook(file_path)
    if wb is None:
        return {"inserted": 0, "updated": 0, "errors": 1}

    if sheet_name not in wb.sheetnames:
        log.error("Sheet '%s' not found. Available: %s", sheet_name, wb.sheetnames)
        return {"inserted": 0, "updated": 0, "errors": 1}

    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        log.error("Sheet '%s' is empty", sheet_name)
        return {"inserted": 0, "updated": 0, "errors": 1}

    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    log.info("Sheet '%s': %d data rows, %d columns", sheet_name, len(rows) - 1, len(header))

    # Locate required columns
    def col(name: str) -> int | None:
        for i, h in enumerate(header):
            if h == name:
                return i
        return None

    # The first column header is a sponsor name (e.g. "Costa Vida") — that's firstName
    first_name_col = 0
    last_name_col = col("lastName")
    team_col = col("Team")
    position_col = col("Position")
    overall_col = col("stats/overall/value")

    missing = []
    if last_name_col is None:
        missing.append("lastName")
    if team_col is None:
        missing.append("Team")
    if position_col is None:
        missing.append("Position")
    if overall_col is None:
        missing.append("stats/overall/value")
    if missing:
        log.error("Missing required columns: %s", missing)
        log.error("Available columns: %s", header[:20])
        return {"inserted": 0, "updated": 0, "errors": 1}

    # Build attribute column index: our_key → col_index
    attr_col_index: dict[str, int] = {}
    for xlsx_name, our_key in COL_MAP.items():
        idx = col(f"stats/{xlsx_name}/value")
        if idx is not None:
            attr_col_index[our_key] = idx

    log.info("Mapped %d / %d attribute columns", len(attr_col_index), len(MADDEN_ATTR_KEYS))

    inserted = updated = errors = skipped = 0
    seen: dict[str, dict] = {}  # name_lower → best player (highest OVR)

    for row_num, row in enumerate(rows[1:], start=2):
        first = str(row[first_name_col]).strip() if row[first_name_col] is not None else ""
        last = str(row[last_name_col]).strip() if row[last_name_col] is not None else ""
        name = f"{first} {last}".strip()
        if not name or name.lower() in ("none none", "none"):
            skipped += 1
            continue

        full_team = str(row[team_col]).strip() if row[team_col] is not None else ""
        team = NFL_TEAM_ABBR.get(full_team, full_team[:3].upper() if full_team else "")

        position = str(row[position_col]).strip() if row[position_col] is not None else ""

        overall = _parse_int(row[overall_col])

        attrs = {k: 0 for k in MADDEN_ATTR_KEYS}
        for our_key, idx in attr_col_index.items():
            if idx < len(row):
                attrs[our_key] = _parse_int(row[idx])

        player = {
            "name": name, "team": team, "position": position,
            "overall": overall, "attrs": attrs,
        }

        key = name.lower()
        if key not in seen or overall > seen[key]["overall"]:
            seen[key] = player

    log.info("Read %d unique players from spreadsheet, upserting...", len(seen))

    for player in seen.values():
        if dry_run:
            log.info("DRY RUN: %-28s OVR=%-3d %-4s %s",
                     player["name"], player["overall"], player["position"], player["team"])
        else:
            try:
                was_existing = upsert_player(
                    name=player["name"], team=player["team"],
                    position=player["position"], attrs=player["attrs"],
                    overall=player["overall"], sport="madden",
                )
                updated += was_existing
                inserted += not was_existing
            except Exception as exc:
                log.error("upsert_player(%s): %s", player["name"], exc)
                errors += 1

    log.info("Skipped %d blank rows", skipped)
    return {"inserted": inserted, "updated": updated, "errors": errors}


if __name__ == "__main__":
    args = sys.argv[1:]

    dry_run = "--dry-run" in args

    file_path = DEFAULT_FILE
    if "--file" in args:
        idx = args.index("--file")
        if idx + 1 < len(args):
            file_path = args[idx + 1]

    sheet_name = DEFAULT_SHEET
    if "--sheet" in args:
        idx = args.index("--sheet")
        if idx + 1 < len(args):
            sheet_name = args[idx + 1]

    if not dry_run:
        init_db()

    start = datetime.now(timezone.utc)
    result = import_players(file_path=file_path, sheet_name=sheet_name, dry_run=dry_run)
    elapsed = (datetime.now(timezone.utc) - start).seconds
    log.info(
        "Madden done in %ds — inserted=%d updated=%d errors=%d",
        elapsed, result["inserted"], result["updated"], result["errors"],
    )
