"""
seed_puzzles_mlb.py — Insert MLB daily puzzles 2026-03-17 through 2026-05-24 (69 days).
Mix of ~40 hitters and ~29 pitchers, including legends. Safe to re-run.

Reveal order philosophy:
  Hitters — start with fielding/arm/speed (generic), end on signature contact or power stat
  Pitchers — start with fielding/speed (generic), reveal stamina mid (shows SP vs CP),
             end on pitchVelocity for power arms or pitchControl for finesse arms
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

# Exactly 69 players (~40 hitters, ~29 pitchers)
PLAYER_REVEALS = [
    # ══ HITTERS (40) ══

    # ── Legends / 99 OVR ──
    (  39, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","plateVision","contactRight","powerRight"]),   # Albert Pujols 99 1B
    (1403, ["armStrength","fieldingAbility","speed","battingClutch","plateVision","powerRight","contactRight","contactLeft"]),       # Miguel Cabrera 99 3B
    (1874, ["fieldingAbility","speed","plateDiscipline","battingClutch","powerLeft","contactLeft","armStrength","powerRight"]),      # Troy Tulowitzki 99 SS

    # ── 95-96 OVR current ──
    ( 668, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","contactRight","powerLeft","armStrength"]),    # Francisco Lindor 95 SS
    (1059, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","powerRight","contactRight","powerLeft"]),     # José Ramírez 95 3B
    (1096, ["armAccuracy","fieldingAbility","speed","battingClutch","contactRight","powerRight","powerLeft","plateDiscipline"]),     # Juan Soto 95 RF

    # ── 94 OVR ──
    ( 272, ["armAccuracy","fieldingAbility","speed","battingClutch","contactLeft","powerLeft","contactRight","plateDiscipline"]),    # Bryce Harper 94 RF
    ( 615, ["fieldingAbility","speed","plateDiscipline","battingClutch","powerLeft","contactLeft","contactRight","armStrength"]),    # Elly De La Cruz 94 SS
    ( 831, ["armAccuracy","fieldingAbility","speed","battingClutch","powerRight","contactRight","powerLeft","contactLeft"]),         # Jackie Robinson 94 2B
    (2001, ["armAccuracy","speed","fieldingAbility","battingClutch","plateDiscipline","powerRight","powerLeft","contactLeft"]),      # Yordan Alvarez 94 LF
    (1145, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","contactRight","powerRight","powerLeft"]),     # Ken Griffey Jr. 95 CF
    (1801, ["armStrength","fieldingAbility","speed","battingClutch","plateDiscipline","powerLeft","contactLeft","plateVision"]),     # Ted Simmons 96 C
    (1037, ["armStrength","fieldingAbility","speed","battingClutch","plateDiscipline","powerLeft","contactLeft","powerRight"]),      # Jorge Posada 94 C
    (1303, ["armAccuracy","speed","fieldingAbility","battingClutch","plateDiscipline","contactLeft","powerLeft","powerRight"]),      # Manny Ramirez 94 LF
    (1652, ["armStrength","fieldingAbility","speed","battingClutch","plateDiscipline","powerLeft","contactLeft","powerRight"]),      # Roy Campanella 94 C
    ( 521, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","contactLeft","powerLeft","powerRight"]),      # Daylen Lile 94 LF
    (1460, ["armAccuracy","fieldingAbility","speed","battingClutch","contactLeft","powerLeft","contactRight","plateDiscipline"]),    # Nick Kurtz 94 1B
    (  50, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","contactLeft","contactRight","powerRight"]),   # Alex Bregman 94 3B
    ( 461, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","powerLeft","contactRight","contactLeft"]),    # Craig Biggio 94 2B

    # ── 93 OVR ──
    (   9, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","contactLeft","powerLeft","powerRight"]),      # Aaron Judge 93 RF
    ( 190, ["armAccuracy","fieldingAbility","plateDiscipline","battingClutch","powerLeft","powerRight","contactRight","speed"]),     # Bobby Witt Jr. 93 SS
    ( 511, ["armAccuracy","speed","fieldingAbility","battingClutch","contactLeft","powerLeft","contactRight","powerRight"]),         # David Ortiz 93 1B
    ( 674, ["armAccuracy","speed","fieldingAbility","battingClutch","plateDiscipline","powerLeft","contactRight","powerRight"]),     # Freddie Freeman 93 1B
    ( 716, ["armAccuracy","speed","fieldingAbility","battingClutch","plateDiscipline","contactLeft","powerLeft","powerRight"]),      # Giancarlo Stanton 93 LF
    ( 950, ["armStrength","fieldingAbility","speed","battingClutch","plateDiscipline","contactLeft","powerRight","armAccuracy"]),    # Jim Rice 93 LF
    ( 954, ["armStrength","fieldingAbility","speed","battingClutch","plateDiscipline","contactLeft","contactRight","armAccuracy"]),  # Jimmy Rollins 93 SS
    (1302, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","contactRight","powerLeft","powerRight"]),     # Manny Machado 93 3B
    (1346, ["armAccuracy","speed","fieldingAbility","battingClutch","plateDiscipline","contactLeft","powerLeft","powerRight"]),      # Matt Olson 93 1B
    (1399, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","powerRight","powerLeft","contactLeft"]),      # Mickey Mantle 93 CF
    (1840, ["armAccuracy","fieldingAbility","speed","battingClutch","contactRight","powerLeft","powerRight","plateDiscipline"]),     # Travis Bazzana 93 2B
    (1934, ["fieldingAbility","speed","battingClutch","plateDiscipline","contactLeft","contactRight","powerLeft","armStrength"]),    # Vladimir Guerrero Sr. 93 RF
    (1935, ["armAccuracy","speed","fieldingAbility","battingClutch","plateDiscipline","contactLeft","powerLeft","powerRight"]),      # Vladimir Guerrero Jr. 93 1B
    ( 324, ["armAccuracy","speed","fieldingAbility","battingClutch","plateDiscipline","powerLeft","powerRight","contactLeft"]),      # Carlos Santana 95 1B
    ( 412, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","contactLeft","powerLeft","contactRight"]),    # Cody Bellinger 93 CF
    ( 574, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","powerRight","contactRight","contactLeft"]),   # Dustin Pedroia 93 2B
    ( 717, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","contactLeft","powerLeft","powerRight"]),      # Gil Hodges 93 1B
    (1043, ["armAccuracy","speed","fieldingAbility","battingClutch","plateDiscipline","contactLeft","powerLeft","powerRight"]),      # Jose Bautista 93 RF
    (1697, ["armStrength","fieldingAbility","speed","battingClutch","plateDiscipline","contactRight","powerLeft","powerRight"]),     # Salvador Perez 93 C
    (1985, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","powerRight","contactRight","contactLeft"]),   # Yandy Díaz 93 1B
    (   1, ["armAccuracy","fieldingAbility","speed","battingClutch","plateDiscipline","powerRight","powerLeft","contactLeft"]),        # A.J. Ewing 92 CF

    # ══ PITCHERS (29) ══

    # ── 99 OVR Legend ──
    ( 660, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchVelocity","pitchMovement"]),          # Felix Hernandez 99 SP

    # ── 94 OVR ──
    ( 128, ["fieldingAbility","speed","stamina","pitchingClutch","pitchMovement","bbPerBf","pitchControl","pitchVelocity"]),          # Aroldis Chapman 94 CP
    ( 383, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchMovement","pitchVelocity"]),          # Chris Sale 94 SP
    ( 454, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchVelocity","pitchMovement"]),          # Corbin Burnes 94 SP
    (1653, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchVelocity","pitchMovement","pitchControl"]),          # Roy Halladay 94 SP
    (1747, ["fieldingAbility","speed","stamina","pitchMovement","pitchingClutch","bbPerBf","pitchControl","pitchVelocity"]),          # Shohei Ohtani 94 SP
    (   5, ["fieldingAbility","speed","stamina","pitchingClutch","bbPerBf","pitchControl","pitchMovement","pitchVelocity"]),          # Aaron Ashby 94 RP
    ( 111, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchVelocity","pitchMovement"]),          # Anibal Sanchez 94 SP

    # ── 93 OVR ──
    ( 185, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchVelocity","pitchMovement"]),          # Bob Gibson 93 SP
    ( 307, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchMovement","pitchVelocity"]),          # Cam Schlittler 93 SP
    ( 360, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchMovement","pitchVelocity"]),          # Chase Dollander 93 SP
    ( 856, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchMovement","pitchVelocity"]),          # Jake Arrieta 93 SP
    (1160, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchVelocity","pitchMovement"]),          # Kevin Gausman 93 SP
    (1364, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchVelocity","pitchMovement","pitchControl"]),          # Max Fried 93 SP
    (1893, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchMovement","pitchVelocity"]),          # Tyler Glasnow 93 SP

    # ── 92 OVR ──
    ( 268, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchMovement","pitchVelocity"]),          # Bryan Woo 92 SP
    ( 342, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchVelocity","pitchMovement"]),          # CC Sabathia 92 SP
    ( 659, ["fieldingAbility","speed","stamina","pitchingClutch","bbPerBf","pitchControl","pitchMovement","pitchVelocity"]),          # Felix Bautista 92 CP
    (1152, ["fieldingAbility","speed","stamina","pitchingClutch","bbPerBf","pitchControl","pitchMovement","pitchVelocity"]),          # Kenley Jansen 92 CP
    (1575, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchMovement","pitchVelocity"]),          # Randy Johnson 92 SP

    # ── 91 OVR ──
    ( 258, ["fieldingAbility","speed","stamina","pitchingClutch","bbPerBf","pitchVelocity","pitchControl","pitchMovement"]),          # Bruce Sutter 91 CP
    ( 779, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchMovement","pitchVelocity"]),          # Hunter Brown 91 SP
    ( 840, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchMovement","pitchVelocity"]),          # Jacob deGrom 91 SP
    ( 940, ["fieldingAbility","speed","stamina","pitchingClutch","bbPerBf","pitchMovement","pitchControl","pitchVelocity"]),          # Jhoan Duran 91 CP
    (1326, ["fieldingAbility","speed","stamina","pitchingClutch","bbPerBf","pitchControl","pitchMovement","pitchVelocity"]),          # Mason Miller 91 CP
    (1569, ["fieldingAbility","speed","stamina","pitchingClutch","bbPerBf","pitchMovement","pitchControl","pitchVelocity"]),          # Raisel Iglesias 91 CP
    (1640, ["fieldingAbility","speed","stamina","pitchingClutch","bbPerBf","pitchControl","pitchMovement","pitchVelocity"]),          # Rollie Fingers 91 CP
    (1709, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchVelocity","pitchMovement"]),          # Sandy Alcantara 91 SP
    (1712, ["fieldingAbility","speed","pitchingClutch","bbPerBf","stamina","pitchControl","pitchMovement","pitchVelocity"]),          # Satchel Paige 91 SP
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
        cur.execute("SELECT player_id, created_by FROM daily_puzzles_mlb WHERE date = ?", (date,))
        existing = cur.fetchone()
        if existing:
            ex_pid, ex_by = existing
            if ex_pid != player_id:
                skipped.append(f"  SKIP {date}: already has player_id={ex_pid} (created_by={ex_by})")
                continue
        cur.execute(
            "INSERT OR REPLACE INTO daily_puzzles_mlb (date, player_id, reveal_order_json, created_by) VALUES (?,?,?,?)",
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
