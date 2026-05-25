"""
Database layer for Rebuildle. All SQLite access goes through here.

DB_PATH defaults to ratingscheck.db next to this file; override with
the RATINGSCHECK_DB env var.
"""

import json
import os
import re
import sqlite3
from datetime import datetime

DB_PATH = os.environ.get(
    "RATINGSCHECK_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "ratingscheck.db"),
)

# ── NBA 2K ──────────────────────────────────────────────────────────────────────
NBA_ATTR_KEYS = [
    # Shooting
    "closeShot", "freeThrow", "three", "midRange", "shotIQ", "offConsistency",
    # Inside scoring
    "layup", "drivingDunk", "standingDunk", "postHook", "postFade", "postControl",
    # Athleticism
    "speed", "agility", "vertical", "strength", "hustle", "stamina", "drawFoul", "hands",
    # Ball handling
    "ballHandle", "speedWithBall",
    # Passing
    "passAcc", "passVision", "passIQ",
    # Defense
    "block", "steal", "interiorD", "perimeterD", "defConsistency", "helpDefIQ", "passPerception",
    # Rebounding
    "defRebound", "offRebound",
    # Misc
    "durability", "intangibles",
]

# ── NHL 26 ───────────────────────────────────────────────────────────────────────
NHL_ATTR_KEYS = [
    # Skating
    "speed", "acceleration", "agility", "balance", "endurance", "strength",
    # Shooting
    "slapShotPow", "slapShotAcc", "wristShotPow", "wristShotAcc",
    # Puck skills
    "passAcc", "puckControl", "handEye", "deking",
    # Awareness
    "offAwareness", "defAwareness",
    # Physical / Misc (skater)
    "bodyChecking", "shotBlocking", "stickChecking", "faceoffs", "durability",
    "fighting", "discipline", "aggression", "toughness", "poise",
    # Goalie-only (= 0 for skaters)
    "gBreakaway", "gAggressiveness", "gAngles", "gCrease",
    "gDefAwareness", "gDexterity", "gDurability", "gReboundControl",
    "gPokeCheck", "gReflexes", "gRecovery", "gVision",
]

# ── Madden 26 ────────────────────────────────────────────────────────────────────
MADDEN_ATTR_KEYS = [
    # General
    "awareness", "speed", "acceleration", "agility", "jumping",
    "stamina", "strength", "toughness", "injury",
    # QB passing
    "throwPower", "throwAccShort", "throwAccMed", "throwAccDeep",
    "throwAccOnRun", "throwUnderPressure", "playAction", "breakSack",
    # Ball carrier
    "trucking", "breakTackle", "bcVision", "carrying",
    "stiffArm", "spinMove", "jukeMoves", "changeDir",
    # Receiving
    "catching", "specCatch", "shortRoute", "medRoute", "deepRoute", "release", "cit",
    # Blocking
    "runBlock", "passBlock", "runBlockPow", "runBlockFin",
    "passBlockPow", "passBlockFin", "impactBlock", "leadBlock",
    # Defense
    "tackle", "hitPower", "pursuit", "playRecog",
    "manCoverage", "zoneCoverage", "pressing",
    "blockShed", "finesseMoves", "powerMoves",
    # Special teams
    "kickPower", "kickAcc", "kickReturn",
]

# ── MLB The Show 26 ──────────────────────────────────────────────────────────────
MLB_ATTR_KEYS = [
    # Hitting
    "contactLeft", "contactRight", "powerLeft", "powerRight",
    "plateVision", "plateDiscipline", "battingClutch",
    # Speed / Baserunning
    "speed", "baserunningAbility", "baserunningAggr",
    # Fielding
    "armStrength", "armAccuracy", "fieldingAbility", "blocking",
    # Pitching (= 0 for hitters)
    "stamina", "pitchingClutch", "bbPerBf", "hrPerBf",
    "pitchControl", "pitchVelocity", "pitchMovement",
    # Bunting
    "buntingAbility", "dragBuntAbility",
    # General
    "hittingDurability",
]

# Sport → attr keys lookup
SPORT_ATTR_KEYS = {
    "nba":    NBA_ATTR_KEYS,
    "nhl":    NHL_ATTR_KEYS,
    "madden": MADDEN_ATTR_KEYS,
    "mlb":    MLB_ATTR_KEYS,
}

# Backward-compat alias (old scraper + admin code reference ATTR_KEYS directly)
ATTR_KEYS = NBA_ATTR_KEYS

VALID_SPORTS = frozenset(SPORT_ATTR_KEYS)


