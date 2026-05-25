"""
gen_reveals.py — Generate z-score-based reveal orders for NHL, MLB, and NBA puzzle seed files.

Algorithm: same as gen_madden_reveals.py
  Slots 1-3: near-average attributes (low |z|, generic)
  Slots 4-6: moderately distinctive
  Slots 7-8: highest |z| (signature stats)

Usage:
  py -3 gen_reveals.py nhl
  py -3 gen_reveals.py mlb
  py -3 gen_reveals.py nba
  py -3 gen_reveals.py all
"""

import sqlite3, os, statistics, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = os.environ.get("RATINGSCHECK_DB", "ratingscheck.db")
MIN_STD = 1.0


# ════════════════════════════════════════════════════════════════════════════
# NHL
# ════════════════════════════════════════════════════════════════════════════

NHL_TABLE = "players_nhl"

def nhl_group(pos):
    """Map any NHL position string to 'forward', 'defense', or None (goalie/empty)."""
    pos = (pos or "").strip()
    if not pos or pos == "G":
        return None
    primary = pos.split("/")[0].strip()
    if primary in ("D", "LD", "RD"):
        return "defense"
    return "forward"

NHL_GROUP_ATTRS = {
    "forward": [
        "speed", "acceleration", "agility", "strength",
        "wristShotPow", "wristShotAcc", "slapShotPow", "slapShotAcc",
        "passAcc", "puckControl", "deking", "handEye",
        "offAwareness", "defAwareness",
        "faceoffs", "stickChecking", "bodyChecking", "fighting",
    ],
    "defense": [
        "speed", "acceleration", "agility", "strength",
        "defAwareness", "offAwareness",
        "bodyChecking", "stickChecking", "shotBlocking",
        "slapShotPow", "wristShotPow",
        "passAcc", "puckControl", "deking",
        "fighting",
    ],
}

# IDs from seed_puzzles_nhl.py (order preserved)
NHL_PUZZLE_IDS = [
    278, 173, 279, 716,
    174, 307, 365,
    32, 366, 607, 746, 834,
    226, 308, 309, 449,
    57, 198, 337, 428, 718, 719, 747, 835, 897,
    227, 450, 898,
    123, 124, 175, 400, 507, 525, 535, 720, 775, 868, 899,
    33, 58, 94, 176, 199, 229, 230, 255, 256, 311, 312, 368, 429, 451, 508, 536, 537, 692, 721, 836, 837, 838, 869,
    1, 125, 126, 147, 231, 257, 258,
]


# ════════════════════════════════════════════════════════════════════════════
# MLB
# ════════════════════════════════════════════════════════════════════════════

MLB_TABLE = "players_mlb"

def mlb_group(pos):
    """Map MLB position to 'pitcher', 'catcher', or 'hitter'."""
    if pos in ("SP", "RP", "CP"):
        return "pitcher"
    if pos == "C":
        return "catcher"
    return "hitter"

MLB_GROUP_ATTRS = {
    # Pitchers: stamina separates SP from RP/CP naturally
    "pitcher": [
        "speed", "fieldingAbility",
        "stamina", "pitchingClutch", "bbPerBf", "hrPerBf",
        "pitchControl", "pitchVelocity", "pitchMovement",
    ],
    # Catchers have blocking which is a distinctive extra
    "catcher": [
        "speed", "armStrength", "armAccuracy", "fieldingAbility", "blocking",
        "plateVision", "plateDiscipline", "battingClutch",
        "contactLeft", "contactRight", "powerLeft", "powerRight",
    ],
    "hitter": [
        "speed", "armStrength", "armAccuracy", "fieldingAbility",
        "plateVision", "plateDiscipline", "battingClutch",
        "contactLeft", "contactRight", "powerLeft", "powerRight",
    ],
}

# IDs from seed_puzzles_mlb.py (order preserved)
MLB_PUZZLE_IDS = [
    # Hitters
    39, 1403, 1874, 668, 1059, 1096,
    272, 615, 831, 2001, 1145, 1801, 1037, 1303, 1652, 521, 1460, 50, 461,
    9, 190, 511, 674, 716, 950, 954, 1302, 1346, 1399, 1840, 1934, 1935,
    324, 412, 574, 717, 1043, 1697, 1985, 1,
    # Pitchers
    660,
    128, 383, 454, 1653, 1747, 5, 111,
    185, 307, 360, 856, 1160, 1364, 1893,
    268, 342, 659, 1152, 1575,
    258, 779, 840, 940, 1326, 1569, 1640, 1709, 1712,
]


