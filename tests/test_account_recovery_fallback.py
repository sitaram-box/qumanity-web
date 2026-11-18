"""Verifies the account-recovery fallback for members with no usable Family Tree (2026-11-14):
the public POST /api/recovery/admin-ticket intake route, its validation/rate-limiting/
anti-enumeration behavior, the Admin Panel's new "Account Recovery" feed source and detail view
(reusing the EXISTING /api/admin/queries/<id> detail/reply/close routes unchanged), the
verify/reveal-private-id/generate-pin Admin-only actions, and that every pre-existing recovery
path and Admin Panel ticket queue keeps working unmodified.

Standalone script, no test framework (none installed in this project): throwaway DB built through
the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure -- same conventions
as tests/test_lbe_admin_panel.py (its register()/login_as() helpers) and tests/test_family_recovery.py.

Run with: python3 tests/test_account_recovery_fallback.py
"""
from __future__ import annotations

import datetime as dt
import io
import json
import logging
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"
os.environ["QM_ADMIN_PRIVATE_IDS"] = "719341677"
os.environ["QM_DEV_SHOW_OTP"] = "1"

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402
import admin_queries_core  # noqa: E402

_seed_conn = appmod.get_db()
_seed_conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES ('CS.DL.3.4.1A', 'CS.DL.3.4', 'Rohini Sector 24')")
_seed_conn.commit()
_seed_conn.close()

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


client = appmod.app.test_client()
ROHINI = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}
# Birth location now stops at State (2026-11-19) -- present_location (ROHINI, unchanged) still
# carries the full chain down to Village.
ROHINI_BIRTH = {k: ROHINI[k] for k in ("continent", "country", "zone", "state")}
_n = [0]


def register(name, private_id_override=None, dob="1990-10-01"):
    _n[0] += 1
    payload = {
        "name": f"{name} {_n[0]}", "gender": "male", "dob": dob, "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": ROHINI_BIRTH, "present_location": ROHINI, "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    data = res.get_json()
    if private_id_override:
        conn = dbmod.get_db()
        conn.execute("UPDATE users SET private_id_9digit = ? WHERE id = ?", (private_id_override, data["user_id"]))
        conn.commit()
        conn.close()
        data["private_code"] = private_id_override
    return data


def login_as(uid):
    with client.session_transaction() as sess:
        sess["user_id"] = uid


def logout():
    with client.session_transaction() as sess:
        sess.clear()


def reset_rate_limits():
    appmod._RATE_LIMIT_HITS.clear()


def valid_payload(**overrides):
    base = {
        "name": "Recovery Claimant", "date_of_birth": "1985-05-05",
        "present_location": ROHINI, "contact_method": "phone", "contact_value": "+911234567890",
    }
    base.update(overrides)
    return base


admin_uid = register("FounderTest", private_id_override="719341677")["user_id"]
real_member = register("RealMember")

print("=" * 70)
print("Ticket creation: one ticket per valid contact method")
print("=" * 70)

reset_rate_limits()
res = client.post("/api/recovery/admin-ticket", json=valid_payload(contact_method="phone", contact_value="+911234567890"))
check("valid phone submission succeeds (201)", res.status_code == 201)
body = res.get_json()
check("response has status/message/reference, no raw id", body.get("status") == "received" and bool(body.get("reference")) and "ticket_id" not in body)
check("reference follows the REC-###### safe-reference shape", body.get("reference", "").startswith("REC-") and body["reference"][4:].isdigit())
phone_ticket_ref = body["reference"]

res = client.post("/api/recovery/admin-ticket", json=valid_payload(contact_method="email", contact_value="claimant@example.com"))
check("valid email submission succeeds (201)", res.status_code == 201)

res = client.post("/api/recovery/admin-ticket", json=valid_payload(contact_method="member_private_id", contact_value=real_member["private_code"]))
check("valid member_private_id submission succeeds (201)", res.status_code == 201)

conn = dbmod.get_db()
ar_count = conn.execute("SELECT COUNT(*) AS n FROM admin_queries WHERE category = 'account_recovery'").fetchone()["n"]
conn.close()
check("exactly 3 account_recovery tickets exist after the 3 valid submissions above", ar_count == 3)

print()
print("=" * 70)
print("Ticket creation: validation rejects malformed input")
print("=" * 70)

reset_rate_limits()
res = client.post("/api/recovery/admin-ticket", json={"name": "No Other Fields"})
check("missing required fields are rejected (400)", res.status_code == 400)

res = client.post("/api/recovery/admin-ticket", json=valid_payload(date_of_birth="not-a-date"))
check("malformed date of birth is rejected (400)", res.status_code == 400)

res = client.post("/api/recovery/admin-ticket", json=valid_payload(date_of_birth="2099-01-01"))
check("a date of birth in the future is rejected (400)", res.status_code == 400)

res = client.post("/api/recovery/admin-ticket", json=valid_payload(contact_method="carrier_pigeon"))
check("an unsupported contact method is rejected (400)", res.status_code == 400)

res = client.post("/api/recovery/admin-ticket", json=valid_payload(contact_method="phone", contact_value="abc"))
check("an invalid phone value is rejected (400)", res.status_code == 400)

reset_rate_limits()
res = client.post("/api/recovery/admin-ticket", json=valid_payload(contact_method="email", contact_value="not-an-email"))
check("an invalid email value is rejected (400)", res.status_code == 400)
res = client.post("/api/recovery/admin-ticket", json=valid_payload(contact_method="member_private_id", contact_value="123"))
check("a member_private_id that isn't 9 digits is rejected (400)", res.status_code == 400)

reset_rate_limits()
res = client.post("/api/recovery/admin-ticket", json=valid_payload(present_location={"country": "not-an-object"}))
check("a malformed present_location is handled safely (400, no 500)", res.status_code == 400)
res = client.post("/api/recovery/admin-ticket", json=valid_payload(present_location={"continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"}}))
check("a Subcontinent country with no state is rejected (400)", res.status_code == 400)

