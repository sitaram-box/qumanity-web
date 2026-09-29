#!/usr/bin/env python3
"""Election pilot for Rohini Sector 24 (CS.DL.3.4.1A): 500 demo residents + week-1 candidates.

    python3 scripts/seed_election_demo.py            # back up the DB, add 500 demo users, pick candidates
    python3 scripts/seed_election_demo.py --vote     # weeks 2-3 (1-14 Oct): every eligible member votes
    python3 scripts/seed_election_demo.py --remove   # delete the demo users again (backup first)

Demo users go through the real /api/auth/register route (Flask test client), so zodiac, kundali,
IDs and search codes are made exactly as for a real member. Their on-disk folders in 0_Earth are
NOT written (folder_connector is switched off here) -- they are test data only, marked
users.is_demo = 1. The admin account is never touched.

Age mix: 60% Yuvak (25-49), 25% Vridh (50-75), 15% Balak (5-24); half male, half female.
Every demo user's PIN is DEMO_PIN (docs/ELECTION_PILOT.md lists their Private IDs).
"""
import datetime as dt
import json
import random
import shutil
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import app as appmod  # noqa: E402
import election_core  # noqa: E402
import folder_connector  # noqa: E402
from db import DB_PATH, get_db  # noqa: E402

TOTAL = 500
DEMO_PIN = "24024"
VILLAGE = election_core.PILOT_VILLAGE_ID
DOC_PATH = BASE_DIR / "docs" / "ELECTION_PILOT.md"

MALE = ["Aarav", "Vihaan", "Arjun", "Rohan", "Kabir", "Ishaan", "Aditya", "Karan", "Rahul", "Vikram", "Siddharth",
        "Manish", "Deepak", "Suresh", "Rajesh", "Amit", "Nikhil", "Pranav", "Harsh", "Yash", "Gaurav", "Mohit",
        "Ankit", "Varun", "Sanjay", "Ramesh", "Naveen", "Tarun", "Ajay", "Vivek"]
FEMALE = ["Aanya", "Diya", "Priya", "Ananya", "Isha", "Kavya", "Meera", "Neha", "Pooja", "Riya", "Sneha", "Tanvi",
          "Aditi", "Shreya", "Nisha", "Sunita", "Geeta", "Anjali", "Pallavi", "Swati", "Kiran", "Rekha", "Jyoti",
          "Simran", "Divya", "Lakshmi", "Radha", "Sarita", "Komal", "Payal"]
SURNAMES = ["Sharma", "Verma", "Gupta", "Singh", "Kumar", "Aggarwal", "Mehta", "Chauhan", "Yadav", "Joshi", "Bansal",
            "Malhotra", "Kapoor", "Saxena", "Tiwari", "Mishra", "Rawat", "Negi", "Bhatia", "Arora"]
LANGS = ["Hindi", "Hindi", "Hindi", "Punjabi", "English", "Urdu"]


def _admin_location() -> dict:
    conn = get_db()
    row = conn.execute("SELECT present_location_json FROM users WHERE json_extract(present_location_json, '$.village.id') = ? "
                       "ORDER BY id LIMIT 1", (VILLAGE,)).fetchone()
    conn.close()
    if not row:
        sys.exit("No member lives in Rohini Sector 24 yet -- the admin account should.")
    return json.loads(row["present_location_json"])


def _dob(rng: random.Random, lo: int, hi: int, today: dt.date) -> dt.date:
    """A birthday that makes the person lo..hi years old today."""
    earliest = dt.date(today.year - hi - 1, today.month, today.day) + dt.timedelta(days=1)
    latest = dt.date(today.year - lo, today.month, today.day)
    return earliest + dt.timedelta(days=rng.randint(0, (latest - earliest).days))


def _plan(rng: random.Random, today: dt.date) -> list[dict]:
    bands = [("Yuvak", 25, 49)] * int(TOTAL * 0.60) + [("Vridh", 50, 75)] * int(TOTAL * 0.25) + [("Balak", 5, 24)] * int(TOTAL * 0.15)
    people = []
    for i, (band, lo, hi) in enumerate(bands):
        gender = "male" if i % 2 == 0 else "female"
        first = rng.choice(MALE if gender == "male" else FEMALE)
        people.append({"name": f"{first} {rng.choice(SURNAMES)}", "gender": gender, "band": band,
                       "dob": _dob(rng, lo, hi, today).isoformat(),
                       "tob": f"{rng.randint(0, 23):02d}:{rng.choice([0, 15, 30, 45]):02d}", "language": rng.choice(LANGS)})
    return people


