"""
seed_puzzles_madden.py — Insert Madden daily puzzles 2026-03-17 through 2026-05-24 (69 days).
Safe to re-run: uses INSERT OR REPLACE. Player order is randomized.

Reveal order philosophy:
  Positions 1-3: generic for position (agility, strength, acceleration)
  Positions 4-8: increasingly position-specific, ending on signature stat
    QB: ends on throwPower or throwAccShort
    WR: ends on catching or deepRoute
    HB: ends on jukeMoves or trucking
    TE: ends on catching
    DL: ends on finesseMoves or powerMoves
    LB: ends on tackle
    CB/S: ends on manCoverage or hitPower
    OL: ends on strength
"""

import sqlite3
import json
import os
import random

DB_PATH = os.environ.get("RATINGSCHECK_DB", "ratingscheck.db")

DATES = [
    "2026-03-17","2026-03-18","2026-03-19","2026-03-20","2026-03-21","2026-03-22","2026-03-23",
    "2026-03-24","2026-03-25","2026-03-26","2026-03-27","2026-03-28","2026-03-29","2026-03-30",
    "2026-03-31","2026-04-01","2026-04-02","2026-04-03","2026-04-04","2026-04-05","2026-04-06",
    "2026-04-07","2026-04-08","2026-04-09","2026-04-10","2026-04-11","2026-04-12","2026-04-13",
    "2026-04-14","2026-04-15","2026-04-16","2026-04-17","2026-04-18","2026-04-19","2026-04-20",
    "2026-04-21","2026-04-22","2026-04-23","2026-04-24","2026-04-25","2026-04-26","2026-04-27",
    "2026-04-28","2026-04-29","2026-04-30","2026-05-01","2026-05-02","2026-05-03","2026-05-04",
    "2026-05-05","2026-05-06","2026-05-07","2026-05-08","2026-05-09","2026-05-10","2026-05-11",
    "2026-05-12","2026-05-13","2026-05-14","2026-05-15","2026-05-16","2026-05-17","2026-05-18",
    "2026-05-19","2026-05-20","2026-05-21","2026-05-22","2026-05-23","2026-05-24",
]