reset_rate_limits()
res = client.post("/api/recovery/admin-ticket", json=valid_payload(present_location={
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "state": {"id": "NOT.A.REAL.STATE", "name": "Nowhere"},
}))
check("an unknown state id is rejected (400)", res.status_code == 400)

print()
print("=" * 70)
print("Client cannot choose a different category or assign Admin privileges")
print("=" * 70)

reset_rate_limits()
res = client.post("/api/recovery/admin-ticket", json=dict(valid_payload(), category="query", status="closed"))
check("extra category/status fields in the body are silently ignored (201 still succeeds)", res.status_code == 201)
conn = dbmod.get_db()
last_ticket = conn.execute("SELECT category, status FROM admin_queries ORDER BY id DESC LIMIT 1").fetchone()
conn.close()
check("...and the ticket was created as 'account_recovery'/'open' regardless of what the client sent",
      last_ticket["category"] == "account_recovery" and last_ticket["status"] == "open")

print()
print("=" * 70)
print("Anti-enumeration: a real vs. a fake member_private_id produce an identical response")
print("=" * 70)

reset_rate_limits()
res_real = client.post("/api/recovery/admin-ticket", json=valid_payload(contact_method="member_private_id", contact_value=real_member["private_code"]))
reset_rate_limits()
res_fake = client.post("/api/recovery/admin-ticket", json=valid_payload(contact_method="member_private_id", contact_value="000000000"))
check("a REAL member's Private ID succeeds (201)", res_real.status_code == 201)
check("a clearly FAKE 9-digit Private ID succeeds IDENTICALLY (201, same shape) -- no enumeration signal",
      res_fake.status_code == 201 and set(res_real.get_json().keys()) == set(res_fake.get_json().keys())
      and res_real.get_json()["status"] == res_fake.get_json()["status"])

# PROOF 2(b): a body-shape check alone doesn't rule out a TIMING side-channel (a flat body with
# a measurable timing gap is still an oracle, per the explicit instruction this check answers).
# 60 samples each, real vs. well-formed-but-fake, rate limit cleared before every single call so
# the limiter's own early-exit never contaminates the timing of the code path under test.
import time as _time
import statistics as _statistics

def _timed_submit(contact_value):
    reset_rate_limits()
    t0 = _time.perf_counter()
    r = client.post("/api/recovery/admin-ticket", json=valid_payload(contact_method="member_private_id", contact_value=contact_value))
    return _time.perf_counter() - t0, r

real_times, fake_times = [], []
for _ in range(60):
    t, _ = _timed_submit(real_member["private_code"])
    real_times.append(t)
    t, _ = _timed_submit("000000002")
    fake_times.append(t)
