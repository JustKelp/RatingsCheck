"""
seed_puzzles.py — Insert NBA 2K daily puzzles from 2026-03-17 through 2026-06-30.
Safe to re-run: uses INSERT OR REPLACE.
Skips 2026-05-22 (DeRozan already scheduled by admin).

Reveal order philosophy:
  Positions 1-3 (shown at start): generic/weak stats for this player — could be many players
  Positions 4-8 (one per wrong guess): increasingly distinctive, ending on the player's signature stat
"""

import sqlite3
import json
import os

DB_PATH = os.environ.get("RATINGSCHECK_DB", "ratingscheck.db")

# Each entry: (date, player_id, reveal_order_list)
# Ordered from biggest stars → deeper pulls as the season progresses
PUZZLES = [
    # ── MARCH 2026 ──────────────────────────────────────────────────────────────
    # Jokic 98 OVR: low speed/steal → elite passVision signature
    ("2026-03-17", 126, ["speed","steal","block","interiorD","passAcc","defRebound","midRange","passVision"]),
    # Ant Edwards 96 OVR: low block/steal → elite drivingDunk
    ("2026-03-18", 303, ["block","steal","defRebound","passVision","perimeterD","three","speed","drivingDunk"]),
    # SGA 98 OVR: low strength/defReb → elite midRange
    ("2026-03-19", 357, ["strength","defRebound","block","steal","perimeterD","passAcc","ballHandle","midRange"]),
    # Holmgren 88 OVR: low speed/passAcc → elite midRange for a big
    ("2026-03-20", 358, ["speed","passAcc","standingDunk","three","steal","interiorD","block","midRange"]),
    # Giannis 97 OVR: moderate 3pt → explosive drivingDunk
    ("2026-03-21", 286, ["three","steal","block","passAcc","passVision","speed","strength","drivingDunk"]),
    # Cade 95 OVR: low block/steal → elite midRange
    ("2026-03-22", 144, ["block","steal","strength","interiorD","perimeterD","three","passAcc","midRange"]),
    # Luka 97 OVR: terrible defense → elite ballHandle
    ("2026-03-23", 232, ["block","steal","interiorD","perimeterD","defRebound","three","passVision","ballHandle"]),
    # Avdija 88 OVR: low steal/standingDunk → high midRange for a wing
    ("2026-03-24", 428, ["steal","standingDunk","three","strength","speed","defRebound","perimeterD","midRange"]),
    # Wemby 97 OVR: moderate passVision/speed → legendary block=99
    ("2026-03-25", 463, ["passVision","steal","speed","three","interiorD","standingDunk","defRebound","block"]),
    # Jaylen Brown 95 OVR: low steal → elite drivingDunk
    ("2026-03-26",  19, ["steal","block","defRebound","passVision","three","perimeterD","midRange","drivingDunk"]),
    # D. Mitchell 94 OVR: low block/defReb → elite speed=95
    ("2026-03-27",  90, ["block","defRebound","strength","interiorD","three","passAcc","drivingDunk","speed"]),
    # Sengun 88 OVR: low speed/perD → elite strength (surprising for slim big)
    ("2026-03-28", 180, ["perimeterD","steal","three","speed","defRebound","passAcc","block","strength"]),
    # Kawhi 95 OVR: moderate passVision → signature steal=93
    ("2026-03-29", 214, ["passVision","block","defRebound","strength","three","passAcc","perimeterD","steal"]),
    # Curry 95 OVR: terrible intD/strength → legendary three=99
    ("2026-03-30", 161, ["strength","standingDunk","defRebound","passVision","passAcc","midRange","ballHandle","three"]),
    # Brunson 94 OVR: terrible finisher stats → elite midRange=97
    ("2026-03-31", 339, ["block","defRebound","steal","standingDunk","interiorD","three","passAcc","midRange"]),

    # ── APRIL 2026 ──────────────────────────────────────────────────────────────
    # Tatum 93 OVR: low block → elite drivingDunk
    ("2026-04-01",  20, ["block","steal","passVision","strength","perimeterD","three","defRebound","drivingDunk"]),
    # KD 93 OVR: low steal/strength → elite midRange=97
    ("2026-04-02", 179, ["steal","strength","defRebound","interiorD","perimeterD","three","ballHandle","midRange"]),
    # Haliburton 93 OVR: low defReb/block → elite passAcc=96
    ("2026-04-03", 196, ["defRebound","block","strength","interiorD","three","ballHandle","passVision","passAcc"]),
    # Maxey 93 OVR: terrible standingDunk/strength → elite speed=90
    ("2026-04-04", 392, ["standingDunk","strength","defRebound","interiorD","steal","perimeterD","three","speed"]),
    # Booker 93 OVR: low steal/standingDunk → elite ballHandle=93
    ("2026-04-05", 409, ["steal","block","standingDunk","interiorD","three","midRange","perimeterD","ballHandle"]),
    # LeBron 92 OVR: moderate steal/3pt → elite strength=89
    ("2026-04-06", 233, ["steal","three","midRange","block","interiorD","passAcc","drivingDunk","strength"]),
    # Embiid 92 OVR: low steal/speed → elite strength=96
    ("2026-04-07", 393, ["steal","speed","ballHandle","perimeterD","block","defRebound","midRange","strength"]),
    # Anthony Davis 92 OVR: low passVision → elite strength=92
    ("2026-04-08", 516, ["passVision","three","steal","perimeterD","defRebound","block","interiorD","strength"]),
    # KAT 91 OVR: low steal/perD=50 → elite defRebound=93
    ("2026-04-09", 340, ["steal","perimeterD","midRange","interiorD","three","block","standingDunk","defRebound"]),
    # Harden 90 OVR: low steal/standingDunk=35 → elite ballHandle=95
    ("2026-04-10",  91, ["steal","block","standingDunk","defRebound","interiorD","passVision","three","ballHandle"]),
    # Kyrie 90 OVR: terrible intD/standingDunk → legendary ballHandle=99
    ("2026-04-11", 108, ["interiorD","strength","standingDunk","drivingDunk","steal","three","midRange","ballHandle"]),
    # Jalen Johnson 89 OVR (deeper pull, ATL): low steal → elite drivingDunk=96
    ("2026-04-12",   1, ["steal","block","three","perimeterD","strength","passAcc","defRebound","drivingDunk"]),
    # Jamal Murray 89 OVR: terrible intD/standingDunk → elite midRange=90
    ("2026-04-13", 127, ["interiorD","steal","block","defRebound","passVision","perimeterD","three","midRange"]),
    # Bam 89 OVR: low passVision → elite interiorD=90
    ("2026-04-14", 269, ["passVision","three","steal","block","defRebound","perimeterD","interiorD","strength"]),
    # Scottie Barnes 89 OVR: well-rounded → signature block=81 for a wing
    ("2026-04-15", 481, ["steal","three","defRebound","strength","perimeterD","passVision","block","midRange"]),
    # Trae Young 89 OVR: terrible block/standingDunk → elite midRange=97
    ("2026-04-16", 517, ["block","drivingDunk","standingDunk","steal","three","interiorD","passVision","midRange"]),
    # LaMelo 88 OVR: low block/intD → elite passAcc=93
    ("2026-04-17",  54, ["block","interiorD","midRange","steal","three","perimeterD","ballHandle","passAcc"]),
    # Cooper Flagg 88 OVR: low 3pt=71 for star → elite perimeterD=83
    ("2026-04-18", 109, ["three","passAcc","steal","block","strength","defRebound","interiorD","perimeterD"]),
    # Jimmy Butler 88 OVR: low block/standingDunk → elite perimeterD=86
    ("2026-04-19", 162, ["block","standingDunk","defRebound","midRange","steal","interiorD","ballHandle","perimeterD"]),
    # OG Anunoby 88 OVR: passVision=37 → elite perimeterD=90
    ("2026-04-20", 341, ["passVision","midRange","passAcc","defRebound","block","steal","three","perimeterD"]),
    # Damian Lillard 88 OVR: terrible intD/standingDunk → elite speed=87 with midRange=95
    ("2026-04-21", 427, ["standingDunk","block","interiorD","steal","three","ballHandle","midRange","speed"]),
    # Stephon Castle 88 OVR (rookie, SAS): low standingDunk → elite drivingDunk=88
    ("2026-04-22", 464, ["block","steal","strength","standingDunk","three","passAcc","perimeterD","drivingDunk"]),
    # Ja Morant 87 OVR: terrible standingDunk → elite speed=95
    ("2026-04-23", 249, ["standingDunk","block","three","steal","defRebound","passVision","drivingDunk","speed"]),
    # Amen Thompson 87 OVR: three=56 (iconic non-shooter) → elite drivingDunk=96
    ("2026-04-24", 181, ["three","passVision","strength","defRebound","steal","interiorD","speed","drivingDunk"]),
    # Jalen Williams 87 OVR: standingDunk=25 → elite perimeterD=92
    ("2026-04-25", 359, ["standingDunk","block","defRebound","steal","three","interiorD","speed","perimeterD"]),
    # Franz Wagner 87 OVR: slow for wing → elite midRange=90
    ("2026-04-26", 376, ["speed","steal","block","interiorD","passVision","defRebound","perimeterD","midRange"]),
    # De'Aaron Fox 87 OVR: terrible strength/intD → legendary speed=97
    ("2026-04-27", 465, ["strength","interiorD","block","defRebound","steal","passAcc","midRange","speed"]),
    # Evan Mobley 87 OVR: low steal/ballHandle → elite interiorD=96
    ("2026-04-28",  92, ["steal","ballHandle","three","passVision","defRebound","block","interiorD","perimeterD"]),
    # Pascal Siakam 87 OVR: low steal/midRange → elite interiorD=85
    ("2026-04-29", 197, ["steal","midRange","passVision","block","three","defRebound","perimeterD","interiorD"]),
    # Austin Reaves 87 OVR (deep pull): terrible intD/standingDunk → elite ballHandle=86
    ("2026-04-30", 234, ["interiorD","standingDunk","steal","strength","midRange","passAcc","three","ballHandle"]),

    # ── MAY 2026 ────────────────────────────────────────────────────────────────
    # Tyler Herro 87 OVR: steal=38/intD=46 → elite midRange=90
    ("2026-05-01", 270, ["steal","interiorD","standingDunk","block","defRebound","three","ballHandle","midRange"]),
    # Lauri Markkanen 87 OVR: passVision=39/steal=41 → shooting big signature
    ("2026-05-02", 498, ["passVision","steal","perimeterD","interiorD","defRebound","block","three","standingDunk"]),
    # Keyonte George 87 OVR (deep pull, UTA): terrible intD → elite ballHandle=86
    ("2026-05-03", 499, ["interiorD","steal","block","defRebound","three","midRange","passAcc","ballHandle"]),
    # Jarrett Allen 86 OVR: passAcc=25 (iconic) → elite standingDunk=90
    ("2026-05-04",  93, ["passVision","passAcc","ballHandle","steal","three","defRebound","interiorD","standingDunk"]),
    # Ausar Thompson 86 OVR: three=70 (non-shooter) → legendary steal=98
    ("2026-05-05", 145, ["passVision","passAcc","three","strength","block","interiorD","speed","steal"]),
    # Zion 86 OVR: three=67/bad defense → explosive drivingDunk=93
    ("2026-05-06", 321, ["three","perimeterD","interiorD","steal","block","defRebound","strength","drivingDunk"]),
    # Desmond Bane 86 OVR (deep pull, ORL): low standingDunk → elite three=86
    ("2026-05-07", 377, ["standingDunk","steal","defRebound","strength","midRange","perimeterD","ballHandle","three"]),
    # Domantas Sabonis 86 OVR: speed=48/perD=49 → elite defRebound=93
    ("2026-05-08", 445, ["speed","block","perimeterD","steal","three","passAcc","midRange","defRebound"]),
    # Brandon Ingram 86 OVR: steal=38/strength=42 → elite midRange=96
    ("2026-05-09", 482, ["steal","strength","interiorD","perimeterD","defRebound","ballHandle","three","midRange"]),
    # Jaren Jackson Jr. 86 OVR: passVision=38/midRange=57 → elite interiorD=93
    ("2026-05-10", 500, ["passVision","midRange","passAcc","steal","defRebound","perimeterD","block","interiorD"]),
    # Rudy Gobert 85 OVR: terrible ballHandle/passVision → famous three=25
    ("2026-05-11", 306, ["passVision","ballHandle","speed","midRange","steal","defRebound","block","three"]),
    # Julius Randle 85 OVR: low steal/block → elite strength=87
    ("2026-05-12", 304, ["steal","block","three","passVision","interiorD","defRebound","standingDunk","strength"]),
    # Trey Murphy III 85 OVR (deep pull, ORL): low passAcc → elite drivingDunk=88
    ("2026-05-13", 322, ["passAcc","block","ballHandle","midRange","steal","perimeterD","three","drivingDunk"]),
    # Jalen Duren 85 OVR (deep pull, DET): three=35/passVision=41 → elite defRebound=94
    ("2026-05-14", 146, ["passVision","three","steal","perimeterD","block","interiorD","strength","defRebound"]),
    # Brandon Miller 87 OVR (CHA): steal=46/intD=50 → elite drivingDunk=87
    ("2026-05-15",  55, ["steal","interiorD","strength","midRange","defRebound","perimeterD","three","drivingDunk"]),
    # Mikal Bridges 84 OVR: low defReb/passVision → elite perimeterD=88
    ("2026-05-16", 342, ["defRebound","block","passVision","steal","three","midRange","ballHandle","perimeterD"]),
    # Dylan Harper 84 OVR (rookie, SAS): low standingDunk → elite midRange=93
    ("2026-05-17", 466, ["standingDunk","strength","interiorD","steal","perimeterD","speed","ballHandle","midRange"]),
    # Alexandre Sarr 84 OVR (rookie, WAS): low steal/passVision → near-max block=96
    ("2026-05-18", 518, ["steal","passVision","three","strength","defRebound","interiorD","standingDunk","block"]),
    # Dyson Daniels 83 OVR (deep pull, ATL): three=50 (iconic) → legendary steal=96
    ("2026-05-19",   4, ["speed","three","block","strength","passVision","passAcc","perimeterD","steal"]),
    # Walker Kessler 83 OVR (deep pull, UTA): terrible passVision/speed → elite block=93
    ("2026-05-20", 501, ["passVision","steal","speed","ballHandle","three","defRebound","interiorD","block"]),
    # May 22 is already scheduled (DeRozan 446)
    # MPJ 86 OVR (BKN): low steal/block → high defRebound for a wing
    ("2026-05-21",  35, ["steal","block","interiorD","passAcc","perimeterD","three","defRebound","drivingDunk"]),
    # Derrick White 85 OVR: low strength → elite perimeterD=91 (best defender PG)
    ("2026-05-23",  21, ["strength","standingDunk","steal","interiorD","block","speed","passAcc","perimeterD"]),
    # Darius Garland 85 OVR: terrible strength/intD → elite midRange=93
    ("2026-05-24", 215, ["strength","interiorD","standingDunk","defRebound","steal","three","ballHandle","midRange"]),
    # Jaden McDaniels 85 OVR: passAcc=44/passVision=46 → elite perimeterD=90
    ("2026-05-25", 305, ["passAcc","passVision","steal","standingDunk","three","interiorD","block","perimeterD"]),
    # Norman Powell 85 OVR: standingDunk=25/strength=46 → solid shooter/finisher
    ("2026-05-26", 271, ["standingDunk","strength","passVision","interiorD","steal","perimeterD","three","drivingDunk"]),
    # Ivica Zubac 85 OVR: extreme low speed/steal → elite intD=92 + iconic three=26
    ("2026-05-27", 198, ["speed","steal","ballHandle","passVision","block","interiorD","defRebound","three"]),
    # Immanuel Quickley 84 OVR (TOR): terrible intD/block → elite midRange=94
    ("2026-05-28", 483, ["interiorD","block","standingDunk","drivingDunk","steal","three","ballHandle","midRange"]),
    # Dejounte Murray 84 OVR: low strength/standingDunk → steal=86 + midRange=98
    ("2026-05-29", 323, ["strength","block","standingDunk","three","passVision","steal","defRebound","midRange"]),
    # Paul George 83 OVR: moderate stats → signature steal=86
    ("2026-05-30", 394, ["block","defRebound","strength","interiorD","perimeterD","three","midRange","steal"]),
    # Aaron Gordon 83 OVR (DEN): low steal/passVision → elite drivingDunk=94
    ("2026-05-31", 128, ["steal","passVision","ballHandle","midRange","interiorD","perimeterD","standingDunk","drivingDunk"]),

    # ── JUNE 2026 — going progressively deeper ──────────────────────────────────
    # Kristaps Porzingis 83 OVR: low passAcc/steal → elite block=84
    ("2026-06-01", 163, ["passAcc","steal","perimeterD","interiorD","three","defRebound","midRange","block"]),
    # Josh Giddey 83 OVR (CHI): moderate stats → iconic midRange=38 (famous non-shooter)
    ("2026-06-02",  72, ["steal","block","interiorD","perimeterD","defRebound","passVision","passAcc","midRange"]),
    # Donovan Clingan 83 OVR (POR): extreme low speed/steal → elite block=86
    ("2026-06-03", 429, ["speed","steal","ballHandle","passVision","interiorD","defRebound","block","standingDunk"]),
    # Zach LaVine 83 OVR (SAC): passVision=42/steal=37 → explosive drivingDunk=94
    ("2026-06-04", 447, ["passVision","steal","defRebound","interiorD","three","speed","ballHandle","drivingDunk"]),
    # Shaedon Sharpe 83 OVR (POR): low block/strength → elite drivingDunk=95
    ("2026-06-05", 430, ["block","strength","standingDunk","interiorD","steal","three","speed","drivingDunk"]),
    # RJ Barrett 83 OVR (TOR): low steal → solid all-round finisher
    ("2026-06-06", 484, ["steal","block","standingDunk","passVision","defRebound","perimeterD","ballHandle","drivingDunk"]),
    # VJ Edgecombe 83 OVR (rookie, PHI): low standingDunk → elite drivingDunk=89
    ("2026-06-07", 395, ["standingDunk","passVision","steal","interiorD","three","midRange","speed","drivingDunk"]),
    # Ty Jerome 83 OVR (deep pull, MEM): terrible intD/dunks → elite midRange=93
    ("2026-06-08", 250, ["interiorD","standingDunk","drivingDunk","speed","steal","three","passVision","midRange"]),
    # Ayo Dosunmu 83 OVR (deep pull, MIN): standingDunk=25/intD=38 → elite three=88+midRange=90
    ("2026-06-09", 307, ["standingDunk","interiorD","steal","block","defRebound","ballHandle","three","midRange"]),
    # Onyeka Okongwu 82 OVR (ATL): low passAcc/ballHandle → surprising midRange=88 for a C
    ("2026-06-10",   5, ["passAcc","ballHandle","steal","perimeterD","interiorD","block","defRebound","midRange"]),
    # Jrue Holiday 82 OVR: low block/standingDunk → elite perimeterD=90 + steal=80
    ("2026-06-11", 431, ["block","strength","standingDunk","interiorD","passVision","steal","three","perimeterD"]),
    # Cason Wallace 82 OVR (deep pull, OKC): low passVision/standingDunk → iconic steal=98
    ("2026-06-12", 362, ["standingDunk","passVision","defRebound","strength","midRange","interiorD","perimeterD","steal"]),
    # Naz Reid 82 OVR (deep pull, MIN): slow + bad perD → surprising three=81 for a big
    ("2026-06-13", 308, ["speed","passVision","midRange","perimeterD","defRebound","block","three","strength"]),
    # Payton Pritchard 82 OVR: terrible intD/all dunks → elite midRange=88
    ("2026-06-14",  22, ["interiorD","standingDunk","drivingDunk","block","steal","perimeterD","three","midRange"]),
    # Matas Buzelis 82 OVR (deep pull, CHI): low steal/passVision → elite block=82 + drivingDunk=89
    ("2026-06-15",  73, ["steal","passVision","interiorD","perimeterD","three","speed","block","drivingDunk"]),
    # Jabari Smith Jr. 82 OVR (HOU): passVision=34/steal=38 → elite drivingDunk=85
    ("2026-06-16", 182, ["passVision","steal","strength","perimeterD","interiorD","three","block","drivingDunk"]),
    # Andrew Nembhard 82 OVR (deep pull, IND): low block → elite perimeterD=88 for a PG
    ("2026-06-17", 199, ["block","defRebound","strength","steal","interiorD","passVision","three","perimeterD"]),
    # Dillon Brooks 84 OVR (deep pull, PHX): passVision=37 enforcer → elite perimeterD=90
    ("2026-06-18", 410, ["passVision","block","standingDunk","defRebound","midRange","steal","three","perimeterD"]),
    # Isaiah Hartenstein 84 OVR (deep pull, OKC): bad perD/3pt → elite standingDunk=90
    ("2026-06-19", 361, ["perimeterD","three","ballHandle","passAcc","block","steal","defRebound","standingDunk"]),
    # Saddiq Bey 84 OVR (very deep pull, NOP): low block/midRange → solid three=82
    ("2026-06-20", 324, ["block","passVision","midRange","steal","interiorD","defRebound","three","drivingDunk"]),
    # Ajay Mitchell 84 OVR (very deep pull, OKC): low standingDunk/intD → steal=70 defender
    ("2026-06-21", 360, ["standingDunk","interiorD","strength","block","defRebound","steal","three","perimeterD"]),
    # NAW 83 OVR (very deep pull, ATL): low standingDunk → elite three=86
    ("2026-06-22",   2, ["standingDunk","defRebound","interiorD","passVision","steal","perimeterD","ballHandle","three"]),
    # CJ McCollum 83 OVR (ATL): terrible intD/dunks → elite midRange=88
    ("2026-06-23",   3, ["interiorD","standingDunk","drivingDunk","steal","perimeterD","three","ballHandle","midRange"]),
    # TJ McConnell 81 OVR (wild deep pull, IND): terrible dunks → shocking midRange=97 + passVision=97
    ("2026-06-24", 200, ["standingDunk","drivingDunk","strength","three","steal","passVision","passAcc","midRange"]),
    # Rui Hachimura 81 OVR (deep pull, LAL): passVision=28/steal=36 → shocking midRange=98
    ("2026-06-25", 235, ["passVision","steal","interiorD","perimeterD","three","standingDunk","strength","midRange"]),
    # Zach Edey 82 OVR (deep pull, MEM): terrible passVision/perD/speed → elite block=94
    ("2026-06-26", 251, ["passVision","perimeterD","speed","ballHandle","interiorD","defRebound","standingDunk","block"]),
    # Peyton Watson 82 OVR (very deep pull, DEN): passVision=39 → surprising midRange=90
    ("2026-06-27", 129, ["passVision","steal","strength","passAcc","interiorD","perimeterD","three","midRange"]),
    # Mark Williams 82 OVR (very deep pull, PHX): three=36/passVision=32 → elite standingDunk=85
    ("2026-06-28", 411, ["passVision","three","ballHandle","perimeterD","interiorD","defRebound","block","standingDunk"]),
    # Reed Sheppard 80 OVR (deep pull, HOU): low standingDunk → elite steal=86 + speed=90
    ("2026-06-29", 183, ["standingDunk","interiorD","strength","defRebound","three","perimeterD","speed","steal"]),
    # Derik Queen 80 OVR (very deep pull, NOP): slow/bad perD → surprisingly elite defRebound=83
    ("2026-06-30", 325, ["speed","perimeterD","three","steal","passAcc","block","standingDunk","defRebound"]),
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
    print("Done. Run 'python -c \"from models import get_daily_puzzle; import json; print(get_daily_puzzle())\"' to verify today's puzzle.")


if __name__ == "__main__":
    main()