# Exactly 69 players (5 QB, 10 WR, 7 HB, 5 TE, 8 DE, 7 DT, 4 LB, 10 CB/S, 13 OL)
PLAYER_REVEALS = [
    # ── QBs (5) ──
    (616, ["agility","acceleration","catching","throwAccDeep","throwAccMed","throwUnderPressure","throwAccShort","throwPower"]),   # Josh Allen 99
    (618, ["strength","agility","throwAccDeep","throwUnderPressure","throwAccMed","throwAccShort","throwPower","speed"]),          # Lamar Jackson 99
    (628, ["agility","acceleration","throwPower","throwAccDeep","throwUnderPressure","throwAccMed","awareness","throwAccShort"]),  # Joe Burrow 97
    (643, ["agility","acceleration","throwAccDeep","throwUnderPressure","throwAccMed","throwPower","speed","throwAccShort"]),      # Mahomes 95
    (705, ["agility","acceleration","catching","throwAccDeep","throwUnderPressure","throwAccMed","throwAccShort","throwPower"]),   # Stafford 89
    # ── WRs (10) ──
    (615, ["agility","strength","acceleration","catching","shortRoute","medRoute","release","deepRoute"]),                        # Ja'Marr Chase 99
    (617, ["strength","agility","acceleration","catching","shortRoute","release","deepRoute","medRoute"]),                        # Justin Jefferson 99
    (631, ["agility","strength","acceleration","shortRoute","medRoute","deepRoute","release","catching"]),                        # Amon-Ra 96
    (636, ["agility","strength","acceleration","shortRoute","medRoute","release","catching","deepRoute"]),                        # CeeDee Lamb 95
    (645, ["agility","strength","acceleration","shortRoute","medRoute","deepRoute","catching","speed"]),                          # Tyreek Hill 95
    (655, ["agility","strength","acceleration","shortRoute","medRoute","deepRoute","speed","catching"]),                          # Terry McLaurin 94
    (657, ["agility","acceleration","shortRoute","medRoute","deepRoute","release","trucking","catching"]),                        # A.J. Brown 93
    (660, ["agility","acceleration","strength","shortRoute","medRoute","deepRoute","release","catching"]),                        # Mike Evans 93
    (682, ["agility","acceleration","strength","shortRoute","medRoute","deepRoute","release","catching"]),                        # Drake London 91
    (695, ["agility","strength","acceleration","shortRoute","medRoute","deepRoute","release","catching"]),                        # Puka Nacua 90
    # ── HBs (7) ──
    (621, ["agility","strength","acceleration","trucking","breakTackle","carrying","speed","jukeMoves"]),                         # Saquon Barkley 99
    (622, ["agility","acceleration","jukeMoves","carrying","breakTackle","speed","stiffArm","trucking"]),                         # Derrick Henry 98
    (639, ["agility","strength","acceleration","trucking","breakTackle","carrying","speed","jukeMoves"]),                         # Jahmyr Gibbs 95
    (648, ["agility","acceleration","trucking","breakTackle","jukeMoves","catching","shortRoute","speed"]),                       # CMC 94
    (668, ["agility","strength","acceleration","trucking","breakTackle","carrying","speed","jukeMoves"]),                         # Bijan Robinson 92
    (683, ["agility","strength","acceleration","trucking","breakTackle","carrying","jukeMoves","speed"]),                         # Joe Mixon 91
    (691, ["agility","strength","acceleration","jukeMoves","carrying","breakTackle","speed","trucking"]),                         # Josh Jacobs 90
    # ── TEs (5) ──
    (623, ["agility","strength","acceleration","shortRoute","medRoute","deepRoute","trucking","catching"]),                       # Kittle 98
    (663, ["agility","strength","acceleration","shortRoute","medRoute","deepRoute","awareness","catching"]),                      # Kelce 93
    (675, ["agility","strength","acceleration","shortRoute","medRoute","deepRoute","trucking","catching"]),                       # Trey McBride 92
    (678, ["agility","strength","acceleration","shortRoute","medRoute","deepRoute","speed","catching"]),                          # Brock Bowers 91
    (694, ["agility","strength","acceleration","shortRoute","medRoute","deepRoute","trucking","catching"]),                       # Mark Andrews 90
    # ── DEs / Pass Rushers (8) ──
    (620, ["agility","speed","tackle","hitPower","pursuit","blockShed","powerMoves","finesseMoves"]),                             # Myles Garrett 99
    (624, ["agility","strength","acceleration","tackle","hitPower","blockShed","powerMoves","finesseMoves"]),                     # Micah Parsons 98
    (632, ["agility","speed","tackle","hitPower","pursuit","blockShed","powerMoves","finesseMoves"]),                             # Maxx Crosby 96
    (634, ["agility","strength","speed","tackle","hitPower","blockShed","powerMoves","finesseMoves"]),                            # T.J. Watt 96
    (642, ["agility","speed","tackle","hitPower","blockShed","powerMoves","strength","finesseMoves"]),                            # Nick Bosa 95
    (664, ["agility","speed","tackle","hitPower","blockShed","powerMoves","strength","finesseMoves"]),                            # Trey Hendrickson 93
    (667, ["agility","speed","tackle","hitPower","blockShed","powerMoves","strength","finesseMoves"]),                            # Hutchinson 92
    (679, ["agility","speed","tackle","hitPower","blockShed","powerMoves","strength","finesseMoves"]),                            # Danielle Hunter 91
    # ── DTs (7) ──
    (625, ["agility","speed","tackle","hitPower","finesseMoves","blockShed","strength","powerMoves"]),                            # Chris Jones 97
    (626, ["agility","speed","tackle","hitPower","finesseMoves","blockShed","powerMoves","strength"]),                            # Dexter Lawrence II 97
    (638, ["agility","speed","tackle","hitPower","finesseMoves","blockShed","powerMoves","strength"]),                            # Derrick Brown 95
    (646, ["agility","speed","tackle","hitPower","finesseMoves","powerMoves","strength","blockShed"]),                            # Cameron Heyward 94
    (665, ["agility","speed","tackle","hitPower","finesseMoves","blockShed","powerMoves","strength"]),                            # Vita Vea 93
    (671, ["agility","speed","tackle","hitPower","finesseMoves","blockShed","powerMoves","strength"]),                            # Jeffery Simmons 92
    (686, ["agility","speed","tackle","hitPower","finesseMoves","blockShed","powerMoves","strength"]),                            # Quinnen Williams 91
    # ── LBs (4) ──
    (627, ["agility","speed","strength","hitPower","pursuit","tackle","manCoverage","awareness"]),                                # Fred Warner 97
    (653, ["agility","speed","strength","hitPower","pursuit","playRecog","awareness","tackle"]),                                  # Roquan Smith 94
    (677, ["agility","speed","strength","hitPower","pursuit","playRecog","awareness","tackle"]),                                  # Bobby Wagner 91
    (688, ["agility","speed","strength","hitPower","pursuit","playRecog","tackle","awareness"]),                                  # Demario Davis 90
    # ── CBs / Safeties (10) ──
    (629, ["agility","strength","acceleration","tackle","hitPower","zoneCoverage","pressing","manCoverage"]),                     # Patrick Surtain II 97
    (637, ["strength","acceleration","tackle","hitPower","zoneCoverage","pressing","speed","manCoverage"]),                       # Christian Gonzalez 95
    (640, ["agility","strength","acceleration","tackle","hitPower","zoneCoverage","manCoverage","awareness"]),                    # Jessie Bates III 95
    (650, ["agility","strength","acceleration","zoneCoverage","manCoverage","pursuit","speed","hitPower"]),                       # Derwin James Jr 94
    (651, ["agility","strength","acceleration","tackle","hitPower","zoneCoverage","pressing","manCoverage"]),                     # Jalen Ramsey 94
    (654, ["agility","strength","acceleration","tackle","hitPower","pressing","zoneCoverage","manCoverage"]),                     # Sauce Gardner 94
    (658, ["agility","strength","acceleration","tackle","hitPower","zoneCoverage","pressing","manCoverage"]),                     # Derek Stingley Jr 93
    (666, ["agility","strength","acceleration","tackle","hitPower","zoneCoverage","manCoverage","awareness"]),                    # Xavier McKinney 93
    (669, ["agility","strength","acceleration","tackle","hitPower","zoneCoverage","manCoverage","pursuit"]),                      # Budda Baker 92
    (672, ["agility","strength","acceleration","tackle","hitPower","zoneCoverage","pressing","manCoverage"]),                     # Marlon Humphrey 92
    # ── OL (13) ──
    (619, ["agility","speed","runBlock","passBlock","runBlockPow","passBlockFin","passBlockPow","strength"]),                     # Lane Johnson 99 RT
    (630, ["agility","speed","passBlock","runBlock","runBlockPow","passBlockFin","passBlockPow","strength"]),                     # Trent Williams 97 LT
    (633, ["agility","speed","passBlock","runBlock","runBlockPow","passBlockFin","passBlockPow","strength"]),                     # Penei Sewell 96 RT
    (635, ["agility","speed","passBlock","runBlock","runBlockPow","passBlockFin","passBlockPow","strength"]),                     # Tristan Wirfs 96 LT
    (641, ["agility","speed","passBlock","runBlock","runBlockPow","passBlockFin","passBlockPow","strength"]),                     # Jordan Mailata 95 LT
    (644, ["agility","speed","passBlock","runBlock","runBlockPow","passBlockFin","passBlockPow","strength"]),                     # Quinn Meinerz 95 RG
    (647, ["agility","speed","passBlock","runBlock","runBlockPow","passBlockFin","strength","awareness"]),                        # Chris Lindstrom 94 RG
    (649, ["agility","speed","passBlock","runBlock","runBlockPow","passBlockFin","strength","awareness"]),                        # Creed Humphrey 94 C
    (652, ["agility","speed","passBlock","runBlock","runBlockPow","passBlockFin","passBlockPow","strength"]),                     # Laremy Tunsil 94 LT
    (659, ["agility","speed","passBlock","runBlock","runBlockPow","passBlockFin","strength","awareness"]),                        # Joe Thuney 93 LG
    (662, ["agility","speed","passBlock","runBlock","runBlockPow","passBlockFin","passBlockPow","strength"]),                     # Rashawn Slater 93 LT
    (670, ["agility","speed","passBlock","runBlock","runBlockPow","passBlockFin","passBlockPow","strength"]),                     # Christian Darrisaw 92 LT
    (674, ["agility","speed","passBlock","runBlock","runBlockPow","passBlockFin","passBlockPow","strength"]),                     # Quenton Nelson 92 LG
]


