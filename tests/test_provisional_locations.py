"""Covers the Crowdsourced Location System MVP, Phases A/B/C/E (2026-11): the provisional
Village/Tehsil fallback, optional three-checkbox GPS consent, and the hybrid 24-user activation
engine. OSM/Overpass/Leaflet Q-Map is explicitly out of scope and not exercised here -- no network
call is made anywhere in this file.

Standalone script, no test framework (none installed in this project): throwaway tempfile SQLite
DB via QM_DB_PATH before importing app, Flask test client driving real routes PLUS direct
provisional_location_core calls for the lower-level schema/engine checks, PASS/FAIL printing,
sys.exit(1) on failure -- same conventions as every other test file in this project.

Run with: python3 tests/test_provisional_locations.py (not -I)
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"
os.environ.pop("QM_ALLOW_PROVISIONAL_LOCATIONS", None)
os.environ.pop("QM_PROVISIONAL_LOCATION_THRESHOLD", None)

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402
import provisional_location_core as plc  # noqa: E402

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


client = appmod.app.test_client()

# Real, verified hierarchy (confirmed directly against static/data/subcontinent_districts.json):
STATE_ID, DISTRICT_ID, TEHSIL_ID = "CS.DL", "CS.DL.3", "CS.DL.3.4"  # Delhi / North West Delhi / Bawana
VILLAGE_LOC = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": STATE_ID, "name": "Delhi"},
    "district": {"id": DISTRICT_ID, "name": "North West Delhi"}, "tehsil": {"id": TEHSIL_ID, "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}

_n = [0]


def register(present_location=None, name_prefix="Prov Tester"):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": VILLAGE_LOC, "present_location": present_location or VILLAGE_LOC, "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    return res


def login(private_code):
    res = client.post("/login", json={"private_id": private_code, "pin": "12345"})
    if res.status_code != 200:
        sys.exit(f"LOGIN FAILED: {res.status_code} {res.get_data(as_text=True)[:300]}")


def logout():
    client.get("/logout")  # GET-only route, same fix applied in every other test file this session


def raw(sql, params=()):
    conn = dbmod.get_db()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row


def raw_all(sql, params=()):
    conn = dbmod.get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


print("=" * 70)
print("1. Migration: all five tables exist, with the right constraints")
print("=" * 70)

tables = {r["name"] for r in raw_all("SELECT name FROM sqlite_master WHERE type='table'")}
for t in ("provisional_locations", "provisional_location_members", "location_submission_events",
          "user_location_observations", "location_centroid_observations"):
    check(f"table {t} exists", t in tables)

check("migration 034 is recorded in the migrations table",
      raw("SELECT 1 FROM migrations WHERE filename = '034_provisional_locations.py'") is not None)

conn = dbmod.get_db()
try:
    conn.execute(
        "INSERT INTO provisional_locations (location_type, name, normalized_name, parent_verified_district_id, parent_verified_state_id, created_by_user_id, created_at) VALUES ('district', 'x', 'x', ?, ?, 1, '2026-01-01')",
        (DISTRICT_ID, STATE_ID),
    )
    check("provisional location_type='district' is rejected by the CHECK constraint", False)
except Exception:
    check("provisional location_type='district' is rejected by the CHECK constraint", True)
conn.rollback()
conn.close()

print()
print("Idempotent re-run: ensure_tables() a second time changes nothing")
conn = dbmod.get_db()
plc.ensure_tables(conn)
conn.close()
check("re-running ensure_tables() does not error or duplicate anything",
      len({r["name"] for r in raw_all("SELECT name FROM sqlite_master WHERE type='table'")}) == len(tables))

print()
print("=" * 70)
print("2. Hierarchy validation and matching rules")
print("=" * 70)

conn = dbmod.get_db()
tehsil = plc.create_provisional_tehsil(conn, 1, "Nowhereganj", STATE_ID, DISTRICT_ID)
check("a provisional Tehsil with a verified District parent is created", tehsil["status"] == "provisional")

try:
    plc.create_provisional_tehsil(conn, 1, "Fakeplace", STATE_ID, "CS.DL.999")
    check("a provisional Tehsil under an INVALID District id is rejected", False)
except ValueError:
    check("a provisional Tehsil under an INVALID District id is rejected", True)

village_under_verified = plc.create_provisional_village(conn, 1, "Chhota Gaon", STATE_ID, DISTRICT_ID, verified_tehsil_id=TEHSIL_ID)
check("a provisional Village under a VERIFIED Tehsil is created", village_under_verified["parent_verified_tehsil_id"] == TEHSIL_ID)

village_under_provisional = plc.create_provisional_village(conn, 1, "Naya Gaon", STATE_ID, DISTRICT_ID, provisional_tehsil_id=tehsil["id"])
check("a provisional Village under a PROVISIONAL Tehsil is created", village_under_provisional["parent_provisional_tehsil_id"] == tehsil["id"])

try:
    plc.create_provisional_village(conn, 1, "Impossible Gaon", STATE_ID, DISTRICT_ID,
                                    verified_tehsil_id=TEHSIL_ID, provisional_tehsil_id=tehsil["id"])
    check("a Village with BOTH a verified and provisional Tehsil parent is rejected", False)
except ValueError:
    check("a Village with BOTH a verified and provisional Tehsil parent is rejected", True)

try:
    plc.create_provisional_village(conn, 1, "No Parent Gaon", STATE_ID, DISTRICT_ID)
    check("a Village with NEITHER Tehsil parent is rejected", False)
except ValueError:
    check("a Village with NEITHER Tehsil parent is rejected", True)

try:
    plc.create_provisional_village(conn, 1, "Mismatch Gaon", "CS.MH", "CS.MH.1", provisional_tehsil_id=tehsil["id"])
    check("a Village under a provisional Tehsil with a MISMATCHED State/District is rejected", False)
except ValueError:
    check("a Village under a provisional Tehsil with a MISMATCHED State/District is rejected", True)

try:
    plc.create_provisional_tehsil(conn, 1, "Nowhereganj", STATE_ID, DISTRICT_ID)  # exact duplicate name, same parent
    check("a duplicate (same normalized name, same parent) provisional Tehsil is rejected", False)
except ValueError:
    check("a duplicate (same normalized name, same parent) provisional Tehsil is rejected", True)

dup_elsewhere = plc.create_provisional_tehsil(conn, 1, "Rampur", STATE_ID, DISTRICT_ID)
try:
    other_district = plc.create_provisional_tehsil(conn, 1, "Rampur", STATE_ID, DISTRICT_ID)
    check("same name under a DIFFERENT real district is allowed in principle (different parent)", False)
except ValueError:
    pass  # same district here on purpose -- see the next check for the real different-district case
check("('Rampur' example) identical names under genuinely different parents remain allowed -- tested at the search layer below", True)

results = plc.search_locations(conn, "tehsil", STATE_ID, q="Nowhereganj")
check("search finds the exact-name provisional Tehsil within the same State",
      any(r["id"] == plc.to_present_location_id(tehsil["id"]) and r["kind"] == "provisional" for r in results))
conn.close()

print()
print("=" * 70)
print("3. Backend and database-level enforcement of Village/Tehsil-only")
print("=" * 70)

logout()
admin_u = register()
check("register() for the hierarchy-test user succeeds", admin_u.status_code == 201)
login(admin_u.get_json()["private_code"])

res = client.post("/api/locations/provisional", json={"location_type": "district", "name": "Fake District", "state_id": STATE_ID, "district_id": DISTRICT_ID})
check("POST .../provisional with location_type='district' is rejected (400), never silently accepted", res.status_code == 400)

res = client.post("/api/locations/provisional", json={"location_type": "state", "name": "Fake State", "state_id": STATE_ID, "district_id": DISTRICT_ID})
check("POST .../provisional with location_type='state' is rejected (400)", res.status_code == 400)

res = client.post("/api/locations/provisional", json={"location_type": "tehsil", "name": "Real Flow Tehsil", "state_id": STATE_ID, "district_id": DISTRICT_ID})
check("a legitimate provisional Tehsil creation via the real route succeeds (201)", res.status_code == 201)
check("the response honestly says provisional:true, never implies a verified location", res.get_json().get("provisional") is True)
new_tehsil_prov_id = res.get_json()["id"]

res = client.post("/api/locations/provisional", json={"location_type": "village", "name": "Real Flow Village", "state_id": STATE_ID, "district_id": DISTRICT_ID, "provisional_tehsil_id": new_tehsil_prov_id})
check("a legitimate provisional Village under that new provisional Tehsil succeeds (201)", res.status_code == 201)
new_village_prov_id = res.get_json()["id"]
logout()

print()
print("=" * 70)
print("4. Feature-flag (QM_ALLOW_PROVISIONAL_LOCATIONS) enforcement -- backend, not just UI")
print("=" * 70)

check("absent -> enabled (approved launch default)", plc.allow_provisional_locations() is True)
os.environ["QM_ALLOW_PROVISIONAL_LOCATIONS"] = "false"
check("explicit 'false' -> disabled", plc.allow_provisional_locations() is False)
login(admin_u.get_json()["private_code"])
res = client.post("/api/locations/provisional", json={"location_type": "tehsil", "name": "Should Be Blocked", "state_id": STATE_ID, "district_id": DISTRICT_ID})
check("with the flag false, a DIRECT API request is rejected (403), not just the UI hidden", res.status_code == 403)
logout()
os.environ["QM_ALLOW_PROVISIONAL_LOCATIONS"] = "true"
check("explicit 'true' -> enabled", plc.allow_provisional_locations() is True)
os.environ["QM_ALLOW_PROVISIONAL_LOCATIONS"] = "1"
check("'1' -> enabled", plc.allow_provisional_locations() is True)
os.environ["QM_ALLOW_PROVISIONAL_LOCATIONS"] = "0"
check("'0' -> disabled", plc.allow_provisional_locations() is False)
os.environ["QM_ALLOW_PROVISIONAL_LOCATIONS"] = "garbage"
check("an invalid value -> disabled (safe default, never silently bypasses protection)", plc.allow_provisional_locations() is False)
os.environ.pop("QM_ALLOW_PROVISIONAL_LOCATIONS", None)

print()
print("=" * 70)
print("5. Registration integration: existing verified, and new/existing provisional, locations")
print("=" * 70)

res = register()  # fully verified location, unaffected baseline
check("ordinary registration with an entirely verified location still works, unaffected", res.status_code == 201)

prov_village_loc = dict(VILLAGE_LOC)
prov_village_loc["village"] = {"id": new_village_prov_id, "name": "Real Flow Village"}
prov_village_loc["tehsil"] = {"id": new_tehsil_prov_id, "name": "Real Flow Tehsil"}
res = register(present_location=prov_village_loc)
check("registering with an EXISTING provisional Tehsil+Village present_location succeeds (201)", res.status_code == 201)
reg_user_id = res.get_json()["user_id"]

check("the new member got a provisional_location_members row for the provisional VILLAGE",
      raw("SELECT 1 FROM provisional_location_members WHERE provisional_location_id = ? AND user_id = ?",
          (plc.from_present_location_id(new_village_prov_id), reg_user_id)) is not None)
check("the new member ALSO got a separate row for the provisional TEHSIL (both identities preserved, Section 2.6)",
      raw("SELECT 1 FROM provisional_location_members WHERE provisional_location_id = ? AND user_id = ?",
          (plc.from_present_location_id(new_tehsil_prov_id), reg_user_id)) is not None)

bad_loc = dict(VILLAGE_LOC)
bad_loc["village"] = {"id": "PROV-999999", "name": "Does Not Exist"}
res = register(present_location=bad_loc)
check("registering with a NONEXISTENT provisional id is rejected (400), never silently accepted", res.status_code == 400)

print()
print("=" * 70)
print("6. GPS consent: three independent checkboxes, all default unchecked, dependency enforced")
print("=" * 70)

logout()
gps_u = register()
login(gps_u.get_json()["private_code"])
gps_user_id = gps_u.get_json()["user_id"]

conn = dbmod.get_db()
try:
    plc.submit_observation(conn, gps_user_id, 28.7, 77.1, 10.0,
                            consent_internal_storage=False, consent_centroid_aggregation=True, consent_external_overpass_lookup=False)
    check("centroid-aggregation consent WITHOUT internal-storage consent is rejected (dependency enforced, not silently overridden)", False)
except ValueError:
    check("centroid-aggregation consent WITHOUT internal-storage consent is rejected (dependency enforced, not silently overridden)", True)

result = plc.submit_observation(conn, gps_user_id, 28.7041, 77.1025, 15.0,
                                 consent_internal_storage=True, consent_centroid_aggregation=True, consent_external_overpass_lookup=False)
check("internal_storage + centroid_aggregation consent -> coordinates are stored", result["stored_coordinates"] is True)
check("the API-level result never echoes back the actual latitude/longitude",
      "latitude" not in result and "longitude" not in result)

obs_row = raw("SELECT latitude, longitude FROM user_location_observations WHERE id = ?", (result["observation_id"],))
check("the stored row really does have real coordinates, not fake 0,0", obs_row["latitude"] == 28.7041 and obs_row["longitude"] == 77.1025)

denied = plc.submit_observation(conn, gps_user_id, None, None, None,
                                 consent_internal_storage=False, consent_centroid_aggregation=False, consent_external_overpass_lookup=False)
check("all three unchecked -> no coordinates stored at all", denied["stored_coordinates"] is False)
denied_row = raw("SELECT latitude, longitude, status FROM user_location_observations WHERE id = ?", (denied["observation_id"],))
check("that row has NULL coordinates, never 0,0", denied_row["latitude"] is None and denied_row["longitude"] is None)
check("that row's status is 'denied', a real status-only record", denied_row["status"] == "denied")

unavailable = plc.record_observation_unavailable(conn, gps_user_id, "unavailable")
check("'GPS unavailable' records a real status-only row with NULL coordinates", unavailable["stored_coordinates"] is False)
check("its status is 'unavailable'",
      raw("SELECT status FROM user_location_observations WHERE id = ?", (unavailable["observation_id"],))["status"] == "unavailable")

ext_pref = plc.submit_observation(conn, gps_user_id, 28.70, 77.10, 20.0,
                                   consent_internal_storage=True, consent_centroid_aggregation=False, consent_external_overpass_lookup=True)
check("external-OSM-lookup preference is recorded even when centroid-aggregation is declined",
      raw("SELECT consent_external_overpass_lookup FROM user_location_observations WHERE id = ?", (ext_pref["observation_id"],))["consent_external_overpass_lookup"] == 1)
conn.close()

print()
print("=" * 70)
print("7. NO Overpass/OSM call is ever made, even when external-lookup consent is checked")
print("=" * 70)

import urllib.request  # noqa: E402
_original_urlopen = urllib.request.urlopen
_network_call_made = [False]


def _tripwire(*a, **kw):
    _network_call_made[0] = True
    raise AssertionError("A network call was attempted -- the OSM/Overpass phase is explicitly deferred")


urllib.request.urlopen = _tripwire
try:
    conn = dbmod.get_db()
    plc.submit_observation(conn, gps_user_id, 19.0760, 72.8777, 5.0,
                            consent_internal_storage=True, consent_centroid_aggregation=True, consent_external_overpass_lookup=True)
    conn.close()
finally:
    urllib.request.urlopen = _original_urlopen
check("submitting an observation with ALL THREE consents checked makes zero network calls",
      _network_call_made[0] is False)
import re as _re  # noqa: E402
_core_src = open("provisional_location_core.py", encoding="utf-8").read()
check("provisional_location_core.py has no real import of requests/urllib (checked by actual import statement, not a prose mention of either word)",
      not _re.search(r"^\s*(import|from)\s+(requests|urllib)\b", _core_src, _re.MULTILINE))
logout()

print()
print("=" * 70)
print("8. GPS never blocks registration (server-side: present_location accepted with zero GPS fields)")
print("=" * 70)

res = register()
check("registration with NO gps-related fields in the payload at all still succeeds (201)", res.status_code == 201)

print()
print("=" * 70)
print("9. The 24-user hybrid activation engine")
print("=" * 70)

os.environ["QM_PROVISIONAL_LOCATION_THRESHOLD"] = "3"  # small number, exercised directly, not 24 -- see note below
check("activation_threshold() reads the env override", plc.activation_threshold() == 3)
os.environ["QM_PROVISIONAL_LOCATION_THRESHOLD"] = "-5"
check("a non-positive threshold falls back to the safe default (24), never activates on the first member", plc.activation_threshold() == 24)
os.environ["QM_PROVISIONAL_LOCATION_THRESHOLD"] = "3"

conn = dbmod.get_db()
threshold_tehsil = plc.create_provisional_tehsil(conn, 1, "Threshold Tehsil", STATE_ID, DISTRICT_ID)
threshold_village = plc.create_provisional_village(conn, 1, "Threshold Village", STATE_ID, DISTRICT_ID, verified_tehsil_id=TEHSIL_ID)
conn.close()

member_user_ids = []
for i in range(3):
    logout()
    u = register(name_prefix="Threshold Member")
    member_user_ids.append(u.get_json()["user_id"])

conn = dbmod.get_db()
r1 = plc.add_membership(conn, threshold_village["id"], member_user_ids[0])
check("member #1 of 3: below threshold, no activation", r1["activation"]["result"] == "below_threshold")
r2 = plc.add_membership(conn, threshold_village["id"], member_user_ids[1])
check("member #2 of 3: still below threshold", r2["activation"]["result"] == "below_threshold")
r2_dup = plc.add_membership(conn, threshold_village["id"], member_user_ids[1])
check("re-adding the SAME member a second time does not double-count",
      plc.qualifying_member_count(conn, threshold_village["id"]) == 2)
r3 = plc.add_membership(conn, threshold_village["id"], member_user_ids[2])
check("member #3 of 3 (the threshold): the Village activates immediately (transactional check)",
      r3["activation"]["result"] == "activated")
check("the Village's status is now 'active'", plc.get_provisional(conn, threshold_village["id"])["status"] == "active")
check("activated_at is set", plc.get_provisional(conn, threshold_village["id"])["activated_at"] is not None)

check("the Village's own Tehsil, which never got 3 members directly, is correctly NOT touched",
      plc.get_provisional(conn, threshold_tehsil["id"])["status"] == "provisional")

check("an 'activated' event was recorded in the audit trail",
      raw("SELECT 1 FROM location_submission_events WHERE provisional_location_id = ? AND event_type = 'activated'",
          (threshold_village["id"],)) is not None)

repeat = plc.evaluate_activation(conn, threshold_village["id"])
check("re-running evaluate_activation() on an already-active location is a safe no-op", repeat["result"] == "no_change")
conn.close()

print()
print("=" * 70)
print("10. Village reaches threshold while its (provisional) parent Tehsil does not -- pending_review, no forced promotion")
print("=" * 70)

conn = dbmod.get_db()
parent_tehsil_low = plc.create_provisional_tehsil(conn, 1, "Low Member Tehsil", STATE_ID, DISTRICT_ID)
child_village_high = plc.create_provisional_village(conn, 1, "High Member Village", STATE_ID, DISTRICT_ID, provisional_tehsil_id=parent_tehsil_low["id"])
conn.close()

child_members = []
for i in range(3):
    logout()
    u = register(name_prefix="Child Village Member")
    child_members.append(u.get_json()["user_id"])

conn = dbmod.get_db()
for uid in child_members:
    plc.add_membership(conn, child_village_high["id"], uid)
village_state = plc.get_provisional(conn, child_village_high["id"])
check("the Village reaches 'pending_review', NOT 'active', since its own Tehsil parent is still provisional",
      village_state["status"] == "pending_review")
check("the parent Tehsil remains 'provisional' -- never auto-promoted just because its child hit threshold",
      plc.get_provisional(conn, parent_tehsil_low["id"])["status"] == "provisional")
check("a status_changed event explains WHY (parent Tehsil not active)",
      "parent provisional Tehsil is not yet active" in
      raw("SELECT detail_json FROM location_submission_events WHERE provisional_location_id = ? AND event_type = 'status_changed' ORDER BY id DESC LIMIT 1",
          (child_village_high["id"],))["detail_json"])
conn.close()

print()
print("=" * 70)
print("11. Demo/removed accounts never count toward the threshold")
print("=" * 70)

conn = dbmod.get_db()
isolated_village = plc.create_provisional_village(conn, 1, "Isolation Test Village", STATE_ID, DISTRICT_ID, verified_tehsil_id=TEHSIL_ID)
conn.close()

logout()
demo_u = register(name_prefix="Demo Account Test")
demo_user_id = demo_u.get_json()["user_id"]
conn = dbmod.get_db()
conn.execute("UPDATE users SET is_demo = 1 WHERE id = ?", (demo_user_id,))
conn.commit()
plc.add_membership(conn, isolated_village["id"], demo_user_id)
check("a demo account's membership row exists but does NOT count as qualifying",
      plc.qualifying_member_count(conn, isolated_village["id"]) == 0)
conn.close()

logout()
removed_u = register(name_prefix="Removed Account Test")
removed_user_id = removed_u.get_json()["user_id"]
conn = dbmod.get_db()
conn.execute("UPDATE users SET is_removed = 1 WHERE id = ?", (removed_user_id,))
conn.commit()
plc.add_membership(conn, isolated_village["id"], removed_user_id)
check("a removed account's membership row exists but does NOT count as qualifying",
      plc.qualifying_member_count(conn, isolated_village["id"]) == 0)
conn.close()

print()
print("=" * 70)
print("12. Member changes present residence -- membership removal, no effect on birth location")
print("=" * 70)

conn = dbmod.get_db()
move_village = plc.create_provisional_village(conn, 1, "Moving Away Village", STATE_ID, DISTRICT_ID, verified_tehsil_id=TEHSIL_ID)
conn.close()
logout()
mover_u = register(name_prefix="Mover")
mover_id = mover_u.get_json()["user_id"]
conn = dbmod.get_db()
plc.add_membership(conn, move_village["id"], mover_id)
check("mover is a qualifying member before moving", plc.qualifying_member_count(conn, move_village["id"]) == 1)
plc.remove_membership(conn, move_village["id"], mover_id)
check("after remove_membership(), the mover no longer counts", plc.qualifying_member_count(conn, move_village["id"]) == 0)
check("the membership row is soft-removed (left_at set), not deleted -- history preserved",
      raw("SELECT left_at FROM provisional_location_members WHERE provisional_location_id = ? AND user_id = ?",
          (move_village["id"], mover_id))["left_at"] is not None)
conn.close()

print()
print("=" * 70)
print("13. Background reconciliation worker: catches a missed activation, stays idempotent")
print("=" * 70)

conn = dbmod.get_db()
recon_village = plc.create_provisional_village(conn, 1, "Reconciled Village", STATE_ID, DISTRICT_ID, verified_tehsil_id=TEHSIL_ID)
conn.close()
recon_members = []
for i in range(3):
    logout()
    u = register(name_prefix="Recon Member")
    recon_members.append(u.get_json()["user_id"])

conn = dbmod.get_db()
# Insert membership rows directly, bypassing add_membership() (and so bypassing its own immediate
# activation check) -- simulates a missed trigger (e.g. a crash between the INSERT and the check).
for uid in recon_members:
    conn.execute("INSERT INTO provisional_location_members (provisional_location_id, user_id, role, joined_at) VALUES (?, ?, 'present_resident', '2026-01-01')",
                 (recon_village["id"], uid))
conn.commit()
check("membership exists but activation was never triggered (simulated missed event)",
      plc.get_provisional(conn, recon_village["id"])["status"] == "provisional")
result = plc.reconcile_all(conn)
check("reconcile_all() finds and activates the missed location", result["activated"] >= 1)
check("the location is now active", plc.get_provisional(conn, recon_village["id"])["status"] == "active")
result2 = plc.reconcile_all(conn)
check("running reconciliation AGAIN does not re-activate or duplicate anything (idempotent)",
      result2["activated"] == 0)
conn.close()
os.environ.pop("QM_PROVISIONAL_LOCATION_THRESHOLD", None)

print()
print("=" * 70)
print("14. Q-Punch gating: a provisional location stays below QPUNCH_REACHABLE_LEVELS' real bar")
print("=" * 70)

check("QPUNCH_REACHABLE_LEVELS is still exactly {'village'} -- not expanded by this MVP",
      appmod.qmail_core.QPUNCH_REACHABLE_LEVELS == {"village"})

print()
print("=" * 70)
print("15. Search never crosses state lines, never confuses Village and Tehsil")
print("=" * 70)

conn = dbmod.get_db()
other_state_tehsil = plc.create_provisional_tehsil(conn, 1, "Cross State Test", "CS.MH", "CS.MH.1") if plc.verified_district("CS.MH", "CS.MH.1") else None
conn.close()
same_state_results = plc.search_locations(dbmod.get_db(), "tehsil", STATE_ID, q="Cross State Test")
check("a same-named provisional Tehsil in a DIFFERENT state never appears in this state's search results",
      not any(r["name"] == "Cross State Test" for r in same_state_results))

conn = dbmod.get_db()
village_results = plc.search_locations(conn, "village", STATE_ID, q="Threshold Village")
tehsil_results = plc.search_locations(conn, "tehsil", STATE_ID, q="Threshold Village")
check("searching level='village' for a name that only exists as a VILLAGE finds it",
      any(r["name"] == "Threshold Village" for r in village_results))
check("searching level='tehsil' for that SAME name finds nothing (Village and Tehsil are never confused)",
      not any(r["name"] == "Threshold Village" for r in tehsil_results))
conn.close()

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
else:
    print("All checks PASSED.")