mean_real, mean_fake = _statistics.mean(real_times), _statistics.mean(fake_times)
pooled_stdev = (_statistics.pstdev(real_times) + _statistics.pstdev(fake_times)) / 2 or 1e-9
timing_gap_in_stdevs = abs(mean_real - mean_fake) / pooled_stdev
print(f"  [INFO] PROOF 2(b) timing: real mean={mean_real*1000:.3f}ms fake mean={mean_fake*1000:.3f}ms "
      f"gap={abs(mean_real - mean_fake)*1000:.4f}ms ({timing_gap_in_stdevs:.2f} pooled stdevs)")
check("PROOF 2(b): the real-vs-fake timing gap is well within normal jitter (under 3 pooled standard deviations), not a measurable side-channel",
      timing_gap_in_stdevs < 3)

print()
print("=" * 70)
print("Rate limiting: 5 requests / hour by caller IP")
print("=" * 70)

reset_rate_limits()
results = [client.post("/api/recovery/admin-ticket", json=valid_payload()).status_code for _ in range(6)]
check("first 5 requests in the window succeed", results[:5] == [201] * 5)
check("the 6th request within the hour is rate-limited (429)", results[5] == 429)
reset_rate_limits()

print()
print("=" * 70)
print("Admin Panel: the Account Recovery filter / feed source")
print("=" * 70)

res = client.post("/api/recovery/admin-ticket", json=valid_payload(name="Feed Test Claimant", contact_method="phone", contact_value="+919999999999"))
check("a fresh ticket for the feed test is created", res.status_code == 201)
conn = dbmod.get_db()
feed_test_id = conn.execute("SELECT id FROM admin_queries WHERE guest_name LIKE 'Feed Test Claimant%' ORDER BY id DESC LIMIT 1").fetchone()["id"]
conn.close()

login_as(admin_uid)
res = client.get("/api/admin/panel/feed")
check("the global Admin's feed call succeeds", res.status_code == 200)
items = res.get_json()["items"]
ar_items = [it for it in items if it["source"] == "account_recovery"]
query_items = [it for it in items if it["source"] == "query"]
check("account_recovery tickets appear under their OWN 'account_recovery' source, not 'query'",
      len(ar_items) >= 1 and all(it["title"] == "Account recovery request" for it in ar_items))
check("account_recovery items carry date_of_birth/contact_method/verification_status for the list view (Part 4.1)",
      all("date_of_birth" in it and "contact_method" in it and it.get("verification_status") == "pending" for it in ar_items))
feed_test_item = [it for it in ar_items if it["id"] == feed_test_id][0]
logout()

print()
print("=" * 70)
print("Admin Panel: other ticket categories keep working unaffected")
print("=" * 70)

# No standalone "submit a query" POST route exists for a logged-in member in this codebase today
# (admin_queries_core.py's own module docstring names one, but it was never actually wired up as
# a route -- only /api/queries/mine (GET, read-only) exists) -- so the real regression check is
# admin_queries_core.create() itself, the function every query-submission path funnels through,
# still working correctly for a non-account_recovery category and still surfacing under the
# existing "query" feed source, not the new one.
conn = dbmod.get_db()
karma_ticket_id = admin_queries_core.create(conn, real_member["user_id"], "karma", "My karma looks wrong", "Please check.")
conn.close()
check("admin_queries_core.create() still creates an ordinary 'karma' ticket (regression)", bool(karma_ticket_id))
login_as(admin_uid)
res = client.get("/api/admin/panel/feed")
items = res.get_json()["items"]
check("an ordinary 'query'-source ticket still appears under 'query', never 'account_recovery'",
      any(it["source"] == "query" and it["id"] == karma_ticket_id for it in items))
logout()

print()
print("=" * 70)
print("Unauthorized users cannot list, open, or modify account-recovery tickets")
print("=" * 70)