def main():
    assert len(PLAYER_REVEALS) == len(DATES), f"{len(PLAYER_REVEALS)} players != {len(DATES)} dates"

    random.seed(42)
    players = list(PLAYER_REVEALS)
    random.shuffle(players)

    puzzles = [(date, pid, rev) for date, (pid, rev) in zip(DATES, players)]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    skipped = []
    inserted = []

    for date, player_id, reveal_order in puzzles:
        cur.execute("SELECT player_id, created_by FROM daily_puzzles_madden WHERE date = ?", (date,))
        existing = cur.fetchone()
        if existing:
            ex_pid, ex_by = existing
            if ex_pid != player_id:
                skipped.append(f"  SKIP {date}: already has player_id={ex_pid} (created_by={ex_by})")
                continue
        cur.execute(
            "INSERT OR REPLACE INTO daily_puzzles_madden (date, player_id, reveal_order_json, created_by) VALUES (?,?,?,?)",
            (date, player_id, json.dumps(reveal_order), "seed")
        )
        inserted.append(date)

    conn.commit()
    conn.close()

    print(f"Inserted/updated {len(inserted)} puzzles.")
    if skipped:
        print(f"Skipped {len(skipped)} dates (different player already scheduled):")
        for s in skipped:
            print(s)
    print(f"Date range: {puzzles[0][0]} to {puzzles[-1][0]}")
    print("Done.")


if __name__ == "__main__":
    main()