def _sport_tables(sport: str) -> tuple[str, str, str]:
    """Return (players_table, puzzles_table, sessions_table) for a sport."""
    if sport == "nba":
        return "players", "daily_puzzles", "game_sessions"
    s = sport.replace("-", "_")
    return f"players_{s}", f"daily_puzzles_{s}", f"game_sessions_{s}"


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _con(readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        uri = f"file:{DB_PATH}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
    else:
        con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    """Create tables for all sports if they don't exist."""
    con = _con()

    for sport, attr_keys in SPORT_ATTR_KEYS.items():
        pt, dt, st = _sport_tables(sport)
        attr_col_defs = "\n".join(
            f"    {k:<25} INTEGER NOT NULL DEFAULT 0," for k in attr_keys
        )
        con.executescript(f"""
        CREATE TABLE IF NOT EXISTS {pt} (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            name                  TEXT    UNIQUE NOT NULL,
            team                  TEXT    NOT NULL DEFAULT '',
            position              TEXT    NOT NULL DEFAULT '',
            slug                  TEXT    UNIQUE NOT NULL,
{attr_col_defs}
            overall               INTEGER NOT NULL DEFAULT 0,
            last_scraped          DATETIME,
            manual_overrides_json TEXT    NOT NULL DEFAULT '{{}}'
        );

        CREATE TABLE IF NOT EXISTS {dt} (
            date              TEXT    PRIMARY KEY,
            player_id         INTEGER NOT NULL REFERENCES {pt}(id),
            reveal_order_json TEXT    NOT NULL,
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_by        TEXT
        );

        CREATE TABLE IF NOT EXISTS {st} (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      TEXT,
            guest_uuid   TEXT,
            date         TEXT    NOT NULL,
            guesses_json TEXT    NOT NULL DEFAULT '[]',
            won          INTEGER NOT NULL DEFAULT 0,
            completed    INTEGER NOT NULL DEFAULT 0,
            completed_at DATETIME,
            UNIQUE(user_id, date),
            UNIQUE(guest_uuid, date)
        );
        """)

    con.executescript("""
    CREATE TABLE IF NOT EXISTS user_stats (
        user_id           TEXT    PRIMARY KEY,
        current_streak    INTEGER NOT NULL DEFAULT 0,
        max_streak        INTEGER NOT NULL DEFAULT 0,
        total_played      INTEGER NOT NULL DEFAULT 0,
        total_won         INTEGER NOT NULL DEFAULT 0,
        distribution_json TEXT    NOT NULL DEFAULT '{"1":0,"2":0,"3":0,"4":0,"5":0,"6":0,"fail":0}'
    );
    """)

    con.commit()
    con.close()
    migrate_db()


def migrate_db() -> None:
    """Upgrade existing DB schema for all sports."""
    con = _con()

    for sport, attr_keys in SPORT_ATTR_KEYS.items():
        pt, _, _ = _sport_tables(sport)
        try:
            cols_raw = con.execute(f"PRAGMA table_info({pt})").fetchall()
        except Exception:
            continue
        cols = {row[1] for row in cols_raw}

        if sport == "nba":
            # Old column renames that existed before the 36-attr expansion
            for old_col, new_col in [("speed", "speedWithBall"), ("rebounding", "defRebound")]:
                if old_col in cols and new_col not in cols:
                    try:
                        con.execute(f"ALTER TABLE {pt} RENAME COLUMN {old_col} TO {new_col}")
                        cols.discard(old_col)
                        cols.add(new_col)
                        print(f"[INFO] migrate_db: renamed {pt}.{old_col} → {new_col}")
                    except Exception as exc:
                        print(f"[WARN] migrate_db: could not rename {old_col}: {exc}")

        for key in attr_keys:
            if key not in cols:
                try:
                    con.execute(f"ALTER TABLE {pt} ADD COLUMN {key} INTEGER NOT NULL DEFAULT 0")
                    print(f"[INFO] migrate_db: added {pt}.{key}")
                except Exception as exc:
                    print(f"[WARN] migrate_db: could not add {pt}.{key}: {exc}")

    con.commit()
    con.close()


def _apply_overrides(row: dict, attr_keys: list) -> dict:
    overrides = {}
    try:
        overrides = json.loads(row.get("manual_overrides_json") or "{}")
    except (json.JSONDecodeError, TypeError) as exc:
        print(f"[WARN] bad manual_overrides_json for {row.get('name')}: {exc}")
    for key, val in overrides.items():
        if key in attr_keys:
            row[key] = val
    return row


def get_all_players(sport: str = "nba") -> list[dict]:
    attr_keys = SPORT_ATTR_KEYS.get(sport, NBA_ATTR_KEYS)
    pt, _, _ = _sport_tables(sport)
    # NHL: skaters need speed > 0 and a non-goalie position; goalies need gReflexes > 0
    quality_filter = (
        " WHERE (speed > 0 AND position NOT LIKE 'G%') OR gReflexes > 0"
    ) if sport == "nhl" else ""
    try:
        con = _con()
        rows = con.execute(
            f"SELECT * FROM {pt}{quality_filter} ORDER BY overall DESC, name ASC"
        ).fetchall()
        con.close()
        return [_apply_overrides(dict(r), attr_keys) for r in rows]
    except Exception as exc:
        print(f"[ERROR] get_all_players({sport}): {exc}")
        return []


def get_player_by_id(player_id: int, sport: str = "nba") -> dict | None:
    attr_keys = SPORT_ATTR_KEYS.get(sport, NBA_ATTR_KEYS)
    pt, _, _ = _sport_tables(sport)
    try:
        con = _con()
        row = con.execute(f"SELECT * FROM {pt} WHERE id=?", (player_id,)).fetchone()
        con.close()
        return _apply_overrides(dict(row), attr_keys) if row else None
    except Exception as exc:
        print(f"[ERROR] get_player_by_id({player_id}, {sport}): {exc}")
        return None


def upsert_player(
    name: str, team: str, position: str, attrs: dict,
    overall: int = 0, sport: str = "nba",
) -> bool:
    """Insert or update a player. Returns True if row already existed (UPDATE)."""
    attr_keys = SPORT_ATTR_KEYS.get(sport, NBA_ATTR_KEYS)
    pt, _, _ = _sport_tables(sport)
    slug = slugify(name)
    now = datetime.utcnow().isoformat()
    safe_attrs = {k: int(attrs.get(k, 0)) for k in attr_keys}
    attr_vals = [safe_attrs[k] for k in attr_keys]

    try:
        con = _con()
        existing = con.execute(f"SELECT id FROM {pt} WHERE slug=?", (slug,)).fetchone()
        if existing:
            set_clause = ", ".join(f"{k}=?" for k in attr_keys)
            con.execute(
                f"UPDATE {pt} SET name=?, team=?, position=?, {set_clause}, overall=?, last_scraped=? WHERE slug=?",
                [name, team, position] + attr_vals + [overall, now, slug],
            )
            con.commit()
            con.close()
            return True
        else:
            attr_col_names = ", ".join(attr_keys)
            vals = [name, team, position, slug] + attr_vals + [overall, now, "{}"]
            placeholders = ", ".join("?" for _ in vals)
            con.execute(
                f"INSERT INTO {pt} (name, team, position, slug, {attr_col_names}, overall, last_scraped, manual_overrides_json) "
                f"VALUES ({placeholders})",
                vals,
            )
            con.commit()
            con.close()
            return False
    except Exception as exc:
        print(f"[ERROR] upsert_player({name}, {sport}): {exc}")
        return False


def apply_override(player_id: int, attribute: str, value: int, sport: str = "nba") -> bool:
    attr_keys = SPORT_ATTR_KEYS.get(sport, NBA_ATTR_KEYS)
    if attribute not in attr_keys:
        return False
    pt, _, _ = _sport_tables(sport)
    try:
        con = _con()
        row = con.execute(
            f"SELECT manual_overrides_json FROM {pt} WHERE id=?", (player_id,)
        ).fetchone()
        if not row:
            con.close()
            return False
        try:
            overrides = json.loads(row["manual_overrides_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            overrides = {}
        overrides[attribute] = int(value)
        con.execute(
            f"UPDATE {pt} SET {attribute}=?, manual_overrides_json=? WHERE id=?",
            (int(value), json.dumps(overrides), player_id),
        )
        con.commit()
        con.close()
        return True
    except Exception as exc:
        print(f"[ERROR] apply_override(player_id={player_id}, {attribute}={value}, {sport}): {exc}")
        return False


def get_today_puzzle_db(date_str: str, sport: str = "nba") -> dict | None:
    pt, dt, _ = _sport_tables(sport)
    try:
        con = _con()
        row = con.execute(
            f"SELECT p.name, dp.reveal_order_json FROM {dt} dp "
            f"JOIN {pt} p ON p.id = dp.player_id WHERE dp.date=?",
            (date_str,),
        ).fetchone()
        con.close()
        if not row:
            return None
        return {
            "target": row["name"],
            "revealOrder": json.loads(row["reveal_order_json"]),
        }
    except Exception as exc:
        print(f"[ERROR] get_today_puzzle_db({date_str}, {sport}): {exc}")
        return None


def save_daily_puzzle(
    date_str: str, player_id: int, reveal_order: list,
    created_by: str = "", sport: str = "nba",
) -> bool:
    pt, dt, _ = _sport_tables(sport)
    try:
        con = _con()
        con.execute(
            f"""INSERT OR REPLACE INTO {dt}
               (date, player_id, reveal_order_json, created_at, created_by)
               VALUES (?,?,?,?,?)""",
            (date_str, player_id, json.dumps(reveal_order), datetime.utcnow().isoformat(), created_by),
        )
        con.commit()
        con.close()
        return True
    except Exception as exc:
        print(f"[ERROR] save_daily_puzzle({date_str}, {sport}): {exc}")
        return False


def get_past_puzzles(limit: int = 0, sport: str = "nba") -> list[dict]:
    pt, dt, _ = _sport_tables(sport)
    try:
        con = _con()
        rows = con.execute(
            f"SELECT dp.date, p.name FROM {dt} dp JOIN {pt} p ON p.id=dp.player_id "
            "WHERE dp.date < date('now') ORDER BY dp.date DESC",
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        print(f"[ERROR] get_past_puzzles({sport}): {exc}")
        return []


def get_upcoming_puzzles(days: int = 14, sport: str = "nba") -> list[dict]:
    pt, dt, _ = _sport_tables(sport)
    try:
        con = _con()
        rows = con.execute(
            f"SELECT dp.date, p.name, p.team, p.position, dp.reveal_order_json "
            f"FROM {dt} dp JOIN {pt} p ON p.id=dp.player_id "
            "WHERE dp.date >= date('now') ORDER BY dp.date LIMIT ?",
            (days,),
        ).fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        print(f"[ERROR] get_upcoming_puzzles({sport}): {exc}")
        return []


def get_or_create_user_stats(user_id: str) -> dict:
    try:
        con = _con()
        row = con.execute("SELECT * FROM user_stats WHERE user_id=?", (user_id,)).fetchone()
        if row:
            con.close()
            result = dict(row)
            result["distribution"] = json.loads(result.pop("distribution_json", "{}"))
            return result
        con.execute(
            "INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (user_id,)
        )
        con.commit()
        row = con.execute("SELECT * FROM user_stats WHERE user_id=?", (user_id,)).fetchone()
        con.close()
        result = dict(row)
        result["distribution"] = json.loads(result.pop("distribution_json", "{}"))
        return result
    except Exception as exc:
        print(f"[ERROR] get_or_create_user_stats({user_id}): {exc}")
        return {
            "user_id": user_id, "current_streak": 0, "max_streak": 0,
            "total_played": 0, "total_won": 0,
            "distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6": 0, "fail": 0},
        }


def save_game_session(user_id: str, sport: str, date_str: str, won: bool, guess_names: list) -> bool:
    """Persist a completed game. Returns True if this is a new completion, False if replacing."""
    _, _, st = _sport_tables(sport)
    try:
        con = _con()
        existing = con.execute(
            f"SELECT id FROM {st} WHERE user_id=? AND date=? AND completed=1",
            (user_id, date_str),
        ).fetchone()
        is_new = existing is None
        con.execute(
            f"""INSERT OR REPLACE INTO {st}
               (user_id, date, guesses_json, won, completed, completed_at)
               VALUES (?,?,?,?,1,CURRENT_TIMESTAMP)""",
            (user_id, date_str, json.dumps(guess_names), 1 if won else 0),
        )
        con.commit()
        con.close()
        return is_new
    except Exception as exc:
        print(f"[ERROR] save_game_session({user_id}, {sport}, {date_str}): {exc}")
        return False


def get_user_sport_stats(user_id: str) -> dict:
    """Return per-sport played/won counts for a user."""
    result = {}
    for sport in SPORT_ATTR_KEYS:
        _, _, st = _sport_tables(sport)
        try:
            con = _con()
            played = con.execute(
                f"SELECT COUNT(*) FROM {st} WHERE user_id=? AND completed=1", (user_id,)
            ).fetchone()[0]
            won = con.execute(
                f"SELECT COUNT(*) FROM {st} WHERE user_id=? AND won=1 AND completed=1", (user_id,)
            ).fetchone()[0]
            con.close()
            result[sport] = {"played": played, "won": won}
        except Exception as exc:
            print(f"[ERROR] get_user_sport_stats({user_id}, {sport}): {exc}")
            result[sport] = {"played": 0, "won": 0}
    return result


def update_user_stats(user_id: str, guess_count: int, won: bool) -> None:
    stats = get_or_create_user_stats(user_id)
    dist = stats["distribution"]
    key = str(guess_count) if won else "fail"
    dist[key] = dist.get(key, 0) + 1

    new_streak = (stats["current_streak"] + 1) if won else 0
    new_max = max(stats["max_streak"], new_streak)
    new_played = stats["total_played"] + 1
    new_won = stats["total_won"] + (1 if won else 0)

    try:
        con = _con()
        con.execute(
            """UPDATE user_stats SET
                current_streak=?, max_streak=?, total_played=?, total_won=?,
                distribution_json=?
               WHERE user_id=?""",
            (new_streak, new_max, new_played, new_won, json.dumps(dist), user_id),
        )
        con.commit()
        con.close()
    except Exception as exc:
        print(f"[ERROR] update_user_stats({user_id}): {exc}")
