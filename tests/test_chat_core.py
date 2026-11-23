"""Verifies the Unified Chat Architecture's Phase 2 Step 1 backend (2026-11-24): the generalized
(location_id, location_level) subgroups schema and its Village-vs-Tehsil+ creation rules, the
removed one-channel-per-user cap, the dual Account ID logic for temporary cross-location access,
the live-computed presence system, and the list_my_conversations() aggregator.

Standalone script, no test framework (none installed in this project): throwaway DB built through
the real Flask app and its real routes/functions, PASS/FAIL printing, exit 1 on failure. Follows
the same pattern as tests/test_q_cards.py and tests/test_local_areas.py.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"
os.environ["QM_ADMIN_PRIVATE_IDS"] = ""  # set per-user below once we know the real Private ID

import app as appmod  # noqa: E402
import board_core  # noqa: E402
import chat_core  # noqa: E402
import db as dbmod  # noqa: E402
import election_core  # noqa: E402

VILLAGE_A = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}
VILLAGE_B = {**VILLAGE_A, "village": {"id": "CS.DL.3.4.1B", "name": "Rohini Sector 25"}}
VILLAGE_A_BIRTH = {k: VILLAGE_A[k] for k in ("continent", "country", "zone", "state")}

_seed = dbmod.get_db()
_seed.execute("PRAGMA foreign_keys=OFF")  # this file seeds village_council directly (see seat_council())
_seed.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES ('CS.DL.3.4.1A', 'CS.DL.3.4', 'Rohini Sector 24')")
_seed.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES ('CS.DL.3.4.1B', 'CS.DL.3.4', 'Rohini Sector 25')")
_seed.commit()
_seed.close()

client = appmod.app.test_client()
FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


_n = [0]


def register(name_prefix, village=VILLAGE_A):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": VILLAGE_A_BIRTH, "present_location": village, "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def login(private_code, pin="12345"):
    res = client.post("/login", json={"private_id": private_code, "pin": pin})
    if res.status_code != 200:
        sys.exit(f"LOGIN FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")


def logout():
    client.post("/logout")


def raw(sql, params=()):
    conn = dbmod.get_db()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row


def raw_exec(sql, params=()):
    conn = dbmod.get_db()
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def seat_council(village_id, male_id, female_id, cycle_id):
    today = dt.date.today()
    raw_exec(
        "INSERT INTO election_cycles (id, village_id, zodiac_sign, element, year, nomination_start, "
        "nomination_end, voting_start, voting_end, status) VALUES (?, ?, 'Aries', 'Fire', 2026, ?, ?, ?, ?, 'closed')",
        (cycle_id, village_id,
         (today - dt.timedelta(days=20)).isoformat(), (today - dt.timedelta(days=15)).isoformat(),
         (today - dt.timedelta(days=10)).isoformat(), (today - dt.timedelta(days=1)).isoformat()),
    )
    raw_exec(
        "INSERT INTO village_council (village_id, zodiac_sign, year, male_head_user_id, female_head_user_id, "
        "election_cycle_id, leadership_start, leadership_end) VALUES (?, 'Aries', 2026, ?, ?, ?, ?, ?)",
        (village_id, male_id, female_id, cycle_id, (today - dt.timedelta(days=1)).isoformat(), (today + dt.timedelta(days=300)).isoformat()),
    )


print("=" * 70)
print("Setup: a seated Village A council (Nayak/Nayika) and an ordinary resident")
print("=" * 70)
nayak = register("Nayak")
nayika = register("Nayika")
resident = register("Resident")
other_resident = register("OtherResident")
seat_council(VILLAGE_A["village"]["id"], nayak["user_id"], nayika["user_id"], 501)


print()
print("=" * 70)
print("1. Village-level channel creation: Nayak/Nayika or Founder only, no vote needed")
print("=" * 70)
conn = dbmod.get_db()
try:
    chat_core.create_channel(conn, resident["user_id"], "village", VILLAGE_A["village"]["id"], "Water Supply", "desc", is_admin=False)
    check("1a. a plain resident cannot create a Village channel", False)
except PermissionError:
    check("1a. a plain resident cannot create a Village channel", True)
village_channel_id = chat_core.create_channel(conn, nayak["user_id"], "village", VILLAGE_A["village"]["id"], "Water Supply", "desc", is_admin=False)
check("1b. the Nayak CAN create a Village channel", village_channel_id is not None)
check("1c. it carries no created_via_vote_id (Village needs no vote)",
      raw("SELECT created_via_vote_id FROM subgroups WHERE id = ?", (village_channel_id,))["created_via_vote_id"] is None)
conn.close()


print()
print("=" * 70)
print("2. Tehsil-level channel creation: requires an already-PASSED People's Vote")
print("=" * 70)
conn = dbmod.get_db()
try:
    chat_core.create_channel(conn, resident["user_id"], "tehsil", VILLAGE_A["tehsil"]["id"], "Tehsil Elections", "desc", is_admin=False)
    check("2a. no vote at all -> refused", False)
except ValueError:
    check("2a. no vote at all -> refused", True)

open_vote = election_core.initiate_people_vote(conn, "tehsil", VILLAGE_A["tehsil"]["id"], "Create Tehsil Elections channel", "", resident["user_id"])
try:
    chat_core.create_channel(conn, resident["user_id"], "tehsil", VILLAGE_A["tehsil"]["id"], "Tehsil Elections", "desc",
                              is_admin=False, people_vote_id=open_vote["id"])
    check("2b. a still-OPEN (not yet tallied) vote -> refused", False)
except ValueError:
    check("2b. a still-OPEN (not yet tallied) vote -> refused", True)

election_core.cast_people_vote(conn, open_vote["id"], resident["user_id"], True)
election_core.cast_people_vote(conn, open_vote["id"], other_resident["user_id"], False)
tallied = election_core.tally_people_vote(conn, open_vote["id"], today=dt.date.today() + dt.timedelta(days=20))
check("2c. the vote failed (1 for / 1 against, 50% < 51%)", tallied["status"] == "failed")
try:
    chat_core.create_channel(conn, resident["user_id"], "tehsil", VILLAGE_A["tehsil"]["id"], "Tehsil Elections", "desc",
                              is_admin=False, people_vote_id=open_vote["id"])
    check("2d. a FAILED vote -> refused", False)
except ValueError:
    check("2d. a FAILED vote -> refused", True)

passing_vote = election_core.initiate_people_vote(conn, "tehsil", VILLAGE_A["tehsil"]["id"], "Create Tehsil Elections channel (retry)", "", resident["user_id"])
election_core.cast_people_vote(conn, passing_vote["id"], resident["user_id"], True)
election_core.cast_people_vote(conn, passing_vote["id"], other_resident["user_id"], True)
passed = election_core.tally_people_vote(conn, passing_vote["id"], today=dt.date.today() + dt.timedelta(days=20))
check("2e. this vote passed (2/2 in favour)", passed["status"] == "passed")

try:
    # resident genuinely lives in this district (so residency itself passes) -- isolates the
    # vote's OWN (level, location_id) mismatch check from the residency check above it.
    chat_core.create_channel(conn, resident["user_id"], "district", VILLAGE_A["district"]["id"], "Wrong Level", "desc",
                              is_admin=False, people_vote_id=passing_vote["id"])
    check("2f. the vote's own (level, location_id) must match exactly -> refused for a different level", False)
except ValueError:
    check("2f. the vote's own (level, location_id) must match exactly -> refused for a different level", True)

tehsil_channel_id = chat_core.create_channel(conn, resident["user_id"], "tehsil", VILLAGE_A["tehsil"]["id"], "Tehsil Elections", "desc",
                                              is_admin=False, people_vote_id=passing_vote["id"])
check("2g. a PASSED vote at the exact (level, location_id) -> channel created", tehsil_channel_id is not None)
check("2h. created_via_vote_id records which vote authorized it",
      raw("SELECT created_via_vote_id FROM subgroups WHERE id = ?", (tehsil_channel_id,))["created_via_vote_id"] == passing_vote["id"])

try:
    chat_core.create_channel(conn, resident["user_id"], "tehsil", VILLAGE_A["tehsil"]["id"], "Second Channel", "desc",
                              is_admin=False, people_vote_id=passing_vote["id"])
    check("2i. the SAME passed vote cannot be spent on a second channel", False)
except ValueError:
    check("2i. the SAME passed vote cannot be spent on a second channel", True)
conn.close()


print()
print("=" * 70)
print("3. The one-channel-per-user cap is REMOVED -- a member can join both channels at once")
print("=" * 70)
board_core.request_join(dbmod.get_db(), resident["user_id"], VILLAGE_A, village_channel_id)
board_core.decide_join(dbmod.get_db(), village_channel_id, resident["user_id"], True)
board_core.request_join(dbmod.get_db(), resident["user_id"], VILLAGE_A, tehsil_channel_id)
board_core.decide_join(dbmod.get_db(), tehsil_channel_id, resident["user_id"], True)
member_rows = raw(
    "SELECT COUNT(*) AS n FROM subgroup_members WHERE user_id = ? AND status = 'approved'", (resident["user_id"],)
)["n"]
check("3a. resident is an approved member of BOTH channels at once", member_rows == 2)
board_core.send_message(dbmod.get_db(), resident["user_id"], village_channel_id, "hello village", is_admin=False)
board_core.send_message(dbmod.get_db(), resident["user_id"], tehsil_channel_id, "hello tehsil", is_admin=False)
check("3b. resident can chat in both", True)


print()
print("=" * 70)
print("4. api_subgroup_decide is gated by the channel's own admin, not a bare Founder-only check")
print("=" * 70)
login(other_resident["private_code"])
res = client.post(f"/api/subgroups/{village_channel_id}/decide", json={"user_id": resident["user_id"], "approve": True})
check("4a. a non-admin, non-Nayak resident cannot decide a Village channel's join request", res.status_code == 403)
login(nayika["private_code"])
res = client.post(f"/api/subgroups/{village_channel_id}/decide", json={"user_id": resident["user_id"], "approve": True})
check("4b. the OTHER council head (Nayika, not just Nayak) can also decide it", res.status_code == 200)
logout()


print()
print("=" * 70)
print("5. list_my_conversations() aggregator")
print("=" * 70)
conn = dbmod.get_db()
convos = chat_core.list_my_conversations(conn, resident["user_id"])
by_kind = {(c["kind"], c["title"]): c for c in convos}
check("5a. the Village channel appears, tagged pane='channel' at location_level='village'",
      by_kind.get(("sub", "Water Supply"), {}).get("pane") == "channel" and by_kind[("sub", "Water Supply")]["location_level"] == "village")
check("5b. the Tehsil channel appears, tagged location_level='tehsil'",
      by_kind.get(("sub", "Tehsil Elections"), {}).get("location_level") == "tehsil")
check("5c. every row has an (even if None) last_message_at key and an unread_count key",
      all("last_message_at" in c and "unread_count" in c for c in convos))
conn.close()


print()
print("=" * 70)
print("6. Dual Account ID: temporary cross-location access")
print("=" * 70)
req = chat_core.request_temporary_access(dbmod.get_db(), resident["user_id"], "village", VILLAGE_B["village"]["id"])
check("6a. a fresh request starts 'pending'", req["status"] == "pending")
req_again = chat_core.request_temporary_access(dbmod.get_db(), resident["user_id"], "village", VILLAGE_B["village"]["id"])
check("6b. requesting again while pending is idempotent (same row, not a duplicate)", req_again["id"] == req["id"])

conn = dbmod.get_db()
try:
    chat_core.decide_temporary_access(conn, nayak["user_id"], req["id"], True, is_admin=False, location_name=VILLAGE_B)
    check("6c. Village A's own Nayak has no authority over Village B's access request", False)
except PermissionError:
    check("6c. Village A's own Nayak has no authority over Village B's access request", True)

chat_core.decide_temporary_access(conn, 0, req["id"], True, is_admin=True, location_name=VILLAGE_B)
active = chat_core.my_temporary_access(conn, resident["user_id"])[0]
check("6d. the Founder CAN approve it (no elected authority exists for Village B here)", active["status"] == "active")
check("6e. a real, minted foreign_account_id replaces the pending placeholder",
      active["foreign_account_id"] and not active["foreign_account_id"].startswith("PENDING-"))

home_id = chat_core.account_id_for_context(conn, resident["user_id"])
foreign_id = chat_core.account_id_for_context(conn, resident["user_id"], "village", VILLAGE_B["village"]["id"])
unrelated_id = chat_core.account_id_for_context(conn, resident["user_id"], "village", "CS.DL.3.4.9Z")
check("6f. home account_id is unchanged by the grant", home_id == raw("SELECT account_id FROM users WHERE id = ?", (resident["user_id"],))["account_id"])
check("6g. acting in the GRANTED foreign village resolves to the foreign account_id", foreign_id == active["foreign_account_id"])
check("6h. acting in an UNRELATED village still resolves to the home account_id", unrelated_id == home_id)
check("6i. the foreign and home account_ids are genuinely different", foreign_id != home_id)
conn.close()


print()
print("=" * 70)
print("7. Presence: computed live from last_seen_at/presence_override, never a stored status")
print("=" * 70)
conn = dbmod.get_db()
now = dt.datetime.now(dt.timezone.utc)
fresh_user = register("PresenceTester")
conn.execute("UPDATE users SET last_seen_at = ? WHERE id = ?", (now.isoformat(timespec="seconds"), fresh_user["user_id"]))
conn.commit()
check("7a. last_seen_at within 2 minutes -> green", chat_core.presence_status(conn, fresh_user["user_id"], now=now) == "green")
check("7b. same timestamp, 10 minutes later -> yellow",
      chat_core.presence_status(conn, fresh_user["user_id"], now=now + dt.timedelta(minutes=10)) == "yellow")
check("7c. same timestamp, 30 minutes later -> grey",
      chat_core.presence_status(conn, fresh_user["user_id"], now=now + dt.timedelta(minutes=30)) == "grey")
# Registering auto-logs a user in (session["user_id"] is set), and the after_request hook touches
# last_seen_at on every authenticated request -- so a user genuinely has one the instant they
# register, same as in real use. A direct NULL isolates presence_status()'s own handling of "no
# last_seen_at row value at all" (e.g. a pre-presence-feature legacy row) from that real behavior.
never_seen = register("NeverSeen")
conn.execute("UPDATE users SET last_seen_at = NULL WHERE id = ?", (never_seen["user_id"],))
conn.commit()
check("7d. a user with no last_seen_at value at all -> grey", chat_core.presence_status(conn, never_seen["user_id"]) == "grey")

chat_core.set_presence_override(conn, fresh_user["user_id"], True)
check("7e. a Busy override reports red even though last_seen_at is fresh (green-eligible)",
      chat_core.presence_status(conn, fresh_user["user_id"], now=now) == "red")
override_row = raw("SELECT presence_override_at FROM users WHERE id = ?", (fresh_user["user_id"],))
override_at = dt.datetime.fromisoformat(override_row["presence_override_at"])
check("7f. the Busy override auto-expires after PRESENCE_BUSY_HOURS, falling back to the computed status",
      chat_core.presence_status(conn, fresh_user["user_id"], now=override_at + dt.timedelta(hours=chat_core.PRESENCE_BUSY_HOURS, minutes=1)) == "grey")
chat_core.set_presence_override(conn, fresh_user["user_id"], False)
check("7g. clearing the override removes the Red state immediately",
      chat_core.presence_status(conn, fresh_user["user_id"], now=now) == "green")
conn.close()


print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
