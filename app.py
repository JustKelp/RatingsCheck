"""
Rebuildle — Daily multi-sport ratings guessing game.

Single-file Flask app. Game logic on the backend, HTML/CSS/JS served as
a single index page. Session-based state keyed by Flask cookie.

Run locally:
    pip install flask beautifulsoup4 requests rapidfuzz
    python app.py
    open http://localhost:5050
"""

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, session, Response, render_template
from datetime import date
import hashlib
import hmac as _hmac
import logging
import os
import secrets
import sqlite3
import time
from werkzeug.security import check_password_hash

from models import (
    ATTR_KEYS, NBA_ATTR_KEYS, NHL_ATTR_KEYS, MADDEN_ATTR_KEYS, MLB_ATTR_KEYS,
    SPORT_ATTR_KEYS, VALID_SPORTS, DB_PATH, _sport_tables,
    apply_override, get_all_players, get_past_puzzles, get_player_by_id,
    get_today_puzzle_db, get_upcoming_puzzles, get_or_create_user_stats,
    init_db, migrate_db, save_daily_puzzle, update_user_stats, upsert_player,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("RATINGSCHECK_SECRET", secrets.token_hex(16))

if not os.environ.get("RATINGSCHECK_SECRET"):
    log.warning(
        "RATINGSCHECK_SECRET not set — generated random key. "
        "Sessions will not survive restart. Set it in production."
    )

_cookie_domain = os.environ.get("SESSION_COOKIE_DOMAIN")
if _cookie_domain:
    app.config["SESSION_COOKIE_DOMAIN"] = _cookie_domain
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_HTTPONLY"] = True

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "").strip().lower()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

STATCHECK_USERS_DB = os.environ.get("STATCHECK_USERS_DB", "").replace("\\", "/")
_statcheck_db_available = False

# ── AUTH ──────────────────────────────────────────────────────────────────────
_TOKEN_LIFETIME = 86400 * 30


def _make_token(user_id: str, username: str) -> str:
    expiry = int(time.time()) + _TOKEN_LIFETIME
    payload = f"{user_id}:{username}:{expiry}"
    sig = _hmac.new(
        app.secret_key.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload}:{sig}"


def _verify_token(token: str) -> dict | None:
    if not token or not isinstance(token, str):
        return None
    parts = token.split(":")
    if len(parts) != 4:
        return None
    user_id, username, expiry_str, sig = parts
    try:
        expiry = int(expiry_str)
    except ValueError:
        return None
    if expiry < int(time.time()):
        return None
    expected_payload = f"{user_id}:{username}:{expiry_str}"
    expected_sig = _hmac.new(
        app.secret_key.encode(), expected_payload.encode(), hashlib.sha256
    ).hexdigest()
    if not _hmac.compare_digest(expected_sig, sig):
        return None
    return {"user_id": user_id, "username": username}


def _require_auth() -> dict | None:
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif request.is_json:
        token = (request.get_json(silent=True) or {}).get("auth_token")
    return _verify_token(token) if token else None


def _require_admin() -> dict | None:
    if not ADMIN_USERNAME:
        log.error("ADMIN_USERNAME env var not set — admin endpoints locked.")
        return None
    sess_username = session.get("username", "")
    if sess_username and sess_username.lower() == ADMIN_USERNAME:
        return {"user_id": session.get("user_id", ""), "username": sess_username}
    claims = _require_auth()
    if not claims:
        return None
    if claims["username"].lower() != ADMIN_USERNAME:
        return None
    return claims


# ── STATCHECK SSO ─────────────────────────────────────────────────────────────

def _check_statcheck_db() -> None:
    global _statcheck_db_available
    if not STATCHECK_USERS_DB:
        log.warning("STATCHECK_USERS_DB not set — StatCheck login unavailable.")
        return
    try:
        con = sqlite3.connect(f"file:{STATCHECK_USERS_DB}?mode=ro", uri=True)
        con.execute("SELECT 1 FROM users LIMIT 1")
        con.close()
        _statcheck_db_available = True
        log.info("StatCheck users.db connected: %s", STATCHECK_USERS_DB)
    except Exception as exc:
        log.warning("StatCheck users.db unavailable — login disabled: %s", exc)


