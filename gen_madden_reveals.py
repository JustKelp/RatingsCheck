"""
gen_madden_reveals.py — Generate data-driven reveal orders for Madden daily puzzles.

Algorithm per player:
  1. Build position-group peer set from all players_madden rows.
  2. Compute z-scores for every relevant attribute relative to peers.
  3. Reveal order:
       - Slots 1-3: lowest |z| (generic, don't give it away early)
       - Slots 4-6: medium |z| (increasingly distinctive)
       - Slots 7-8: highest |z| (signature / most unique)

Run:  py -3 gen_madden_reveals.py
Output: printed PLAYER_REVEALS block ready to paste into seed_puzzles_madden.py
"""

import sqlite3, os, statistics, textwrap, sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = os.environ.get("RATINGSCHECK_DB", "ratingscheck.db")

# ── Puzzle player IDs (same order as seed_puzzles_madden.py) ─────────────────
PUZZLE_IDS = [
    616, 618, 628, 643, 717, 734, 705,   # QB
    615, 617, 631, 636, 645, 655, 657, 660, 682, 695,  # WR
    621, 622, 639, 648, 668, 683, 691, 715, 718,  # HB
    623, 663, 675, 678, 694, 723, 731,   # TE
    620, 624, 632, 634, 642, 664, 667, 679,  # DE
    625, 626, 638, 646, 665, 671, 686,   # DT
    627, 653, 677, 688, 721, 726,        # LB
    629, 637, 640, 650, 651, 654, 658, 666, 669, 672,  # CB/S
    619, 630, 633, 635,  # OL
    728,  # K
]

# ── Position group definitions ───────────────────────────────────────────────
# Maps DB position value → peer group name used for z-score computation
POSITION_TO_GROUP = {
    "QB": "QB",
    "WR": "WR", "WR2": "WR",
    "HB": "HB", "FB": "HB",
    "TE": "TE",
    "LE": "DE", "RE": "DE", "DE": "DE",
    "DT": "DT", "NT": "DT",
    "MLB": "LB", "OLB": "LB", "LOLB": "LB", "ROLB": "LB", "LB": "LB",
    "CB": "CB_S", "SS": "CB_S", "FS": "CB_S",
    "LT": "OL", "RT": "OL", "LG": "OL", "RG": "OL", "C": "OL", "G": "OL", "T": "OL",
    "K": "K", "P": "K",
}

# Relevant attributes per group — only these are candidates for reveal slots
GROUP_ATTRS = {
    "QB": [
        "speed", "agility", "acceleration", "awareness",
        "throwPower", "throwAccShort", "throwAccMed", "throwAccDeep",
        "throwAccOnRun", "throwUnderPressure", "playAction", "breakSack",
    ],
    "WR": [
        "speed", "agility", "acceleration", "strength",
        "catching", "specCatch", "shortRoute", "medRoute", "deepRoute",
        "release", "cit",
    ],
    "HB": [
        "speed", "agility", "acceleration", "strength",
        "trucking", "breakTackle", "jukeMoves", "stiffArm",
        "carrying", "bcVision", "changeDir", "catching",
    ],
    "TE": [
        "speed", "agility", "acceleration", "strength",
        "catching", "shortRoute", "medRoute", "deepRoute",
        "release", "trucking", "blockShed", "runBlock",
    ],
    "DE": [
        "speed", "agility", "acceleration", "strength",
        "tackle", "hitPower", "pursuit",
        "blockShed", "finesseMoves", "powerMoves",
    ],
    "DT": [
        "speed", "agility", "strength",
        "tackle", "hitPower", "pursuit",
        "blockShed", "finesseMoves", "powerMoves",
    ],
    "LB": [
        "speed", "agility", "acceleration", "strength",
        "tackle", "hitPower", "pursuit", "playRecog",
        "manCoverage", "zoneCoverage", "awareness",
    ],
    "CB_S": [
        "speed", "agility", "acceleration", "strength",
        "tackle", "hitPower", "pursuit",
        "manCoverage", "zoneCoverage", "pressing", "awareness",
    ],
    "OL": [
        "speed", "agility", "strength",
        "runBlock", "passBlock",
        "runBlockPow", "runBlockFin",
        "passBlockPow", "passBlockFin", "impactBlock",
    ],
    "K": [
        "speed", "agility", "awareness", "stamina",
        "strength", "acceleration", "kickAcc", "kickPower",
    ],
}

# Minimum std to avoid division-by-zero on attributes where everyone is identical
MIN_STD = 1.0


def load_players(conn):
    cur = conn.cursor()
    cur.execute("SELECT * FROM players_madden")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    players = {}
    for row in rows:
        p = dict(zip(cols, row))
        players[p["id"]] = p
    return players