# ════════════════════════════════════════════════════════════════════════════
# NBA
# ════════════════════════════════════════════════════════════════════════════

NBA_TABLE = "players"

def nba_group(pos):
    if pos in ("PG", "SG"):
        return "guard"
    if pos in ("SF", "PF"):
        return "forward"
    if pos == "C":
        return "center"
    return None

NBA_GROUP_ATTRS = {
    "guard": [
        "speed", "agility", "speedWithBall", "ballHandle",
        "passAcc", "passVision", "passIQ",
        "three", "midRange", "drivingDunk", "layup", "closeShot",
        "perimeterD", "steal", "drawFoul",
    ],
    "forward": [
        "speed", "agility", "strength",
        "three", "midRange", "drivingDunk", "layup",
        "postHook", "postFade",
        "interiorD", "perimeterD", "steal", "block", "defRebound",
    ],
    "center": [
        "strength", "agility",
        "standingDunk", "drivingDunk", "layup",
        "postHook", "postFade", "postControl",
        "interiorD", "defRebound", "block", "speed",
    ],
}

# IDs from players table — top players per position (adjust as needed)
# If no NBA seed file exists yet, this still prints out a ready-to-use block.
NBA_PUZZLE_IDS: list[int] = []  # empty until you add a seed file


# ════════════════════════════════════════════════════════════════════════════
# Core algorithm
# ════════════════════════════════════════════════════════════════════════════

def load_table(conn, table):
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]
    return {row[0]: dict(zip(cols, row)) for row in cur.fetchall()}


def group_stats(players, group_name, attrs, group_fn):
    """Mean and std per attr, using only non-zero values from players in this group."""
    peers = [p for p in players.values() if group_fn(p.get("position", "")) == group_name]
    means, stds = {}, {}
    for attr in attrs:
        vals = [p.get(attr) or 0 for p in peers]
        nonzero = [v for v in vals if v > 0]
        if not nonzero:
            means[attr] = 0; stds[attr] = MIN_STD; continue
        m = statistics.mean(nonzero)
        s = statistics.stdev(nonzero) if len(nonzero) > 1 else MIN_STD
        means[attr] = m
        stds[attr] = max(s, MIN_STD)
    return means, stds