def _get_statcheck_user(username: str) -> dict | None:
    if not _statcheck_db_available or not STATCHECK_USERS_DB:
        return None
    try:
        con = sqlite3.connect(f"file:{STATCHECK_USERS_DB}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT id, username, password_hash FROM users WHERE username=? COLLATE NOCASE",
            (username.strip(),),
        ).fetchone()
        con.close()
        return dict(row) if row else None
    except Exception as exc:
        log.error("_get_statcheck_user(%s): %s", username, exc)
        return None


# =============================================================================
# SPORT CONFIG
# =============================================================================

SPORT_NAMES = {
    "nba":    "NBA 2K",
    "nhl":    "NHL 26",
    "madden": "Madden 26",
    "mlb":    "MLB The Show 26",
}

NBA_ATTR_LABELS = {
    "closeShot": "Close Shot", "freeThrow": "Free Throw", "three": "3-Point",
    "midRange": "Mid Range", "shotIQ": "Shot IQ", "offConsistency": "Off Consistency",
    "layup": "Layup", "drivingDunk": "Driving Dunk", "standingDunk": "Standing Dunk",
    "postHook": "Post Hook", "postFade": "Post Fade", "postControl": "Post Control",
    "speed": "Speed", "agility": "Agility", "vertical": "Vertical",
    "strength": "Strength", "hustle": "Hustle", "stamina": "Stamina",
    "drawFoul": "Draw Foul", "hands": "Hands",
    "ballHandle": "Ball Handle", "speedWithBall": "Speed W/ Ball",
    "passAcc": "Pass Accuracy", "passVision": "Pass Vision", "passIQ": "Pass IQ",
    "block": "Block", "steal": "Steal", "interiorD": "Interior D",
    "perimeterD": "Perimeter D", "defConsistency": "Def Consistency",
    "helpDefIQ": "Help Def IQ", "passPerception": "Pass Perception",
    "defRebound": "Def Rebound", "offRebound": "Off Rebound",
    "durability": "Durability", "intangibles": "Intangibles",
}

NHL_ATTR_LABELS = {
    "speed": "Speed", "acceleration": "Acceleration", "agility": "Agility",
    "balance": "Balance", "endurance": "Endurance", "strength": "Strength",
    "slapShotPow": "Slap Shot Pwr", "slapShotAcc": "Slap Shot Acc",
    "wristShotPow": "Wrist Shot Pwr", "wristShotAcc": "Wrist Shot Acc",
    "passAcc": "Pass Accuracy", "puckControl": "Puck Control",
    "handEye": "Hand Eye", "deking": "Deking",
    "offAwareness": "Off Awareness", "defAwareness": "Def Awareness",
    "bodyChecking": "Body Checking", "shotBlocking": "Shot Blocking",
    "stickChecking": "Stick Checking",
    "faceoffs": "Faceoffs", "durability": "Durability",
    "fighting": "Fighting", "discipline": "Discipline",
    "aggression": "Aggression", "toughness": "Toughness", "poise": "Poise",
    "gBreakaway": "G: Breakaway", "gAggressiveness": "G: Aggress.",
    "gAngles": "G: Angles", "gCrease": "G: Crease",
    "gDefAwareness": "G: Def Aware", "gDexterity": "G: Dexterity",
    "gDurability": "G: Durability", "gReboundControl": "G: Rebound",
    "gPokeCheck": "G: Poke Check", "gReflexes": "G: Reflexes",
    "gRecovery": "G: Recovery", "gVision": "G: Vision",
}