def group_stats(players, group_name, attrs):
    """Return (mean, std) dicts for each attr across all players in this group."""
    peers = [p for p in players.values()
             if POSITION_TO_GROUP.get(p["position"]) == group_name]
    means, stds = {}, {}
    for attr in attrs:
        vals = [p.get(attr) or 0 for p in peers]
        if not vals:
            means[attr] = 0; stds[attr] = MIN_STD; continue
        m = statistics.mean(vals)
        s = statistics.stdev(vals) if len(vals) > 1 else MIN_STD
        means[attr] = m
        stds[attr] = max(s, MIN_STD)
    return means, stds


def z_score(val, mean, std):
    return (val - mean) / std


def build_reveal(player, group_name, all_players):
    attrs = GROUP_ATTRS[group_name]
    means, stds = group_stats(all_players, group_name, attrs)

    # Only use attrs where the player has a non-zero value
    scored = []
    for attr in attrs:
        val = player.get(attr) or 0
        if val == 0:
            continue
        z = abs(z_score(val, means[attr], stds[attr]))
        scored.append((attr, z))

    # Sort by |z|
    scored.sort(key=lambda x: x[1])

    # Bucket: low (generic), mid, high (distinctive)
    n = len(scored)
    low = scored[: max(1, n // 3)]
    mid = scored[max(1, n // 3) : max(2, 2 * n // 3)]
    high = scored[max(2, 2 * n // 3) :]

    # Build 8-slot reveal: 3 from low, 2-3 from mid, 2-3 from high
    reveal = []
    for bucket, target in [(low, 3), (mid, 2), (high, 3)]:
        take = bucket[:target]
        # within each bucket, order by z ascending (less distinctive first within bucket)
        reveal.extend(a for a, _ in take)

    # Pad if under 8 or trim if over 8
    # Fill remaining slots from mid/high if needed
    extras = [a for a, _ in scored if a not in reveal]
    while len(reveal) < 8 and extras:
        reveal.append(extras.pop(0))
    reveal = reveal[:8]

    # Ensure the single most distinctive attr is last
    most_distinctive = scored[-1][0] if scored else attrs[-1]
    if most_distinctive in reveal:
        reveal.remove(most_distinctive)
        reveal.append(most_distinctive)
    elif len(reveal) == 8:
        reveal[-1] = most_distinctive

    return reveal


def main():
    conn = sqlite3.connect(DB_PATH)
    all_players = load_players(conn)
    conn.close()

    # Group names for labeling output comments
    GROUP_LABEL = {
        "QB": "QB", "WR": "WR", "HB": "HB", "TE": "TE",
        "DE": "DE", "DT": "DT", "LB": "LB", "CB_S": "CB/S",
        "OL": "OL", "K": "K",
    }

    lines = []
    current_group = None

    for pid in PUZZLE_IDS:
        p = all_players.get(pid)
        if not p:
            print(f"  WARNING: player_id={pid} not found in DB")
            continue

        pos = p["position"]
        group = POSITION_TO_GROUP.get(pos)
        if not group:
            print(f"  WARNING: unknown position '{pos}' for {p['name']}")
            continue

        if group != current_group:
            label = GROUP_LABEL.get(group, group)
            lines.append(f"    # ── {label}s ──")
            current_group = group

        reveal = build_reveal(p, group, all_players)
        ovr = p.get("overall", "?")
        name = p["name"]
        team = p["team"]
        comment = f"# {name} {ovr} {pos} {team}"

        attr_str = ", ".join(f'"{a}"' for a in reveal)
        lines.append(f'    ({pid}, [{attr_str}]),  {comment}')

    print("PLAYER_REVEALS = [")
    for l in lines:
        print(l)
    print("]")

    print(f"\n# Total: {len([l for l in lines if l.strip().startswith('(')])} players")

    # Also print a diagnostic: show z-scores for each player's reveal
    print("\n\n# ── Diagnostic: reveal attrs and |z| per player ──")
    for pid in PUZZLE_IDS:
        p = all_players.get(pid)
        if not p:
            continue
        pos = p["position"]
        group = POSITION_TO_GROUP.get(pos)
        if not group:
            continue
        attrs = GROUP_ATTRS[group]
        means, stds = group_stats(all_players, group, attrs)
        reveal = build_reveal(p, group, all_players)
        zs = []
        for attr in reveal:
            val = p.get(attr) or 0
            z = abs(z_score(val, means[attr], stds[attr]))
            zs.append(f"{attr}={val}(z={z:.2f})")
        print(f"  {p['name']:25s} {pos:4s}: {' -> '.join(zs)}")


if __name__ == "__main__":
    main()
