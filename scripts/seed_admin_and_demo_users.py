#!/usr/bin/env python3
"""Wipes all existing user accounts and seeds a fresh Admin account plus 5
demo accounts in every Indian state (185 total), via the app's own real
/api/auth/register endpoint (Flask test client) -- not hand-rolled DB rows,
so zodiac/kundali calculation, ID generation, and the real on-disk
BORN_HERE/LIVING_HERE folder trees all go through the exact same code path
a real registration would.

Run once from the project root:
    python3 scripts/seed_admin_and_demo_users.py

Writes credentials to docs/DEMO_ACCOUNTS.md (plaintext passwords -- this is
a local prototype's test data, not a production credential store).
"""
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
os.chdir(BASE_DIR)
sys.path.insert(0, str(BASE_DIR))

import app as appmod  # noqa: E402
import folder_connector  # noqa: E402

DB_PATH = BASE_DIR / "qumanity_prototype.db"
CREDENTIALS_PATH = BASE_DIR / "docs" / "DEMO_ACCOUNTS.md"

ADMIN_PASSWORD = "RohitAdmin@90"


def wipe_existing_users():
    """Deletes every user row (and dependents) plus their real on-disk
    folders -- explicit, one-time reset requested by the project owner."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    users = conn.execute("SELECT id, private_id, account_id FROM users").fetchall()
    print(f"Wiping {len(users)} existing user(s): " + ", ".join(str(u["id"]) for u in users))

    for u in users:
        for owner_id in (u["private_id"], u["account_id"]):
            if not owner_id:
                continue
            for folder in folder_connector.EARTH_ROOT.rglob(owner_id):
                if folder.is_dir():
                    print(f"  removing folder {folder}")
                    shutil.rmtree(folder)

    # Children before parent, regardless of whether FK enforcement is on.
    conn.execute("DELETE FROM user_zodiac")
    conn.execute("DELETE FROM user_elemental_profile")
    conn.execute("DELETE FROM wallet_transactions")
    conn.execute("DELETE FROM election_candidates")
    conn.execute("DELETE FROM election_votes")
    conn.execute("DELETE FROM village_council")
    conn.execute("DELETE FROM wallets")
    conn.execute("DELETE FROM users")
    conn.execute("DELETE FROM location_elements")
    conn.commit()
    conn.close()
    print("Database wiped.")


# ---- Real location payload builders (continent/country/zone/state/... ,
# each {id, name[, lat, lng]} -- only what id_generator/folder_connector/
# _location_lat_lng actually read, not the whole frontend-shaped blob). ----
_world = json.loads((BASE_DIR / "static" / "data" / "global_countries.json").read_text())
_states = json.loads((BASE_DIR / "static" / "data" / "india_states.json").read_text())
_districts = json.loads((BASE_DIR / "static" / "data" / "india_districts_tehsils.json").read_text())

_asia = next(c for c in _world["continents"] if c["code"] == "AS")
_india = next(co for co in _asia["countries"] if co["code"] == "IND")
CONTINENT = {"id": _asia["id"], "name": _asia["name"], "code": _asia["code"], "lat": _asia["lat"], "lng": _asia["lng"]}
COUNTRY = {"id": _india["id"], "name": _india["name"], "code": _india["code"]}


def village_lookup(village_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT name FROM india_villages WHERE id = ?", (village_id,)).fetchone()
    conn.close()
    return row[0] if row else None


def location_for_village(zone, state, district, tehsil, village_id, village_name):
    return {
        "continent": CONTINENT,
        "country": COUNTRY,
        "zone": {"id": zone["id"], "name": zone["name"]},
        "state": {"id": state["id"], "name": state["name"], "lat": state.get("lat"), "lng": state.get("lng")},
        "district": {"id": district["id"], "name": district["name"]},
        "tehsil": {"id": tehsil["id"], "name": tehsil["name"]},
        "village": {"id": village_id, "name": village_name},
    }


def first_village_location(zone, state):
    """The state's first district -> first tehsil -> first real village on
    disk -- every one of the 37 states was checked to have this chain
    before this script was written."""
    state_data = _districts["states"][state["id"]]
    district = state_data["districts"][0]
    tehsil = district["tehsils"][0]
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id, name FROM india_villages WHERE tehsil_id = ? LIMIT 1", (tehsil["id"],)).fetchone()
    conn.close()
    return location_for_village(zone, state, district, tehsil, row[0], row[1])


def register(client, **kwargs):
    resp = client.post("/api/auth/register", json=kwargs)
    body = resp.get_json()
    if resp.status_code != 201:
        raise RuntimeError(f"Registration failed for {kwargs.get('name')}: {body}")
    return body


def main():
    wipe_existing_users()

    client = appmod.app.test_client()
    credential_rows = []

    # ---- Admin account ----
    admin_birth = location_for_village(
        {"id": "IND/CS", "name": "Central State"},
        next(s for z in _states["zones"] for s in z["states"] if s["id"] == "CS.DL"),
        next(d for d in _districts["states"]["CS.DL"]["districts"] if d["id"] == "CS.DL.1"),
        next(t for t in next(d for d in _districts["states"]["CS.DL"]["districts"] if d["id"] == "CS.DL.1")["tehsils"] if t["id"] == "CS.DL.1.A"),
        "CS.DL.1.A.12", village_lookup("CS.DL.1.A.12"),
    )
    admin_present = location_for_village(
        {"id": "IND/CS", "name": "Central State"},
        next(s for z in _states["zones"] for s in z["states"] if s["id"] == "CS.DL"),
        next(d for d in _districts["states"]["CS.DL"]["districts"] if d["id"] == "CS.DL.5"),
        next(t for t in next(d for d in _districts["states"]["CS.DL"]["districts"] if d["id"] == "CS.DL.5")["tehsils"] if t["id"] == "CS.DL.5.4"),
        "CS.DL.5.4.1E", village_lookup("CS.DL.5.4.1E"),
    )
    admin_result = register(
        client, name="Rohit Mudgal", gender="male", dob="1990-07-30", tob="07:05",
        language="Hindi", password=ADMIN_PASSWORD,
        birth_location=admin_birth, present_location=admin_present,
    )
    print(f"Admin created: {admin_result['private_id']}")
    credential_rows.append(("Admin", "Rohit Mudgal", admin_result["private_id"], admin_result["account_id"], ADMIN_PASSWORD))
    client.get("/logout")

    # ---- 5 demo users per state (185 total), sequential numbering ----
    dob_pool = [("2005-03-15", "male"), ("1995-06-10", "female"), ("1975-09-20", "male"),
                ("1945-01-05", "female"), ("1985-11-25", "male")]
    counter = 0
    for zone in _states["zones"]:
        for state in zone["states"]:
            loc = first_village_location(zone, state)
            for i, (dob, gender) in enumerate(dob_pool, start=1):
                counter += 1
                name = f"Demo User{counter}"
                password = f"Demo{counter}Pass!"
                result = register(
                    client, name=f"Demo User{counter}", gender=gender, dob=dob, tob="12:00",
                    language="", password=password,
                    birth_location=loc, present_location=loc,
                )
                credential_rows.append((state["name"], name, result["private_id"], result["account_id"], password))
                client.get("/logout")
    print(f"Created {counter} demo users across {sum(len(z['states']) for z in _states['zones'])} states.")

    # ---- Credentials file ----
    lines = [
        "# Qumanity Demo Accounts",
        "",
        "**Testing credentials only — plaintext, local prototype data, not for production use.**",
        "Regenerate any time via `python3 scripts/seed_admin_and_demo_users.py` (wipes and reseeds everything).",
        "",
        "## Admin",
        "",
        "| Role | Name | User-ID (login) | Account ID | Password |",
        "|---|---|---|---|---|",
    ]
    role, name, uid, acc, pw = credential_rows[0]
    lines.append(f"| {role} | {name} | `{uid}` | `{acc}` | `{pw}` |")
    lines += ["", "## Demo Users (5 per state, 185 total)", "", "| State | Name | User-ID (login) | Account ID | Password |", "|---|---|---|---|---|"]
    for role, name, uid, acc, pw in credential_rows[1:]:
        lines.append(f"| {role} | {name} | `{uid}` | `{acc}` | `{pw}` |")
    CREDENTIALS_PATH.write_text("\n".join(lines) + "\n")
    print(f"Wrote credentials for {len(credential_rows)} accounts to {CREDENTIALS_PATH}")


if __name__ == "__main__":
    main()