MADDEN_ATTR_LABELS = {
    "awareness": "Awareness", "speed": "Speed", "acceleration": "Acceleration",
    "agility": "Agility", "jumping": "Jumping", "stamina": "Stamina",
    "strength": "Strength", "toughness": "Toughness", "injury": "Injury",
    "throwPower": "Throw Power", "throwAccShort": "Throw Acc (S)",
    "throwAccMed": "Throw Acc (M)", "throwAccDeep": "Throw Acc (D)",
    "throwAccOnRun": "Throw On Run", "throwUnderPressure": "Throw Pressure",
    "playAction": "Play Action", "breakSack": "Break Sack",
    "trucking": "Trucking", "breakTackle": "Break Tackle",
    "bcVision": "BC Vision", "carrying": "Carrying",
    "stiffArm": "Stiff Arm", "spinMove": "Spin Move",
    "jukeMoves": "Juke Move", "changeDir": "Change Dir",
    "catching": "Catching", "specCatch": "Spec Catch",
    "shortRoute": "Short Route", "medRoute": "Med Route",
    "deepRoute": "Deep Route", "release": "Release", "cit": "Catch Traffic",
    "runBlock": "Run Block", "passBlock": "Pass Block",
    "runBlockPow": "RB Power", "runBlockFin": "RB Finesse",
    "passBlockPow": "PB Power", "passBlockFin": "PB Finesse",
    "impactBlock": "Impact Block", "leadBlock": "Lead Block",
    "tackle": "Tackle", "hitPower": "Hit Power",
    "pursuit": "Pursuit", "playRecog": "Play Recog",
    "manCoverage": "Man Coverage", "zoneCoverage": "Zone Coverage",
    "pressing": "Press", "blockShed": "Block Shed",
    "finesseMoves": "Finesse Moves", "powerMoves": "Power Moves",
    "kickPower": "Kick Power", "kickAcc": "Kick Accuracy", "kickReturn": "Kick Return",
}

MLB_ATTR_LABELS = {
    "contactLeft": "Contact L", "contactRight": "Contact R",
    "powerLeft": "Power L", "powerRight": "Power R",
    "plateVision": "Plate Vision", "plateDiscipline": "Plate Disc.", "battingClutch": "Clutch",
    "speed": "Speed", "baserunningAbility": "Base Running", "baserunningAggr": "BR Aggr.",
    "armStrength": "Arm Strength", "armAccuracy": "Arm Accuracy",
    "fieldingAbility": "Fielding", "blocking": "Blocking",
    "stamina": "Stamina", "pitchingClutch": "Pitch Clutch",
    "bbPerBf": "BB/BF", "hrPerBf": "HR/BF",
    "pitchControl": "Control", "pitchVelocity": "Velocity", "pitchMovement": "Movement",
    "buntingAbility": "Bunting", "dragBuntAbility": "Drag Bunt",
    "hittingDurability": "Durability",
}

# Backward compat alias (admin template uses ATTR_LABELS)
ATTR_LABELS = NBA_ATTR_LABELS

SPORT_ATTR_LABELS = {
    "nba": NBA_ATTR_LABELS,
    "nhl": NHL_ATTR_LABELS,
    "madden": MADDEN_ATTR_LABELS,
    "mlb": MLB_ATTR_LABELS,
}

SPORT_DEFAULT_REVEAL_ORDERS = {
    "nba": ["three", "drivingDunk", "speed", "passAcc", "interiorD", "defRebound", "ballHandle", "steal"],
    "nhl": ["speed", "wristShotPow", "defAwareness", "bodyChecking", "faceoffs", "puckControl", "slapShotPow", "shotBlocking"],
    "madden": ["speed", "awareness", "throwPower", "catching", "tackle", "manCoverage", "strength", "acceleration"],
    "mlb": ["speed", "contactRight", "powerRight", "fieldingAbility", "armStrength", "pitchVelocity", "pitchControl", "battingClutch"],
}

# Backward compat alias
DEFAULT_REVEAL_ORDER = SPORT_DEFAULT_REVEAL_ORDERS["nba"]

BOARD_SIZE = 8
MAX_GUESSES = 5
INITIAL_REVEALED = 3