def _ensure_demo_column(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if "is_demo" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")
        conn.commit()


def backup() -> Path:
    dest = DB_PATH.with_name(f"qumanity_prototype.before_election_demo_{dt.datetime.now():%Y%m%d_%H%M%S}.db")
    src = sqlite3.connect(DB_PATH)
    out = sqlite3.connect(dest)
    src.backup(out)  # safe while the website is running
    out.close()
    src.close()
    return dest


def create_users(rng: random.Random) -> list[dict]:
    conn = get_db()
    _ensure_demo_column(conn)
    have = conn.execute("SELECT COUNT(*) FROM users WHERE is_demo = 1").fetchone()[0]
    conn.close()
    if have:
        print(f"{have} demo users already exist -- not adding more.")
        return []
    where = _admin_location()
    folder_connector.register_user_folder = lambda *a, **k: None  # keep 0_Earth free of test data
    today = dt.date.today()
    made = []
    for p in _plan(rng, today):
        client = appmod.app.test_client()
        r = client.post("/api/auth/register", json={
            "name": p["name"], "gender": p["gender"], "dob": p["dob"], "tob": p["tob"], "language": p["language"],
            "pin": DEMO_PIN, "birth_location": where, "present_location": where,
        })
        if r.status_code != 201:
            raise SystemExit(f"Registration failed for {p['name']}: {r.status_code} {r.get_data(as_text=True)[:200]}")
        body = r.get_json()
        made.append({**p, "user_id": body["user_id"], "private_code": body["private_code"], "sign": body["zodiac"]["sun_sign"]})
    conn = get_db()
    conn.executemany("UPDATE users SET is_demo = 1 WHERE id = ?", [(m["user_id"],) for m in made])
    conn.commit()
    conn.close()
    return made


def write_doc(made: list[dict], picked: dict):
    conn = get_db()
    rows = conn.execute("SELECT u.id, u.name, u.gender, u.dob, u.private_id_9digit, z.sun_sign FROM users u "
                        "JOIN user_zodiac z ON z.user_id = u.id WHERE u.is_demo = 1 ORDER BY z.sun_sign, u.gender, u.name").fetchall()
    summary = election_core.election_summary(conn, VILLAGE)
    conn.close()
    today = dt.date.today()
    band = lambda d: "Balak" if (a := election_core._age_years(d, today)) < 25 else "Yuvak" if a < 50 else "Vridh"  # noqa: E731
    lines = ["# Election pilot — Rohini Sector 24 (CS.DL.3.4.1A)", "",
             f"500 demo residents (test data, `users.is_demo = 1`). **Every demo PIN is `{DEMO_PIN}`.** "
             "They were registered through the real registration route; their 0_Earth folders were not written.", "",
             f"This month: **{summary['sign']}** ({summary['element']}) — week {summary['week']} of 4, status `{summary['status']}`.", ""]
    for w in summary["weeks"]:
        lines.append(f"- Week {w['week']} · {w['title']}: {w['start']} → {w['end']} — {w['text']}")
    lines += ["", "## Candidates (chosen at random in week 1)", ""]
    for g in ("male", "female"):
        for c in summary["candidates"][g]:
            lines.append(f"- {g}: {c['name']} (user {c['user_id']}) — “{c['reason']}”")
    lines += ["", f"## Demo members ({len(rows)})", "", "| Private ID | Name | Gender | Age group | Sun sign |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['private_id_9digit']} | {r['name']} | {r['gender']} | {band(r['dob'])} | {r['sun_sign']} |")
    DOC_PATH.write_text("\n".join(lines) + "\n")


def remove_demo():
    conn = get_db()
    _ensure_demo_column(conn)
    ids = [r[0] for r in conn.execute("SELECT id FROM users WHERE is_demo = 1")]
    conn.execute("PRAGMA foreign_keys = OFF")
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for t in tables:
        cols = {c[1] for c in conn.execute(f"PRAGMA table_info({t})")}
        for col in ("user_id", "voter_user_id", "candidate_user_id"):
            if col in cols and t != "users":
                conn.executemany(f"DELETE FROM {t} WHERE {col} = ?", [(i,) for i in ids])
    conn.executemany("DELETE FROM users WHERE id = ?", [(i,) for i in ids])
    conn.commit()
    conn.close()
    print(f"Removed {len(ids)} demo users.")


def main():
    args = set(sys.argv[1:])
    print("Backup:", backup().name)
    if "--remove" in args:
        return remove_demo()
    rng = random.Random(24)
    conn = get_db()
    if "--vote" in args:
        print("Votes:", election_core.auto_vote(conn, VILLAGE, rng=rng))
        print(json.dumps(election_core.election_summary(conn, VILLAGE), indent=1)[:1500])
        return
    made = create_users(rng)
    if made:
        mix = {}
        for m in made:
            mix[m["band"]] = mix.get(m["band"], 0) + 1
        print(f"Created {len(made)} demo users:", mix)
    picked = election_core.auto_nominate(conn, VILLAGE, rng=rng)
    conn.close()
    print("Week-1 candidates picked:", picked)
    write_doc(made, picked)
    print("Wrote", DOC_PATH)


if __name__ == "__main__":
    main()