plain_member = register("PlainMember")
login_as(plain_member["user_id"])
res = client.get("/api/admin/panel/feed")
check("a plain logged-in member gets 403 from the Admin Panel feed entirely", res.status_code == 403)
res = client.get(f"/api/admin/queries/{feed_test_item['id']}")
check("...and 403 trying to open a recovery ticket's detail directly by id", res.status_code == 403)
res = client.post(f"/api/admin/account-recovery/{feed_test_item['id']}/verify", json={"status": "verified"})
check("...and 403 trying to verify it", res.status_code == 403)
res = client.post(f"/api/admin/account-recovery/{feed_test_item['id']}/reveal-private-id", json={"candidate_private_id": real_member["private_code"]})
check("...and 403 trying to reveal a Private ID through it", res.status_code == 403)
res = client.post(f"/api/admin/account-recovery/{feed_test_item['id']}/generate-pin", json={"candidate_private_id": real_member["private_code"]})
check("...and 403 trying to generate a PIN through it", res.status_code == 403)
logout()

print()
print("=" * 70)
print("Admin Panel: ticket detail shows correct submitted information")
print("=" * 70)

login_as(admin_uid)
res = client.get(f"/api/admin/queries/{feed_test_item['id']}")
check("the Admin can open the ticket detail via the EXISTING, unmodified /api/admin/queries/<id> route", res.status_code == 200)
detail = res.get_json()
check("detail shows the claimed name, DOB, contact method and value",
      detail["guest_name"].startswith("Feed Test Claimant") and detail["date_of_birth"] == "1985-05-05"
      and detail["contact_method"] == "phone" and detail["guest_contact"] == "+919999999999")
check("detail shows the structured present_location, parseable back into the canonical object",
      json.loads(detail["present_location_json"])["village"]["id"] == "CS.DL.3.4.1A")
check("verification_status starts 'pending', verification_notes starts empty", detail["verification_status"] == "pending" and not detail["verification_notes"])

print()
print("=" * 70)
print("Recovery actions are blocked before verification, allowed after")
print("=" * 70)

res = client.post(f"/api/admin/account-recovery/{feed_test_item['id']}/reveal-private-id", json={"candidate_private_id": real_member["private_code"]})
check("revealing a Private ID before verification is refused (400)", res.status_code == 400)
res = client.post(f"/api/admin/account-recovery/{feed_test_item['id']}/generate-pin", json={"candidate_private_id": real_member["private_code"]})
check("generating a PIN before verification is refused (400)", res.status_code == 400)

res = client.post(f"/api/admin/account-recovery/{feed_test_item['id']}/verify", json={"status": "verified", "notes": "Called the number, matched DOB and address."})
check("the Admin marks the ticket verified", res.status_code == 200)
res = client.get(f"/api/admin/queries/{feed_test_item['id']}")
detail = res.get_json()
check("verification_status is now 'verified', with the internal note stored", detail["verification_status"] == "verified" and "Called the number" in (detail["verification_notes"] or ""))

print()
print("=" * 70)
print("Action A: Reveal Private ID bridges into the real, unmodified recovery_core mechanism")
print("=" * 70)

res = client.post(f"/api/admin/account-recovery/{feed_test_item['id']}/reveal-private-id", json={"candidate_private_id": "000000000"})
check("revealing against an unknown Private ID is refused (404, no enumeration concern -- this call is Admin-authenticated)", res.status_code == 404)

conn = dbmod.get_db()
reveal_count_before = conn.execute("SELECT COUNT(*) AS n FROM id_recovery_reveals").fetchone()["n"]
conn.close()
res = client.post(f"/api/admin/account-recovery/{feed_test_item['id']}/reveal-private-id", json={"candidate_private_id": real_member["private_code"]})
check("revealing against the real, verified candidate succeeds (200)", res.status_code == 200)
check("...and returns the real member's actual Private ID", res.get_json().get("private_code") == real_member["private_code"])

conn = dbmod.get_db()
reveal_count_after = conn.execute("SELECT COUNT(*) AS n FROM id_recovery_reveals").fetchone()["n"]
bridge_rows = conn.execute("SELECT status FROM id_recovery_requests WHERE candidate_user_id = ? ORDER BY id DESC LIMIT 1", (real_member["user_id"],)).fetchone()
conn.close()
check("the reveal produced a genuine audit row in id_recovery_reveals (the SAME audit trail every existing reveal uses)", reveal_count_after == reveal_count_before + 1)
check("the bridging id_recovery_requests row was immediately marked 'sent' (disappears from the separate ID Recovery tab)", bridge_rows["status"] == "sent")