# =============================================================================
# PLAYER CACHE — one list per sport, refreshed at startup and after scrape
# =============================================================================

_DEMO_PLAYERS_NBA = [
    {"name": "Anthony Edwards", "team": "MIN", "position": "SG",
     "speed": 92, "three": 80, "drivingDunk": 95, "midRange": 78, "layup": 88,
     "interiorD": 65, "perimeterD": 80, "defRebound": 55, "passAcc": 72, "strength": 80, "overall": 95},
    {"name": "Stephen Curry", "team": "GSW", "position": "PG",
     "speed": 88, "three": 99, "drivingDunk": 50, "midRange": 92, "layup": 80,
     "interiorD": 50, "perimeterD": 75, "defRebound": 50, "passAcc": 88, "strength": 60, "overall": 96},
    {"name": "Nikola Jokic", "team": "DEN", "position": "C",
     "speed": 60, "three": 75, "drivingDunk": 70, "midRange": 85, "layup": 88,
     "interiorD": 88, "perimeterD": 70, "defRebound": 95, "passAcc": 98, "strength": 90, "overall": 98},
    {"name": "Victor Wembanyama", "team": "SAS", "position": "C",
     "speed": 78, "three": 78, "drivingDunk": 90, "midRange": 82, "layup": 85,
     "interiorD": 92, "perimeterD": 85, "defRebound": 88, "passAcc": 72, "strength": 75, "overall": 97},
    {"name": "Luka Doncic", "team": "LAL", "position": "PG",
     "speed": 78, "three": 84, "drivingDunk": 75, "midRange": 90, "layup": 88,
     "interiorD": 65, "perimeterD": 72, "defRebound": 78, "passAcc": 92, "strength": 85, "overall": 96},
]

_players_cache: dict[str, list[dict]] = {"nba": [], "nhl": [], "madden": [], "mlb": []}


def _load_players(sport: str | None = None) -> None:
    """Reload player cache from DB for one sport or all sports."""
    global _players_cache
    sports = [sport] if sport else list(SPORT_ATTR_KEYS.keys())
    for s in sports:
        attr_keys = SPORT_ATTR_KEYS[s]
        db_rows = get_all_players(s)
        if db_rows:
            _players_cache[s] = [
                {**row, "pos": row.get("position", "")} for row in db_rows
            ]
            log.info("Loaded %d %s players from DB.", len(_players_cache[s]), s.upper())
        elif s == "nba":
            defaults = {k: 0 for k in attr_keys}
            _players_cache["nba"] = [
                {**defaults, **p, "pos": p.get("position", p.get("pos", ""))}
                for p in _DEMO_PLAYERS_NBA
            ]
            log.warning("NBA DB empty — using %d demo players.", len(_players_cache["nba"]))
        else:
            _players_cache[s] = []
            log.info("%s: no players in DB yet.", s.upper())


def _get_players(sport: str) -> list[dict]:
    return _players_cache.get(sport, [])


# =============================================================================
# GAME LOGIC
# =============================================================================

def _parse_sport() -> str:
    """Extract and validate sport from request args or JSON body."""
    sport = (request.args.get("sport") or
             (request.get_json(silent=True) or {}).get("sport") or "nba")
    return sport if sport in VALID_SPORTS else "nba"


def get_today_puzzle(sport: str = "nba") -> dict:
    today = date.today().isoformat()
    db_puzzle = get_today_puzzle_db(today, sport)
    if db_puzzle:
        return db_puzzle
    players = _get_players(sport)
    if not players:
        return {"target": "", "revealOrder": SPORT_DEFAULT_REVEAL_ORDERS[sport]}
    seed = int(hashlib.md5(f"{today}_{sport}".encode()).hexdigest(), 16)
    target = players[seed % len(players)]
    return {"target": target["name"], "revealOrder": SPORT_DEFAULT_REVEAL_ORDERS[sport]}


