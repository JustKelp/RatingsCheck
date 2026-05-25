"""
seed_puzzles.py — Insert NBA 2K daily puzzles from 2026-03-17 through 2026-06-30.
Safe to re-run: uses INSERT OR REPLACE.
Skips 2026-05-22 (DeRozan already scheduled by admin).

Reveal order philosophy:
  Positions 1-3 (shown at start): generic/weak stats for this player — could be many players
  Positions 4-8 (one per wrong guess): increasingly distinctive, ending on the player's signature stat

Player order is randomized — no pattern from stars to deep pulls.
"""

import sqlite3
import json
import os

DB_PATH = os.environ.get("RATINGSCHECK_DB", "ratingscheck.db")

# Each entry: (date, player_id, reveal_order_list)
PUZZLES = [
    ("2026-03-17",  35, ["steal", "block", "interiorD", "passAcc", "perimeterD", "three", "defRebound", "drivingDunk"]),
    ("2026-03-18",  92, ["steal", "ballHandle", "three", "passVision", "defRebound", "block", "interiorD", "perimeterD"]),
    ("2026-03-19",  20, ["block", "steal", "passVision", "strength", "perimeterD", "three", "defRebound", "drivingDunk"]),
    ("2026-03-20",  19, ["steal", "block", "defRebound", "passVision", "three", "perimeterD", "midRange", "drivingDunk"]),
    ("2026-03-21", 235, ["passVision", "steal", "interiorD", "perimeterD", "three", "standingDunk", "strength", "midRange"]),
    ("2026-03-22", 146, ["passVision", "three", "steal", "perimeterD", "block", "interiorD", "strength", "defRebound"]),
    ("2026-03-23", 303, ["block", "steal", "defRebound", "passVision", "perimeterD", "three", "speed", "drivingDunk"]),
    ("2026-03-24", 394, ["block", "defRebound", "strength", "interiorD", "perimeterD", "three", "midRange", "steal"]),
    ("2026-03-25",  72, ["steal", "block", "interiorD", "perimeterD", "defRebound", "passVision", "passAcc", "midRange"]),
    ("2026-03-26", 250, ["interiorD", "standingDunk", "drivingDunk", "speed", "steal", "three", "passVision", "midRange"]),
    ("2026-03-27", 484, ["steal", "block", "standingDunk", "passVision", "defRebound", "perimeterD", "ballHandle", "drivingDunk"]),
    ("2026-03-28", 307, ["standingDunk", "interiorD", "steal", "block", "defRebound", "ballHandle", "three", "midRange"]),
    ("2026-03-29",  90, ["block", "defRebound", "strength", "interiorD", "three", "passAcc", "drivingDunk", "speed"]),
    ("2026-03-30", 465, ["strength", "interiorD", "block", "defRebound", "steal", "passAcc", "midRange", "speed"]),
    ("2026-03-31", 215, ["strength", "interiorD", "standingDunk", "defRebound", "steal", "three", "ballHandle", "midRange"]),
    ("2026-04-01",  21, ["strength", "standingDunk", "steal", "interiorD", "block", "speed", "passAcc", "perimeterD"]),
    ("2026-04-02", 445, ["speed", "block", "perimeterD", "steal", "three", "passAcc", "midRange", "defRebound"]),
    ("2026-04-03", 304, ["steal", "block", "three", "passVision", "interiorD", "defRebound", "standingDunk", "strength"]),
    ("2026-04-04", 162, ["block", "standingDunk", "defRebound", "midRange", "steal", "interiorD", "ballHandle", "perimeterD"]),
    ("2026-04-05", 517, ["block", "drivingDunk", "standingDunk", "steal", "three", "interiorD", "passVision", "midRange"]),
    ("2026-04-06", 305, ["passAcc", "passVision", "steal", "standingDunk", "three", "interiorD", "block", "perimeterD"]),
    ("2026-04-07", 342, ["defRebound", "block", "passVision", "steal", "three", "midRange", "ballHandle", "perimeterD"]),
    ("2026-04-08", 323, ["strength", "block", "standingDunk", "three", "passVision", "steal", "defRebound", "midRange"]),
    ("2026-04-09",   1, ["steal", "block", "three", "perimeterD", "strength", "passAcc", "defRebound", "drivingDunk"]),
    ("2026-04-10",  55, ["steal", "interiorD", "strength", "midRange", "defRebound", "perimeterD", "three", "drivingDunk"]),
    ("2026-04-11", 463, ["passVision", "steal", "speed", "three", "interiorD", "standingDunk", "defRebound", "block"]),
    ("2026-04-12", 393, ["steal", "speed", "ballHandle", "perimeterD", "block", "defRebound", "midRange", "strength"]),
    ("2026-04-13",   4, ["speed", "three", "block", "strength", "passVision", "passAcc", "perimeterD", "steal"]),
    ("2026-04-14", 109, ["three", "passAcc", "steal", "block", "strength", "defRebound", "interiorD", "perimeterD"]),
    ("2026-04-15",   5, ["passAcc", "ballHandle", "steal", "perimeterD", "interiorD", "block", "defRebound", "midRange"]),
    ("2026-04-16", 249, ["standingDunk", "block", "three", "steal", "defRebound", "passVision", "drivingDunk", "speed"]),
    ("2026-04-17", 234, ["interiorD", "standingDunk", "steal", "strength", "midRange", "passAcc", "three", "ballHandle"]),
    ("2026-04-18", 447, ["passVision", "steal", "defRebound", "interiorD", "three", "speed", "ballHandle", "drivingDunk"]),
    ("2026-04-19",   3, ["interiorD", "standingDunk", "drivingDunk", "steal", "perimeterD", "three", "ballHandle", "midRange"]),
    ("2026-04-20", 321, ["three", "perimeterD", "interiorD", "steal", "block", "defRebound", "strength", "drivingDunk"]),
    ("2026-04-21", 518, ["steal", "passVision", "three", "strength", "defRebound", "interiorD", "standingDunk", "block"]),
    ("2026-04-22", 270, ["steal", "interiorD", "standingDunk", "block", "defRebound", "three", "ballHandle", "midRange"]),
    ("2026-04-23", 145, ["passVision", "passAcc", "three", "strength", "block", "interiorD", "speed", "steal"]),
    ("2026-04-24", 499, ["interiorD", "steal", "block", "defRebound", "three", "midRange", "passAcc", "ballHandle"]),
    ("2026-04-25", 183, ["standingDunk", "interiorD", "strength", "defRebound", "three", "perimeterD", "speed", "steal"]),
    ("2026-04-26", 306, ["passVision", "ballHandle", "speed", "midRange", "steal", "defRebound", "block", "three"]),
    ("2026-04-27",  73, ["steal", "passVision", "interiorD", "perimeterD", "three", "speed", "block", "drivingDunk"]),
    ("2026-04-28", 214, ["passVision", "block", "defRebound", "strength", "three", "passAcc", "perimeterD", "steal"]),
    ("2026-04-29", 464, ["block", "steal", "strength", "standingDunk", "three", "passAcc", "perimeterD", "drivingDunk"]),
    ("2026-04-30", 340, ["steal", "perimeterD", "midRange", "interiorD", "three", "block", "standingDunk", "defRebound"]),
    ("2026-05-01", 359, ["standingDunk", "block", "defRebound", "steal", "three", "interiorD", "speed", "perimeterD"]),
    ("2026-05-02", 376, ["speed", "steal", "block", "interiorD", "passVision", "defRebound", "perimeterD", "midRange"]),
    ("2026-05-03", 392, ["standingDunk", "strength", "defRebound", "interiorD", "steal", "perimeterD", "three", "speed"]),
    ("2026-05-04", 430, ["block", "strength", "standingDunk", "interiorD", "steal", "three", "speed", "drivingDunk"]),
    ("2026-05-05", 144, ["block", "steal", "strength", "interiorD", "perimeterD", "three", "passAcc", "midRange"]),
    ("2026-05-06",  91, ["steal", "block", "standingDunk", "defRebound", "interiorD", "passVision", "three", "ballHandle"]),
    ("2026-05-07", 428, ["steal", "standingDunk", "three", "strength", "speed", "defRebound", "perimeterD", "midRange"]),
    ("2026-05-08", 341, ["passVision", "midRange", "passAcc", "defRebound", "block", "steal", "three", "perimeterD"]),
    ("2026-05-09", 431, ["block", "strength", "standingDunk", "interiorD", "passVision", "steal", "three", "perimeterD"]),
    ("2026-05-10", 498, ["passVision", "steal", "perimeterD", "interiorD", "defRebound", "block", "three", "standingDunk"]),
    ("2026-05-11", 357, ["strength", "defRebound", "block", "steal", "perimeterD", "passAcc", "ballHandle", "midRange"]),
    ("2026-05-12", 377, ["standingDunk", "steal", "defRebound", "strength", "midRange", "perimeterD", "ballHandle", "three"]),
    ("2026-05-13", 179, ["steal", "strength", "defRebound", "interiorD", "perimeterD", "three", "ballHandle", "midRange"]),
    ("2026-05-14", 181, ["three", "passVision", "strength", "defRebound", "steal", "interiorD", "speed", "drivingDunk"]),
    ("2026-05-15", 466, ["standingDunk", "strength", "interiorD", "steal", "perimeterD", "speed", "ballHandle", "midRange"]),
    ("2026-05-16", 325, ["speed", "perimeterD", "three", "steal", "passAcc", "block", "standingDunk", "defRebound"]),
    ("2026-05-17", 516, ["passVision", "three", "steal", "perimeterD", "defRebound", "block", "interiorD", "strength"]),
    ("2026-05-18", 232, ["block", "steal", "interiorD", "perimeterD", "defRebound", "three", "passVision", "ballHandle"]),
    ("2026-05-19",  93, ["passVision", "passAcc", "ballHandle", "steal", "three", "defRebound", "interiorD", "standingDunk"]),
    ("2026-05-20", 308, ["speed", "passVision", "midRange", "perimeterD", "defRebound", "block", "three", "strength"]),
    ("2026-05-21", 360, ["standingDunk", "interiorD", "strength", "block", "defRebound", "steal", "three", "perimeterD"]),
    ("2026-05-23", 198, ["speed", "steal", "ballHandle", "passVision", "block", "interiorD", "defRebound", "three"]),
    ("2026-05-24",   2, ["standingDunk", "defRebound", "interiorD", "passVision", "steal", "perimeterD", "ballHandle", "three"]),
    ("2026-05-25", 409, ["steal", "block", "standingDunk", "interiorD", "three", "midRange", "perimeterD", "ballHandle"]),
    ("2026-05-26", 128, ["steal", "passVision", "ballHandle", "midRange", "interiorD", "perimeterD", "standingDunk", "drivingDunk"]),
    ("2026-05-27", 197, ["steal", "midRange", "passVision", "block", "three", "defRebound", "perimeterD", "interiorD"]),
    ("2026-05-28", 182, ["passVision", "steal", "strength", "perimeterD", "interiorD", "three", "block", "drivingDunk"]),
    ("2026-05-29", 233, ["steal", "three", "midRange", "block", "interiorD", "passAcc", "drivingDunk", "strength"]),
    ("2026-05-30", 126, ["speed", "steal", "block", "interiorD", "passAcc", "defRebound", "midRange", "passVision"]),
    ("2026-05-31", 251, ["passVision", "perimeterD", "speed", "ballHandle", "interiorD", "defRebound", "standingDunk", "block"]),
    ("2026-06-01", 199, ["block", "defRebound", "strength", "steal", "interiorD", "passVision", "three", "perimeterD"]),
    ("2026-06-02", 322, ["passAcc", "block", "ballHandle", "midRange", "steal", "perimeterD", "three", "drivingDunk"]),
    ("2026-06-03", 200, ["standingDunk", "drivingDunk", "strength", "three", "steal", "passVision", "passAcc", "midRange"]),
    ("2026-06-04", 482, ["steal", "strength", "interiorD", "perimeterD", "defRebound", "ballHandle", "three", "midRange"]),
    ("2026-06-05", 361, ["perimeterD", "three", "ballHandle", "passAcc", "block", "steal", "defRebound", "standingDunk"]),
    ("2026-06-06", 108, ["interiorD", "strength", "standingDunk", "drivingDunk", "steal", "three", "midRange", "ballHandle"]),
    ("2026-06-07", 483, ["interiorD", "block", "standingDunk", "drivingDunk", "steal", "three", "ballHandle", "midRange"]),
    ("2026-06-08",  22, ["interiorD", "standingDunk", "drivingDunk", "block", "steal", "perimeterD", "three", "midRange"]),
    ("2026-06-09", 429, ["speed", "steal", "ballHandle", "passVision", "interiorD", "defRebound", "block", "standingDunk"]),
    ("2026-06-10", 501, ["passVision", "steal", "speed", "ballHandle", "three", "defRebound", "interiorD", "block"]),
    ("2026-06-11", 481, ["steal", "three", "defRebound", "strength", "perimeterD", "passVision", "block", "midRange"]),
    ("2026-06-12", 127, ["interiorD", "steal", "block", "defRebound", "passVision", "perimeterD", "three", "midRange"]),
    ("2026-06-13", 410, ["passVision", "block", "standingDunk", "defRebound", "midRange", "steal", "three", "perimeterD"]),
    ("2026-06-14", 411, ["passVision", "three", "ballHandle", "perimeterD", "interiorD", "defRebound", "block", "standingDunk"]),
    ("2026-06-15", 286, ["three", "steal", "block", "passAcc", "passVision", "speed", "strength", "drivingDunk"]),
    ("2026-06-16", 500, ["passVision", "midRange", "passAcc", "steal", "defRebound", "perimeterD", "block", "interiorD"]),
    ("2026-06-17", 163, ["passAcc", "steal", "perimeterD", "interiorD", "three", "defRebound", "midRange", "block"]),
    ("2026-06-18", 180, ["perimeterD", "steal", "three", "speed", "defRebound", "passAcc", "block", "strength"]),
    ("2026-06-19", 271, ["standingDunk", "strength", "passVision", "interiorD", "steal", "perimeterD", "three", "drivingDunk"]),
    ("2026-06-20", 362, ["standingDunk", "passVision", "defRebound", "strength", "midRange", "interiorD", "perimeterD", "steal"]),
    ("2026-06-21", 161, ["strength", "standingDunk", "defRebound", "passVision", "passAcc", "midRange", "ballHandle", "three"]),
    ("2026-06-22", 129, ["passVision", "steal", "strength", "passAcc", "interiorD", "perimeterD", "three", "midRange"]),
    ("2026-06-23", 196, ["defRebound", "block", "strength", "interiorD", "three", "ballHandle", "passVision", "passAcc"]),
    ("2026-06-24", 269, ["passVision", "three", "steal", "block", "defRebound", "perimeterD", "interiorD", "strength"]),
    ("2026-06-25",  54, ["block", "interiorD", "midRange", "steal", "three", "perimeterD", "ballHandle", "passAcc"]),
    ("2026-06-26", 427, ["standingDunk", "block", "interiorD", "steal", "three", "ballHandle", "midRange", "speed"]),
    ("2026-06-27", 324, ["block", "passVision", "midRange", "steal", "interiorD", "defRebound", "three", "drivingDunk"]),
    ("2026-06-28", 358, ["speed", "passAcc", "standingDunk", "three", "steal", "interiorD", "block", "midRange"]),
    ("2026-06-29", 339, ["block", "defRebound", "steal", "standingDunk", "interiorD", "three", "passAcc", "midRange"]),
    ("2026-06-30", 395, ["standingDunk", "passVision", "steal", "interiorD", "three", "midRange", "speed", "drivingDunk"]),
]


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    skipped = []
    inserted = []

    for date, player_id, reveal_order in PUZZLES:
        # Check if this date is already scheduled (don't overwrite admin-set puzzles)
        cur.execute("SELECT player_id, created_by FROM daily_puzzles WHERE date = ?", (date,))
        existing = cur.fetchone()
        if existing:
            ex_pid, ex_by = existing
            if ex_pid != player_id:
                skipped.append(f"  SKIP {date}: already has player_id={ex_pid} (created_by={ex_by})")
                continue
            # Same player already set — still INSERT OR REPLACE to update reveal order
        cur.execute(
            "INSERT OR REPLACE INTO daily_puzzles (date, player_id, reveal_order_json, created_by) VALUES (?,?,?,?)",
            (date, player_id, json.dumps(reveal_order), "seed")
        )
        inserted.append(date)

    conn.commit()
    conn.close()

    print(f"Inserted/updated {len(inserted)} puzzles.")
    if skipped:
        print(f"Skipped {len(skipped)} dates (different player already scheduled by admin):")
        for s in skipped:
            print(s)
    print(f"\nDate range: {PUZZLES[0][0]} to {PUZZLES[-1][0]}")
    print("Done.")


if __name__ == "__main__":
    main()