def build_reveal(player, group_name, group_attrs, group_fn, all_players,
                 min_val=0, no_min_attrs=frozenset()):
    """
    Build an 8-slot reveal order sorted low→high |z|.
    Attributes whose value is below min_val are excluded unless the attr is in
    no_min_attrs (useful for rate stats and deliberately low values like stamina
    for closers).  If fewer than 6 attrs survive the filter, fall back to
    all non-zero values so we always fill 8 slots.
    """
    attrs = group_attrs[group_name]
    means, stds = group_stats(all_players, group_name, attrs, group_fn)

    def score_attrs(candidates, apply_min):
        out = []
        for attr in candidates:
            val = player.get(attr) or 0
            if val == 0:
                continue
            if apply_min and attr not in no_min_attrs and val < min_val:
                continue
            z = abs((val - means[attr]) / stds[attr])
            out.append((attr, z))
        return out

    scored = score_attrs(attrs, apply_min=True)
    if len(scored) < 6:                          # fallback: relax threshold
        scored = score_attrs(attrs, apply_min=False)

    scored.sort(key=lambda x: x[1])
    n = len(scored)

    low  = scored[: max(1, n // 3)]
    mid  = scored[max(1, n // 3): max(2, 2 * n // 3)]
    high = scored[max(2, 2 * n // 3):]

    reveal = []
    for bucket, target in [(low, 3), (mid, 2), (high, 3)]:
        reveal.extend(a for a, _ in bucket[:target])

    extras = [a for a, _ in scored if a not in reveal]
    while len(reveal) < 8 and extras:
        reveal.append(extras.pop(0))
    reveal = reveal[:8]

    most_distinctive = scored[-1][0] if scored else attrs[-1]
    if most_distinctive in reveal:
        reveal.remove(most_distinctive)
        reveal.append(most_distinctive)
    elif len(reveal) == 8:
        reveal[-1] = most_distinctive

    return reveal


def generate(sport, table, puzzle_ids, group_fn, group_attrs, all_players,
             min_val=0, no_min_attrs=frozenset(),
             group_min_val=None, group_no_min_attrs=None,
             show_diagnostic=True):
    """
    group_min_val / group_no_min_attrs: per-group overrides (dict keyed by group name).
    Falls back to the flat min_val / no_min_attrs for groups not listed.
    """
    print(f"\n\n# {'═'*60}")
    print(f"# {sport.upper()} PLAYER_REVEALS")
    print(f"# {'═'*60}")
    print("PLAYER_REVEALS = [")

    missing = []
    results = []

    for pid in puzzle_ids:
        p = all_players.get(pid)
        if not p:
            missing.append(pid)
            continue
        pos = p.get("position", "")
        group = group_fn(pos)
        if not group or group not in group_attrs:
            print(f"    # WARNING: player_id={pid} '{p.get('name')}' pos='{pos}' — no group, skipped")
            continue

        gmv  = (group_min_val  or {}).get(group, min_val)
        gnma = (group_no_min_attrs or {}).get(group, no_min_attrs)
        reveal = build_reveal(p, group, group_attrs, group_fn, all_players,
                              min_val=gmv, no_min_attrs=gnma)
        ovr = p.get("overall", "?")
        name = p.get("name", "?")
        team = p.get("team", "?")
        attr_str = ", ".join(f'"{a}"' for a in reveal)
        line = f'    ({pid}, [{attr_str}]),  # {name} {ovr} {pos} {team}'
        print(line)
        results.append((pid, p, group, reveal))

    print("]")
    print(f"\n# Total: {len(results)} players")

    if missing:
        print(f"\n# WARNING: {len(missing)} IDs not found in DB: {missing}")

    if show_diagnostic:
        print(f"\n# ── Diagnostic: reveal attrs with |z| ──")
        for pid, p, group, reveal in results:
            attrs = group_attrs[group]
            means, stds = group_stats(all_players, group, attrs, group_fn)
            zs = []
            for attr in reveal:
                val = p.get(attr) or 0
                z = abs((val - means[attr]) / stds[attr])
                zs.append(f"{attr}={val}(z={z:.2f})")
            name = p.get("name", "?")
            pos = p.get("position", "?")
            print(f"  {name:28s} {pos:6s}: {' -> '.join(zs)}")


def main():
    sports = sys.argv[1:] if len(sys.argv) > 1 else ["all"]
    if "all" in sports:
        sports = ["nhl", "mlb", "nba"]

    conn = sqlite3.connect(DB_PATH)

    for sport in sports:
        if sport == "nhl":
            players = load_table(conn, NHL_TABLE)
            generate("nhl", NHL_TABLE, NHL_PUZZLE_IDS, nhl_group, NHL_GROUP_ATTRS, players,
                     min_val=68)  # filters faceoffs=55 for D/wingers, fighting=63 for skill players
        elif sport == "mlb":
            players = load_table(conn, MLB_TABLE)
            generate("mlb", MLB_TABLE, MLB_PUZZLE_IDS, mlb_group, MLB_GROUP_ATTRS, players,
                     min_val=50,  # hitter/catcher default
                     group_min_val={"pitcher": 50},
                     group_no_min_attrs={
                         # stamina=25 for closers IS the clue; rate stats have no useful floor
                         "pitcher": {"bbPerBf", "hrPerBf", "stamina"},
                     })
        elif sport == "nba":
            if not NBA_PUZZLE_IDS:
                print("\n# NBA: no PUZZLE_IDS defined — add player IDs to NBA_PUZZLE_IDS in gen_reveals.py")
            else:
                players = load_table(conn, NBA_TABLE)
                generate("nba", NBA_TABLE, NBA_PUZZLE_IDS, nba_group, NBA_GROUP_ATTRS, players,
                         min_val=60)
        else:
            print(f"Unknown sport: {sport}. Use nhl, mlb, nba, or all.")

    conn.close()


if __name__ == "__main__":
    main()
