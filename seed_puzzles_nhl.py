"""
seed_puzzles_nhl.py — Insert NHL daily puzzles 2026-03-17 through 2026-05-24 (69 days).
Goalies excluded (goalie-specific stats are unpopulated in DB).
Safe to re-run: uses INSERT OR REPLACE. Player order is randomized.

Reveal order philosophy:
  Positions 1-3: generic/physical (defAwareness, faceoffs, bodyChecking, stickChecking)
  Positions 4-8: increasingly distinctive, ending on each player's signature stat
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

# (player_id, reveal_order) — order is pre-shuffle; main() shuffles with seed 42
PLAYER_REVEALS = [
    # ── 97 OVR ──
    (278, ["defAwareness","strength","faceoffs","wristShotPow","offAwareness","slapShotPow","deking","puckControl"]),       # McDavid
    # ── 96 OVR ──
    (173, ["faceoffs","defAwareness","slapShotPow","wristShotPow","strength","deking","puckControl","speed"]),              # MacKinnon
    (279, ["faceoffs","defAwareness","slapShotPow","deking","passAcc","wristShotPow","strength","puckControl"]),            # Draisaitl
    (716, ["faceoffs","strength","defAwareness","wristShotPow","slapShotPow","deking","puckControl","passAcc"]),            # Kucherov
    # ── 95 OVR ──
    (174, ["faceoffs","stickChecking","bodyChecking","wristShotPow","defAwareness","offAwareness","speed","slapShotPow"]),   # Makar
    (307, ["speed","bodyChecking","wristShotPow","passAcc","strength","faceoffs","offAwareness","defAwareness"]),            # Barkov
    (365, ["stickChecking","strength","faceoffs","slapShotPow","deking","puckControl","passAcc","speed"]),                  # Q. Hughes
    # ── 94 OVR ──
    ( 32, ["defAwareness","faceoffs","strength","slapShotPow","puckControl","offAwareness","deking","wristShotPow"]),        # Pastrnak
    (366, ["defAwareness","faceoffs","strength","wristShotPow","slapShotPow","passAcc","puckControl","deking"]),             # Kaprizov
    (607, ["defAwareness","strength","speed","puckControl","deking","passAcc","wristShotPow","faceoffs"]),                  # Crosby
    (746, ["defAwareness","bodyChecking","strength","slapShotPow","puckControl","passAcc","faceoffs","wristShotPow"]),       # Matthews
    (834, ["defAwareness","faceoffs","strength","slapShotPow","passAcc","puckControl","deking","speed"]),                   # Eichel
    # ── 93 OVR ──
    (226, ["faceoffs","defAwareness","wristShotPow","deking","passAcc","puckControl","fighting","strength"]),               # Rantanen
    (308, ["defAwareness","speed","faceoffs","strength","passAcc","puckControl","fighting","bodyChecking"]),                # M. Tkachuk
    (309, ["bodyChecking","speed","defAwareness","slapShotPow","passAcc","faceoffs","wristShotPow","puckControl"]),         # Reinhart
    (449, ["faceoffs","strength","defAwareness","passAcc","slapShotPow","puckControl","deking","speed"]),                   # Jack Hughes
    # ── 92 OVR ──
    ( 57, ["stickChecking","faceoffs","strength","wristShotPow","offAwareness","defAwareness","puckControl","passAcc"]),    # Dahlin
    (198, ["faceoffs","strength","stickChecking","wristShotPow","offAwareness","defAwareness","passAcc","speed"]),          # Werenski
    (337, ["faceoffs","strength","defAwareness","slapShotPow","passAcc","puckControl","wristShotPow","deking"]),            # Panarin
    (428, ["faceoffs","stickChecking","defAwareness","wristShotPow","speed","offAwareness","puckControl","slapShotPow"]),   # Roman Josi
    (718, ["faceoffs","strength","bodyChecking","slapShotPow","passAcc","puckControl","deking","speed"]),                   # Brayden Point
    (719, ["faceoffs","stickChecking","defAwareness","wristShotPow","offAwareness","passAcc","strength","slapShotPow"]),    # Hedman
    (747, ["faceoffs","strength","bodyChecking","defAwareness","wristShotPow","passAcc","deking","puckControl"]),           # Nylander
    (835, ["faceoffs","strength","bodyChecking","slapShotPow","deking","puckControl","wristShotPow","passAcc"]),            # Marner
    (897, ["faceoffs","defAwareness","bodyChecking","wristShotPow","slapShotPow","passAcc","puckControl","deking"]),        # Kyle Connor
    # ── 91 OVR ──
    (227, ["faceoffs","stickChecking","strength","wristShotPow","offAwareness","passAcc","defAwareness","slapShotPow"]),    # Heiskanen
    (450, ["faceoffs","strength","defAwareness","slapShotPow","wristShotPow","deking","puckControl","passAcc"]),            # Bratt
    (898, ["defAwareness","bodyChecking","strength","wristShotPow","deking","passAcc","puckControl","faceoffs"]),           # Scheifele
    # ── 90 OVR ──
    (123, ["stickChecking","faceoffs","strength","wristShotPow","offAwareness","puckControl","speed","defAwareness"]),      # Slavin
    (124, ["bodyChecking","strength","defAwareness","slapShotPow","wristShotPow","deking","faceoffs","passAcc"]),           # Aho
    (175, ["faceoffs","bodyChecking","strength","wristShotPow","passAcc","puckControl","deking","speed"]),                  # Necas
    (400, ["defAwareness","bodyChecking","strength","slapShotPow","deking","faceoffs","passAcc","puckControl"]),            # Suzuki
    (507, ["stickChecking","faceoffs","strength","wristShotPow","offAwareness","deking","passAcc","puckControl"]),          # Adam Fox
    (525, ["defAwareness","faceoffs","stickChecking","wristShotPow","slapShotPow","strength","passAcc","bodyChecking"]),    # Edstrom
    (535, ["faceoffs","defAwareness","strength","wristShotPow","passAcc","puckControl","deking","speed"]),                  # Stutzle
    (720, ["faceoffs","defAwareness","strength","wristShotPow","slapShotPow","deking","puckControl","speed"]),              # Brandon Hagel
    (775, ["faceoffs","bodyChecking","strength","slapShotPow","wristShotPow","deking","puckControl","passAcc"]),            # Clayton Keller
    (868, ["faceoffs","speed","stickChecking","defAwareness","strength","bodyChecking","wristShotPow","slapShotPow"]),      # Ovechkin
    (899, ["stickChecking","faceoffs","strength","wristShotPow","defAwareness","offAwareness","passAcc","slapShotPow"]),    # Morrissey
    # ── 89 OVR ──
    ( 33, ["faceoffs","strength","stickChecking","slapShotPow","wristShotPow","offAwareness","defAwareness","bodyChecking"]), # McAvoy
    ( 58, ["faceoffs","defAwareness","speed","slapShotPow","puckControl","deking","wristShotPow","strength"]),              # Tage Thompson
    ( 94, ["bodyChecking","defAwareness","stickChecking","wristShotPow","deking","puckControl","passAcc","faceoffs"]),      # Strome
    (176, ["faceoffs","bodyChecking","stickChecking","wristShotPow","slapShotPow","offAwareness","defAwareness","passAcc"]), # Devon Toews
    (199, ["faceoffs","bodyChecking","defAwareness","wristShotPow","slapShotPow","deking","puckControl","speed"]),          # Marchenko
    (229, ["defAwareness","bodyChecking","faceoffs","slapShotPow","puckControl","deking","passAcc","wristShotPow"]),        # Robertson
    (230, ["bodyChecking","defAwareness","strength","wristShotPow","puckControl","deking","passAcc","faceoffs"]),           # Duchene
    (255, ["bodyChecking","defAwareness","stickChecking","slapShotPow","faceoffs","deking","puckControl","wristShotPow"]),  # Larkin
    (256, ["faceoffs","strength","bodyChecking","wristShotPow","slapShotPow","passAcc","puckControl","deking"]),            # Raymond
    (311, ["defAwareness","stickChecking","bodyChecking","wristShotPow","puckControl","passAcc","faceoffs","fighting"]),    # Marchand
    (312, ["stickChecking","faceoffs","bodyChecking","wristShotPow","defAwareness","offAwareness","speed","slapShotPow"]),  # Forsling
    (368, ["faceoffs","defAwareness","strength","slapShotPow","wristShotPow","deking","puckControl","bodyChecking"]),       # Matt Boldy
    (429, ["faceoffs","defAwareness","bodyChecking","slapShotPow","passAcc","deking","puckControl","wristShotPow"]),        # Forsberg
    (451, ["stickChecking","bodyChecking","strength","slapShotPow","passAcc","deking","puckControl","faceoffs"]),           # Hischier
    (508, ["defAwareness","strength","faceoffs","slapShotPow","wristShotPow","deking","bodyChecking","passAcc"]),           # J.T. Miller
    (536, ["defAwareness","speed","puckControl","passAcc","strength","bodyChecking","faceoffs","fighting"]),                # Brady Tkachuk
    (537, ["stickChecking","faceoffs","bodyChecking","wristShotPow","slapShotPow","offAwareness","defAwareness","speed"]), # Jake Sanderson
    (692, ["bodyChecking","strength","defAwareness","slapShotPow","deking","puckControl","faceoffs","passAcc"]),            # Robert Thomas
    (721, ["faceoffs","defAwareness","strength","wristShotPow","slapShotPow","passAcc","deking","puckControl"]),            # Guentzel
    (836, ["stickChecking","faceoffs","puckControl","slapShotPow","wristShotPow","defAwareness","offAwareness","bodyChecking"]), # Pietrangelo
    (837, ["faceoffs","bodyChecking","speed","strength","wristShotPow","puckControl","defAwareness","slapShotPow"]),        # Mark Stone
    (838, ["stickChecking","faceoffs","bodyChecking","wristShotPow","slapShotPow","offAwareness","defAwareness","passAcc"]), # Hanifin
    (869, ["defAwareness","bodyChecking","speed","slapShotPow","wristShotPow","puckControl","deking","faceoffs"]),          # Dylan Strome
    # ── 88 OVR ──
    (  1, ["stickChecking","faceoffs","bodyChecking","wristShotPow","offAwareness","defAwareness","passAcc","slapShotPow"]), # John Carlson
    (125, ["faceoffs","defAwareness","strength","slapShotPow","wristShotPow","puckControl","deking","speed"]),              # Ehlers
    (126, ["faceoffs","bodyChecking","defAwareness","wristShotPow","slapShotPow","puckControl","deking","speed"]),          # Seth Jarvis
    (147, ["faceoffs","bodyChecking","defAwareness","slapShotPow","passAcc","deking","puckControl","wristShotPow"]),        # Bedard
    (231, ["stickChecking","faceoffs","bodyChecking","wristShotPow","offAwareness","defAwareness","passAcc","slapShotPow"]), # Thomas Harley
    (257, ["faceoffs","defAwareness","strength","slapShotPow","passAcc","puckControl","deking","wristShotPow"]),            # DeBrincat
    (258, ["stickChecking","faceoffs","bodyChecking","wristShotPow","offAwareness","defAwareness","slapShotPow","strength"]), # Moritz Seider
]


def main():
    random.seed(42)
    players = list(PLAYER_REVEALS)
    random.shuffle(players)

    puzzles = [(date, pid, rev) for date, (pid, rev) in zip(DATES, players)]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    skipped = []
    inserted = []

    for date, player_id, reveal_order in puzzles:
        cur.execute("SELECT player_id, created_by FROM daily_puzzles_nhl WHERE date = ?", (date,))
        existing = cur.fetchone()
        if existing:
            ex_pid, ex_by = existing
            if ex_pid != player_id:
                skipped.append(f"  SKIP {date}: already has player_id={ex_pid} (created_by={ex_by})")
                continue
        cur.execute(
            "INSERT OR REPLACE INTO daily_puzzles_nhl (date, player_id, reveal_order_json, created_by) VALUES (?,?,?,?)",
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