def fresh_state():
    return {
        "date": date.today().isoformat(),
        "revealed": INITIAL_REVEALED,
        "guesses": [],
        "done": False,
        "won": False,
    }


def get_state(sport: str = "nba") -> dict:
    today = date.today().isoformat()
    key = f"game_{sport}"
    # Backward compat: migrate legacy "game" key to "game_nba"
    if sport == "nba" and "game" in session and key not in session:
        session[key] = session.pop("game")
    if key not in session or session[key].get("date") != today:
        session[key] = fresh_state()
    return session[key]


def find_player(name: str, sport: str = "nba") -> dict | None:
    if not name:
        return None
    nl = name.lower().strip()
    for p in _get_players(sport):
        if p["name"].lower() == nl:
            return p
    return None


def serialize_state(sport: str = "nba") -> dict:
    state = get_state(sport)
    puzzle = get_today_puzzle(sport)
    target = find_player(puzzle["target"], sport)
    attr_keys = SPORT_ATTR_KEYS[sport]
    attr_labels = SPORT_ATTR_LABELS[sport]
    revealed_attrs = puzzle["revealOrder"][:state["revealed"]]
    revealed_values = {a: (target.get(a, 0) if target else 0) for a in revealed_attrs}

    guesses_out = []
    for g in state["guesses"]:
        if isinstance(g, dict) and all(k in g for k in attr_keys):
            guesses_out.append(g)
        else:
            player = find_player(g if isinstance(g, str) else g.get("name", ""), sport)
            if player:
                entry = {k: player.get(k, 0) for k in attr_keys}
                entry["name"] = player["name"]
                entry["pos"] = player.get("pos", player.get("position", ""))
                entry["team"] = player.get("team", "")
                guesses_out.append(entry)

    return {
        "date": state["date"],
        "sport": sport,
        "maxGuesses": MAX_GUESSES,
        "guesses": guesses_out,
        "done": state["done"],
        "won": state["won"],
        "revealedAttrs": revealed_attrs,
        "revealedValues": revealed_values,
        "attrLabels": attr_labels,
        "answer": target if state["done"] else None,
    }


# =============================================================================
# ROUTES
# =============================================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    sport = _parse_sport()
    return jsonify(serialize_state(sport))


@app.route("/api/players")
def api_players():
    sport = _parse_sport()
    return jsonify([
        {"name": p["name"], "team": p["team"], "pos": p.get("pos", p.get("position", ""))}
        for p in _get_players(sport)
    ])


@app.route("/api/me")
def api_me():
    user_id = session.get("user_id")
    username = session.get("username")
    if user_id and username:
        is_admin = bool(ADMIN_USERNAME and username.lower() == ADMIN_USERNAME.lower())
        return jsonify({"user_id": user_id, "username": username, "is_admin": is_admin})
    claims = _require_auth()
    if claims:
        is_admin = bool(ADMIN_USERNAME and claims["username"].lower() == ADMIN_USERNAME.lower())
        return jsonify({"user_id": claims["user_id"], "username": claims["username"], "is_admin": is_admin})
    return jsonify({"guest": True})


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if not username or not password:
        return jsonify({"error": "Username and password required."}), 400

    if (ADMIN_PASSWORD and ADMIN_USERNAME
            and username.lower() == ADMIN_USERNAME and password == ADMIN_PASSWORD):
        session["user_id"] = "0"
        session["username"] = username
        session.modified = True
        log.info("Login (admin fallback): %s", username)
        return jsonify({"ok": True, "user_id": "0", "username": username})

    if not _statcheck_db_available:
        return jsonify({"error": "Login temporarily unavailable."}), 503
    user = _get_statcheck_user(username)
    if not user:
        return jsonify({"error": "Invalid username or password."}), 401
    ph = user["password_hash"]
    if ph.startswith("pbkdf2:") or ph.startswith("scrypt:"):
        valid = check_password_hash(ph, password)
    else:
        valid = (ph == hashlib.sha256(password.encode()).hexdigest())
    if not valid:
        return jsonify({"error": "Invalid username or password."}), 401
    session["user_id"] = str(user["id"])
    session["username"] = user["username"]
    session.modified = True
    log.info("Login: %s", user["username"])
    return jsonify({"ok": True, "user_id": str(user["id"]), "username": user["username"]})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    username = session.pop("username", None)
    session.pop("user_id", None)
    session.modified = True
    if username:
        log.info("Logout: %s", username)
    return jsonify({"ok": True})