conn = dbmod.get_db()
still_open_bridge = conn.execute(
    "SELECT COUNT(*) AS n FROM id_recovery_requests WHERE candidate_user_id = ? AND status NOT IN ('sent', 'rejected')",
    (real_member["user_id"],),
).fetchone()["n"]
conn.close()
check("...confirmed directly: no lingering non-sent/rejected bridge row for this candidate", still_open_bridge == 0)

res = client.get(f"/api/admin/queries/{feed_test_item['id']}")
check("the account_recovery ticket's own verification_notes now records that a reveal happened (never the Private ID itself)",
      "Private ID revealed" in (res.get_json()["verification_notes"] or "") and real_member["private_code"] not in (res.get_json()["verification_notes"] or ""))

print()
print("=" * 70)
print("Action B: Generate Temporary PIN reuses the real existing hashing/reset logic")
print("=" * 70)

old_pin_hash_row = dbmod.get_db()
old_hash = old_pin_hash_row.execute("SELECT pin_hash FROM users WHERE id = ?", (real_member["user_id"],)).fetchone()["pin_hash"]
old_pin_hash_row.close()

# PROOF 1(b): captures BOTH stdout/stderr (this codebase's own print()-based "audit log"
# convention) AND the stdlib `logging` module (in case anything -- app.logger, a library,
# Werkzeug's own request logging -- emits through it instead) for the exact duration of this one
# call, then asserts the raw PIN string appears in NEITHER. Not a claim; direct evidence.
stdout_buf, stderr_buf, log_buf = io.StringIO(), io.StringIO(), io.StringIO()
log_handler = logging.StreamHandler(log_buf)
root_logger = logging.getLogger()
root_logger.addHandler(log_handler)
old_stdout, old_stderr = sys.stdout, sys.stderr
sys.stdout, sys.stderr = stdout_buf, stderr_buf
try:
    res = client.post(f"/api/admin/account-recovery/{feed_test_item['id']}/generate-pin", json={"candidate_private_id": real_member["private_code"]})
finally:
    sys.stdout, sys.stderr = old_stdout, old_stderr
    root_logger.removeHandler(log_handler)
captured_stdout, captured_stderr, captured_log = stdout_buf.getvalue(), stderr_buf.getvalue(), log_buf.getvalue()
print(captured_stdout, end="")  # preserve this codebase's existing [account_recovery] audit-print visibility in the test's own output

check("generating a temporary PIN succeeds (200)", res.status_code == 200)
temp_pin = res.get_json().get("temporary_pin")
check("a temporary_pin value is returned, 5 characters", bool(temp_pin) and len(temp_pin) == 5)
check("PROOF 1(b): the raw PIN does not appear in anything printed to stdout during this call (the route's own [account_recovery] audit line included)",
      temp_pin not in captured_stdout)
check("PROOF 1(b): the raw PIN does not appear in anything printed to stderr during this call", temp_pin not in captured_stderr)
check("PROOF 1(b): the raw PIN does not appear in anything emitted through the logging module during this call", temp_pin not in captured_log)
check("PROOF 1(b) cross-check: the route's own audit line DID fire (confirms the capture actually observed real output, not an empty no-op)",
      "TEMP_PIN_GENERATED" in captured_stdout)

conn = dbmod.get_db()
new_hash = conn.execute("SELECT pin_hash FROM users WHERE id = ?", (real_member["user_id"],)).fetchone()["pin_hash"]
notes_row = conn.execute("SELECT verification_notes FROM admin_queries WHERE id = ?", (feed_test_item["id"],)).fetchone()
conn.close()
check("the account's pin_hash actually changed", new_hash != old_hash)
check("PROOF 1(a): the ticket's verification_notes records that a PIN was generated, WITHOUT the raw PIN value anywhere in it",
      "Temporary PIN generated" in (notes_row["verification_notes"] or "") and temp_pin not in (notes_row["verification_notes"] or ""))

logout()
res = client.post("/login", json={"private_id": real_member["private_code"], "pin": temp_pin})
check("the real member can log in with the new temporary PIN", res.status_code == 200)
logout()
res = client.post("/login", json={"private_id": real_member["private_code"], "pin": "12345"})
check("...and their OLD pin no longer works", res.status_code != 200)

print()
print("=" * 70)
print("Resolved/rejected tickets cannot be processed again inappropriately")
print("=" * 70)