@app.route("/api/guess", methods=["POST"])
def api_guess():
    data = request.get_json(silent=True) or {}
    sport = data.get("sport", "nba") if data.get("sport") in VALID_SPORTS else "nba"
    name = data.get("name", "")
    state = get_state(sport)
    if state["done"]:
        return jsonify({"error": "game over"}), 400
    player = find_player(name, sport)
    if not player:
        return jsonify({"error": "unknown player"}), 400
    if any(g.get("name") == player["name"] for g in state["guesses"]):
        return jsonify({"error": "already guessed"}), 400

    puzzle = get_today_puzzle(sport)
    attr_keys = SPORT_ATTR_KEYS[sport]
    guess_entry = {k: player.get(k, 0) for k in attr_keys}
    guess_entry["name"] = player["name"]
    guess_entry["pos"]  = player.get("pos", player.get("position", ""))
    guess_entry["team"] = player.get("team", "")
    state["guesses"].append(guess_entry)

    if player["name"] == puzzle["target"]:
        state["won"] = True
        state["done"] = True
        state["revealed"] = len(puzzle["revealOrder"])
    else:
        state["revealed"] = min(len(puzzle["revealOrder"]), state["revealed"] + 1)
        if len(state["guesses"]) >= MAX_GUESSES:
            state["done"] = True
            state["revealed"] = len(puzzle["revealOrder"])

    session.modified = True
    return jsonify(serialize_state(sport))


@app.route("/api/past-puzzles")
def api_past_puzzles():
    from datetime import date as _date
    sport = _parse_sport()
    days = get_past_puzzles(30, sport)
    result = []
    for d in days:
        try:
            dt = _date.fromisoformat(d["date"])
            label = dt.strftime("%b") + " " + str(dt.day) + " — " + d["name"]
        except Exception:
            label = d["date"] + " — " + d.get("name", "")
        result.append({"date": d["date"], "label": label})
    return jsonify(result)


@app.route("/api/reset", methods=["POST"])
def api_reset():
    sport = _parse_sport()
    session[f"game_{sport}"] = fresh_state()
    return jsonify(serialize_state(sport))


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================

@app.route("/admin/scrape", methods=["POST"])
def admin_scrape():
    if not _require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json(silent=True) or {}
    sport = data.get("sport", "nba") if data.get("sport") in VALID_SPORTS else "nba"
    try:
        if sport == "nba":
            from scraper import scrape_all
        elif sport == "nhl":
            from scraper_nhl import scrape_all
        elif sport == "madden":
            from scraper_madden import import_players as scrape_all
        elif sport == "mlb":
            from scraper_mlb import scrape_all_pages as scrape_all
        result = scrape_all(dry_run=False)
        _load_players(sport)
        log.info("Admin scrape (%s) complete: %s", sport, result)
        return jsonify({"ok": True, "result": result, "players_loaded": len(_get_players(sport))})
    except Exception as exc:
        log.error("admin_scrape(%s) error: %s", sport, exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/admin/override", methods=["POST"])
def admin_override():
    if not _require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json(silent=True) or {}
    sport = data.get("sport", "nba") if data.get("sport") in VALID_SPORTS else "nba"
    player_id = data.get("player_id")
    attribute = data.get("attribute", "")
    value = data.get("value")
    if player_id is None or not attribute or value is None:
        return jsonify({"error": "player_id, attribute, and value are required"}), 400
    try:
        value = int(value)
    except (TypeError, ValueError):
        return jsonify({"error": "value must be an integer"}), 400
    ok = apply_override(int(player_id), attribute, value, sport)
    if not ok:
        return jsonify({"error": "player not found or invalid attribute"}), 404
    _load_players(sport)
    player = get_player_by_id(int(player_id), sport)
    return jsonify({"ok": True, "player": player})


# =============================================================================
# ADMIN UI
# =============================================================================

def _admin_403():
    return Response(
        "<h2 style='font-family:monospace;padding:40px;color:#C45C78'>"
        "403 Unauthorized — Admin only.</h2>",
        status=403, mimetype="text/html",
    )


def _admin_template(initial_tab: str, sport: str = "nba"):
    sport = sport if sport in VALID_SPORTS else "nba"
    attr_keys = SPORT_ATTR_KEYS[sport]
    attr_labels = SPORT_ATTR_LABELS[sport]
    return render_template(
        "admin.html",
        admin_username=ADMIN_USERNAME,
        attr_keys=attr_keys,
        attr_labels=attr_labels,
        initial_tab=initial_tab,
        sport=sport,
        sport_names=SPORT_NAMES,
    )


@app.route("/admin/curate")
def admin_curate():
    if not _require_admin():
        return _admin_403()
    sport = request.args.get("sport", "nba")
    return _admin_template("curate", sport)


@app.route("/admin/upcoming")
def admin_upcoming_page():
    if not _require_admin():
        return _admin_403()
    sport = request.args.get("sport", "nba")
    return _admin_template("upcoming", sport)


@app.route("/admin/stats")
def admin_stats_page():
    if not _require_admin():
        return _admin_403()
    sport = request.args.get("sport", "nba")
    return _admin_template("stats", sport)


@app.route("/admin/api/player-search")
def admin_api_player_search():
    if not _require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    sport = request.args.get("sport", "nba")
    if sport not in VALID_SPORTS:
        sport = "nba"
    q = request.args.get("q", "").strip().lower()
    if not q:
        return jsonify([])
    players = _get_players(sport)
    attr_keys = SPORT_ATTR_KEYS[sport]
    try:
        from rapidfuzz import process, fuzz
        names = [p["name"] for p in players]
        results = process.extract(q, names, scorer=fuzz.partial_ratio, limit=8, score_cutoff=40)
        matched_names = {r[0] for r in results}
        hits = [p for p in players if p["name"] in matched_names]
    except ImportError:
        hits = [p for p in players if q in p["name"].lower()][:8]
    out = []
    for p in hits[:8]:
        out.append({
            "id":       p.get("id", 0),
            "name":     p["name"],
            "team":     p.get("team", ""),
            "position": p.get("position", p.get("pos", "")),
            "overall":  p.get("overall", 0),
            "attrs":    {k: p.get(k, 0) for k in attr_keys},
        })
    return jsonify(out)


@app.route("/admin/api/narrowing")
def admin_api_narrowing():
    if not _require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    sport = request.args.get("sport", "nba")
    if sport not in VALID_SPORTS:
        sport = "nba"
    player_id = request.args.get("player_id", type=int)
    attrs_str  = request.args.get("attrs", "")
    if not player_id or not attrs_str:
        return jsonify({"error": "player_id and attrs required"}), 400
    valid_keys = set(SPORT_ATTR_KEYS[sport])
    attrs  = [a.strip() for a in attrs_str.split(",") if a.strip() in valid_keys]
    target = get_player_by_id(player_id, sport)
    if not target:
        return jsonify({"error": "player not found"}), 404
    players = _get_players(sport)
    count = sum(
        1 for p in players
        if p.get("id") != player_id
        and all(abs(p.get(a, 0) - target.get(a, 0)) <= 5 for a in attrs)
    )
    return jsonify({"count": count})


@app.route("/admin/api/upcoming")
def admin_api_upcoming():
    if not _require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    sport = request.args.get("sport", "nba")
    if sport not in VALID_SPORTS:
        sport = "nba"
    rows = get_upcoming_puzzles(days=14, sport=sport)
    return jsonify(rows)


@app.route("/admin/api/stats")
def admin_api_stats():
    if not _require_admin():
        return jsonify({"error": "Unauthorized"}), 403
    sport = request.args.get("sport", "nba")
    if sport not in VALID_SPORTS:
        sport = "nba"
    today_str = date.today().isoformat()
    pt, dt, st = _sport_tables(sport)
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row

        today_all    = con.execute(f"SELECT COUNT(*) FROM {st} WHERE date=?", (today_str,)).fetchone()[0]
        today_done   = con.execute(f"SELECT COUNT(*) FROM {st} WHERE date=? AND completed=1", (today_str,)).fetchone()[0]
        today_active = today_all - today_done
        today_won    = con.execute(f"SELECT COUNT(*) FROM {st} WHERE date=? AND won=1 AND completed=1", (today_str,)).fetchone()[0]

        puzzle_row = con.execute(
            f"SELECT p.name FROM {dt} dp JOIN {pt} p ON p.id=dp.player_id WHERE dp.date=?",
            (today_str,),
        ).fetchone()
        today_puzzle = puzzle_row["name"] if puzzle_row else "No puzzle scheduled"

        total_completed = con.execute(f"SELECT COUNT(*) FROM {st} WHERE completed=1").fetchone()[0]
        total_won       = con.execute(f"SELECT COUNT(*) FROM {st} WHERE won=1 AND completed=1").fetchone()[0]
        unique_players  = con.execute(
            f"SELECT COUNT(DISTINCT COALESCE(user_id, guest_uuid)) FROM {st}"
        ).fetchone()[0]
        recent_7d = con.execute(
            f"SELECT COUNT(*) FROM {st} WHERE date >= date('now','-7 days') AND completed=1"
        ).fetchone()[0]
        con.close()
    except Exception as exc:
        log.error("admin_api_stats(%s): %s", sport, exc)
        return jsonify({"error": "DB error"}), 500

    return jsonify({
        "ok": True,
        "today": {
            "date": today_str, "puzzle": today_puzzle,
            "in_progress": today_active, "completed": today_done,
            "won": today_won,
            "win_rate": round(today_won / today_done * 100, 1) if today_done else 0,
        },
        "all_time": {
            "total_completed": total_completed, "total_won": total_won,
            "win_rate": round(total_won / total_completed * 100, 1) if total_completed else 0,
            "unique_players": unique_players, "recent_7d": recent_7d,
        },
    })


@app.route("/admin/save-puzzle", methods=["POST"])
def admin_save_puzzle():
    claims = _require_admin()
    if not claims:
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json(silent=True) or {}
    sport = data.get("sport", "nba") if data.get("sport") in VALID_SPORTS else "nba"
    player_id    = data.get("player_id")
    date_str     = data.get("date", "")
    reveal_order = data.get("reveal_order", [])
    if not player_id or not date_str or not reveal_order:
        return jsonify({"error": "player_id, date, and reveal_order required"}), 400
    try:
        date.fromisoformat(date_str)
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    valid_keys = set(SPORT_ATTR_KEYS[sport])
    if (len(reveal_order) != BOARD_SIZE
            or len(set(reveal_order)) != BOARD_SIZE
            or not all(k in valid_keys for k in reveal_order)):
        return jsonify({"error": f"reveal_order must contain exactly {BOARD_SIZE} unique valid attribute keys"}), 400
    ok = save_daily_puzzle(date_str, int(player_id), reveal_order,
                           created_by=claims.get("username", ""), sport=sport)
    if not ok:
        return jsonify({"error": "DB write failed"}), 500
    log.info("Admin saved puzzle: sport=%s player_id=%s date=%s by=%s",
             sport, player_id, date_str, claims.get("username"))
    return jsonify({"ok": True})


# =============================================================================
# STARTUP
# =============================================================================

init_db()
migrate_db()
_load_players()
_check_statcheck_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