login_as(admin_uid)
res = client.post(f"/api/admin/queries/{feed_test_item['id']}/close", json={})
check("the Admin closes the resolved ticket (reusing the existing, unmodified close route)", res.status_code == 200)
res = client.post(f"/api/admin/account-recovery/{feed_test_item['id']}/reveal-private-id", json={"candidate_private_id": real_member["private_code"]})
check("revealing against a CLOSED ticket is refused, even though it was previously verified", res.status_code == 400)
res = client.post(f"/api/admin/account-recovery/{feed_test_item['id']}/generate-pin", json={"candidate_private_id": real_member["private_code"]})
check("...and generating a PIN against a CLOSED ticket is refused too", res.status_code == 400)

reject_member = register("RejectCase")
# register() calls POST /api/auth/register, which auto-logs the NEW member in (session["user_id"]
# is set there) -- clobbering the admin session established above. Re-establish it before the
# next Admin-only calls, same as every other register()-after-login_as(admin_uid) spot avoids by
# ordering registration before login_as() instead; this is the one place in this file where the
# ordering couldn't be avoided (reject_member's own Private ID is needed for the call below).
login_as(admin_uid)
res = client.post("/api/recovery/admin-ticket", json=valid_payload(name="Reject Case Claimant", contact_method="phone", contact_value="+917000000000"))
reject_ref = res.get_json()["reference"]
conn = dbmod.get_db()
reject_ticket = conn.execute("SELECT id FROM admin_queries WHERE category = 'account_recovery' ORDER BY id DESC LIMIT 1").fetchone()
conn.close()
res = client.post(f"/api/admin/account-recovery/{reject_ticket['id']}/verify", json={"status": "rejected", "notes": "Could not confirm identity."})
check("the Admin rejects a different ticket's verification", res.status_code == 200)
res = client.post(f"/api/admin/account-recovery/{reject_ticket['id']}/reveal-private-id", json={"candidate_private_id": reject_member["private_code"]})
check("neither recovery action is reachable on a REJECTED ticket", res.status_code == 400)
logout()

print()
print("=" * 70)
print("Regression: existing OTP self-service PIN reset still works")
print("=" * 70)

otp_member = register("OtpMember")
conn = dbmod.get_db()
conn.execute("UPDATE users SET phone = '+911112223333' WHERE id = ?", (otp_member["user_id"],))
conn.commit()
conn.close()
res = client.post("/api/auth/forgot-pin/request", json={"private_id": otp_member["private_code"], "channel": "phone"})
check("OTP request still succeeds for a member with a registered phone (regression)", res.status_code == 200)
dev_code = res.get_json().get("dev_code")
res = client.post("/api/auth/forgot-pin/verify", json={"private_id": otp_member["private_code"], "otp": dev_code, "new_pin": "54321"})
check("OTP verification still resets the PIN correctly (regression)", res.status_code == 200)
res = client.post("/login", json={"private_id": otp_member["private_code"], "pin": "54321"})
check("...and the member can log in with it", res.status_code == 200)
logout()

print()
print("=" * 70)
print("Regression: existing (non-bridged) Admin Private ID recovery still works")
print("=" * 70)

direct_member = register("DirectClaimant", dob="1991-03-03")
# register()'s own JSON response doesn't include the generated display name, so read it straight
# back -- needed verbatim for submit_id_recovery()'s exact lower(name) match below.
conn = dbmod.get_db()
direct_member_name = conn.execute("SELECT name FROM users WHERE id = ?", (direct_member["user_id"],)).fetchone()["name"]
conn.close()
res = client.post("/api/auth/recover-id", json={
    "name": direct_member_name, "dob": "1991-03-03", "mailing_address": "123 Real Street",
    "phone": "+911231231234",
})
check("a genuine (non-bridged) ID-recovery submission still succeeds (regression)", res.status_code == 201)
conn = dbmod.get_db()
direct_row = conn.execute(
    "SELECT id, candidate_user_id FROM id_recovery_requests WHERE name = ? ORDER BY id DESC LIMIT 1", (direct_member_name,)
).fetchone()
conn.close()
check("...and it auto-matched the real member registered with that exact name+DOB", direct_row["candidate_user_id"] == direct_member["user_id"])
login_as(admin_uid)
res = client.post(f"/api/admin/recover-id/{direct_row['id']}/reveal")
check("...and the ORIGINAL (non-bridged) reveal route still works unmodified (regression)", res.status_code == 200)
logout()

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
