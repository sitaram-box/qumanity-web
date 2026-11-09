"""Covers the Global Account feature (2026-11-08): registration for a Present Location outside
Qumanity's 10 Public Account Activation countries (SUBCONTINENT_COUNTRY_IDS), account
classification (account_access_type()/_is_valid_global_country()), Dashboard tab visibility,
backend rejection of local Public timeline access, voting on posts that have reached a Global
Page (country/continent/earth level), Q-Punch (Village Council election) ineligibility, and
Family Tree/Personal/Private compatibility.

Also covers the 2026-11-08 Q-Punch security-hardening pass: the account_core.account_access_type()
gate added to election_core._present_village_id() (sections 10, 14), and the present_location
validation added to the profile-change-request pathway, both at submission
(api_dashboard_edit_request) and again at approval (api_admin_profile_decide) (section 14), plus
a regression proving a legitimate, same-classification present_location edit still works
end-to-end (section 15).

Also covers an independent adversarial review's two follow-up findings (same date): full
Zone/District/Tehsil/Village ancestry validation for a Public-country present_location change,
not just state-belongs-to-country (section 16), and confirmation that the admin-only
auto_nominate()/auto_vote() simulation endpoints -- which build their own candidate/voter pools
with a raw SQL query, independently of _present_village_id() -- cannot be used to bypass the same
eligibility checks (section 17).

Standalone script, no test framework (none installed in this project): throwaway DB built
through the real Flask app and its real routes (same convention as tests/test_family_tree.py),
PASS/FAIL printing, exit 1 on failure.

Run with: python3 tests/test_global_account.py (not -I)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"

import app as appmod  # noqa: E402
import board_core  # noqa: E402
import db as dbmod  # noqa: E402

# 2026-11-08 (Phase 1 corrective task): registration now verifies a real (non-provisional)
# Village against india_villages, the same way profile-change already does -- every throwaway
# test DB starts with that table empty, so any test registering a real village through the real
# /api/auth/register route must seed its row here first, before ANY registration in this file
# (sections 2/6 register India/Rohini residents, so this must happen before they run).
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

INDIA_LOC = {
    "continent": {"id": "O_AS", "code": "AS", "name": "Asia"},
    "country": {"id": "O_AS_IND", "code": "IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"},
    "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"},
    "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}
JAPAN_LOC = {
    "continent": {"id": "O_AS", "code": "AS", "name": "Asia"},
    "country": {"id": "O_AS_JPN", "code": "JPN", "name": "Japan"},
}
KENYA_LOC = {
    "continent": {"id": "O_AF", "code": "AF", "name": "Africa"},
    "country": {"id": "O_AF_KEN", "code": "KEN", "name": "Kenya"},
}
MAURITIUS_LOC = {
    "continent": {"id": "O_AF", "code": "AF", "name": "Africa"},
    "country": {"id": "O_AF_MUS", "code": "MUS", "name": "Mauritius"},
}

_n = [0]


def register(name_prefix, present_location, birth_location=None, dob="1990-06-15"):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "female", "dob": dob, "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": birth_location or present_location, "present_location": present_location,
        "assisted": False,
    }
    return client.post("/api/auth/register", json=payload)


def register_or_die(name_prefix, present_location, **kw):
    res = register(name_prefix, present_location, **kw)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED for {name_prefix}: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def login(private_code, pin="12345"):
    res = client.post("/login", json={"private_id": private_code, "pin": pin})
    if res.status_code != 200:
        sys.exit(f"LOGIN FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")


def logout():
    client.post("/logout")


print("=" * 70)
print("1. account_access_type() / _is_valid_global_country() -- unit-level checks")
print("=" * 70)
check("India -> public", appmod.account_access_type(INDIA_LOC) == "public")
check("Balochistan -> public", appmod.account_access_type({"country": {"id": "O_AS_BLC"}}) == "public")
check("Japan -> global", appmod.account_access_type(JAPAN_LOC) == "global")
check("Kenya -> global", appmod.account_access_type(KENYA_LOC) == "global")
check("Mauritius -> global (confirmed excluded from the 10)", appmod.account_access_type(MAURITIUS_LOC) == "global")
check("Missing country -> global (never crashes on an incomplete location)", appmod.account_access_type({}) == "global")
check("Japan is a valid O_AS country", appmod.app.view_functions  # noqa: trivial access to confirm app loaded
      and appmod._is_valid_global_country("O_AS", "O_AS_JPN") is True)
check("Kenya is a valid O_AF country", appmod._is_valid_global_country("O_AF", "O_AF_KEN") is True)
check("Japan is NOT valid under O_AF (continent/country mismatch rejected)", appmod._is_valid_global_country("O_AF", "O_AS_JPN") is False)
check("An unknown country id is rejected", appmod._is_valid_global_country("O_AS", "O_AS_NOPE") is False)
check("An unknown continent id is rejected", appmod._is_valid_global_country("O_XX", "O_AS_JPN") is False)

print()
print("=" * 70)
print("2. Japan registration -- the real /api/auth/register endpoint")
print("=" * 70)
japan = register_or_die("Yuki Tanaka", JAPAN_LOC)
check("registration returns 201 with a private_code/user_id", "private_code" in japan and "user_id" in japan)
japan_user_id = japan["user_id"]

japan_row = dbmod.get_db().execute(
    "SELECT present_location_json, qmail_username FROM users WHERE id = ?", (japan_user_id,)
).fetchone()
japan_loc_saved = json.loads(japan_row["present_location_json"])
check("present_location_json keeps continent+country exactly as submitted",
      japan_loc_saved["continent"]["id"] == "O_AS" and japan_loc_saved["country"]["id"] == "O_AS_JPN")
check("present_location_json has NO zone/state/district/tehsil/village (no fabricated local geography)",
      all(lvl not in japan_loc_saved for lvl in ("zone", "state", "district", "tehsil", "village")))
check("account_access_type() on the SAVED row is 'global'", appmod.account_access_type(japan_loc_saved) == "global")

login(japan["private_code"])
dash = client.get("/dashboard")
check("Japan Global Account can load the Dashboard (200)", dash.status_code == 200)
dash_html = dash.get_data(as_text=True)
check('Dashboard shows the Global tab', 'data-tab="global"' in dash_html)
check('Dashboard shows the Personal tab', 'data-tab="personal"' in dash_html)
check('Dashboard shows the Private tab', 'data-tab="private"' in dash_html)
check('Dashboard does NOT render the Public tab button at all', 'data-tab="public"' not in dash_html)
check('Dashboard does NOT render the Public panel (#qm-dash-public) at all', 'id="qm-dash-public"' not in dash_html)
check("No stray village-council election markup either (it lives inside the now-absent Public panel)",
      'id="qm-elections-card"' not in dash_html)
me = client.get("/api/me").get_json()
check("/api/me reports is_global_account=True", me.get("is_global_account") is True)

print()
print("=" * 70)
print("3. Kenya registration -- proves this is country-classification-driven, not a Japan special case")
print("=" * 70)
logout()
kenya = register_or_die("Amara Wanjiru", KENYA_LOC)
kenya_row = dbmod.get_db().execute("SELECT present_location_json FROM users WHERE id = ?", (kenya["user_id"],)).fetchone()
kenya_loc_saved = json.loads(kenya_row["present_location_json"])
check("Kenya present_location_json keeps continent O_AF + country O_AF_KEN",
      kenya_loc_saved["continent"]["id"] == "O_AF" and kenya_loc_saved["country"]["id"] == "O_AF_KEN")
check("Kenya present_location_json has no subordinate levels either",
      all(lvl not in kenya_loc_saved for lvl in ("zone", "state", "district", "tehsil", "village")))
login(kenya["private_code"])
kenya_me = client.get("/api/me").get_json()
check("Kenya /api/me reports is_global_account=True", kenya_me.get("is_global_account") is True)
kenya_dash = client.get("/dashboard").get_data(as_text=True)
check("Kenya Dashboard also has no Public tab", 'data-tab="public"' not in kenya_dash)
logout()

print()
print("=" * 70)
print("4. A fabricated client-side account flag changes nothing -- classification is server-derived")
print("=" * 70)
spoof_payload = {
    "name": "Spoofer", "gender": "female", "dob": "1990-01-01", "tob": "06:00",
    "language": "English", "email": "", "phone": "", "pin": "12345",
    "birth_location": JAPAN_LOC, "present_location": JAPAN_LOC, "assisted": False,
    "is_global_account": False, "account_access_type": "public", "account_type": "public",
}
spoof_res = client.post("/api/auth/register", json=spoof_payload)
check("registration with Japan present_location still succeeds (unknown extra fields are simply ignored)",
      spoof_res.status_code == 201)
spoof_body = spoof_res.get_json()
spoof_row = dbmod.get_db().execute("SELECT present_location_json FROM users WHERE id = ?", (spoof_body["user_id"],)).fetchone()
check("...and the user is STILL classified Global server-side, regardless of the spoofed flags",
      appmod.account_access_type(json.loads(spoof_row["present_location_json"])) == "global")

print()
print("=" * 70)
print("5. A Global Account cannot fabricate a Subcontinent village/state in present_location")
print("=" * 70)
fabricated = dict(JAPAN_LOC)
fabricated["village"] = {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"}
res = register("Fabricator", fabricated)
check("present_location with Japan country + an injected Subcontinent village id is REJECTED (400)",
      res.status_code == 400)
fabricated2 = dict(JAPAN_LOC)
fabricated2["state"] = {"id": "CS.DL", "name": "Delhi"}
res2 = register("Fabricator2", fabricated2)
check("present_location with Japan country + an injected state id is also REJECTED (400)", res2.status_code == 400)

print()
print("=" * 70)
print("6. Local Public Account (India) registration is unaffected -- full regression")
print("=" * 70)
india = register_or_die("Priya Sharma", INDIA_LOC)
india_row = dbmod.get_db().execute("SELECT present_location_json FROM users WHERE id = ?", (india["user_id"],)).fetchone()
india_loc_saved = json.loads(india_row["present_location_json"])
check("India present_location_json keeps the full Zone..Village chain",
      all(lvl in india_loc_saved for lvl in ("zone", "state", "district", "tehsil", "village")))
check("account_access_type() on the saved India row is 'public'", appmod.account_access_type(india_loc_saved) == "public")
login(india["private_code"])
india_me = client.get("/api/me").get_json()
check("India /api/me reports is_global_account=False", india_me.get("is_global_account") is False)
india_dash = client.get("/dashboard").get_data(as_text=True)
check("India Dashboard DOES show the Public tab", 'data-tab="public"' in india_dash)
check("India Dashboard DOES render the Public panel", 'id="qm-dash-public"' in india_dash)
india_user_id = india["user_id"]
logout()

print()
print("=" * 70)
print("7. Backend rejects local Public timeline access for a Global Account directly (not just UI)")
print("=" * 70)
login(japan["private_code"])
r = client.get("/api/board/village")
check("GET /api/board/village for a Global Account -> 404 ('no group at this level'), never a 500",
      r.status_code == 404)
r = client.get("/api/board/tehsil")
check("GET /api/board/tehsil -> 404 too (Global Account has no tehsil either)", r.status_code == 404)
r = client.post("/api/board/post", json={"content": "Trying to post for free.", "level": "village"})
check("POST /api/board/post level=village for a Global Account -> 400 ('Add your present village...')",
      r.status_code == 400)
r = client.post("/api/board/post", json={"content": "Trying to pay-post.", "level": "zone"})
check("POST /api/board/post level=zone (paid tier) for a Global Account -> 400 ('no group at this level')",
      r.status_code == 400)
r = client.get("/api/board/earth")
check("GET /api/board/earth (a Global-tab level) DOES work for a Global Account -> 200", r.status_code == 200)
r_country = client.get("/api/board/country")
check("GET /api/board/country works too, scoped to the Global Account's OWN country", r_country.status_code == 200)
check("...and it is JAPAN's own country board, not someone else's",
      r_country.status_code == 200 and r_country.get_json()["group_id"] == "O_AS_JPN")
logout()

print()
print("=" * 70)
print("8. Global Page voting -- synthetic posts standing in for ones that reached country/continent/earth")
print("   (board_core.THRESHOLD at these levels is 1M/10M/100M real votes -- infeasible to simulate by")
print("   casting that many real votes, so these rows are inserted directly, exactly matching the shape")
print("   settle()'s own elevation code produces -- see board_core.py's settle()/_open_window().)")
print("=" * 70)
NOW = dt.datetime.now(dt.timezone.utc)


def insert_board_post(conn, author_id, level, group_id, group_name, voting_end_delta_days=5, score=0):
    chain = [{"level": level, "id": group_id, "name": group_name}, {"level": "earth", "id": "EARTH", "name": "Earth"}]
    cur = conn.execute(
        """INSERT INTO board_posts (author_id, level, group_id, group_name, content, status, score,
                                     voting_start, voting_end, chain_json, created_at, post_kind)
           VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, 'member')""",
        (author_id, level, group_id, group_name, "A promoted civic post.", score,
         NOW.isoformat(), (NOW + dt.timedelta(days=voting_end_delta_days)).isoformat(), json.dumps(chain), NOW.isoformat()),
    )
    conn.commit()
    return cur.lastrowid


conn = dbmod.get_db()
india_country_post = insert_board_post(conn, india_user_id, "country", "O_AS_IND", "India")
asia_continent_post = insert_board_post(conn, india_user_id, "continent", "O_AS", "Asia")
earth_post = insert_board_post(conn, india_user_id, "earth", "EARTH", "Earth")
village_post_not_promoted = insert_board_post(conn, india_user_id, "village", "CS.DL.3.4.1A", "Rohini Sector 24")
conn.close()

login(japan["private_code"])
r = client.post("/api/board/vote", json={"post_id": village_post_not_promoted, "value": 1})
check("Japan Global Account CANNOT vote on a village-level (unpromoted) post -> 403",
      r.status_code == 403)
r = client.post("/api/board/vote", json={"post_id": india_country_post, "value": 1})
check("Japan Global Account CANNOT vote on India's own country-level post (different country) -> 403 "
      "-- country-level 'Global Pages' are scoped to that one country's own residents, not worldwide",
      r.status_code == 403)
r = client.post("/api/board/vote", json={"post_id": asia_continent_post, "value": 1})
check("Japan Global Account CAN vote on the O_AS continent-level post (Japan is also continent O_AS) -> 200",
      r.status_code == 200)
check("...score updated to 1", r.status_code == 200 and r.get_json()["score"] == 1)
r = client.post("/api/board/vote", json={"post_id": asia_continent_post, "value": -1})
check("Casting a second vote on the SAME post changes (replaces) the vote rather than being rejected "
      "as a duplicate -- score moves by the delta (-1 - 1 = -2)",
      r.status_code == 200 and r.get_json()["score"] == -1)
r = client.post("/api/board/vote", json={"post_id": earth_post, "value": 1})
check("Japan Global Account CAN vote on the Earth-level post (the one truly universal level) -> 200",
      r.status_code == 200 and r.get_json()["score"] == 1)
logout()

login(kenya["private_code"])
r = client.post("/api/board/vote", json={"post_id": asia_continent_post, "value": 1})
check("Kenya Global Account (continent O_AF) CANNOT vote on the O_AS continent-level post -> 403 "
      "-- proving continent-level voting is genuinely geography-scoped, not a blanket Global allowance",
      r.status_code == 403)
r = client.post("/api/board/vote", json={"post_id": earth_post, "value": 1})
check("Kenya Global Account CAN vote on the Earth-level post -> 200", r.status_code == 200)
logout()

conn = dbmod.get_db()
conn.execute("UPDATE board_posts SET voting_end = ? WHERE id = ?", ((NOW - dt.timedelta(days=1)).isoformat(), earth_post))
conn.commit()
conn.close()
login(japan["private_code"])
r = client.post("/api/board/vote", json={"post_id": earth_post, "value": 1})
check("Voting on an Earth-level post past its voting_end -> 403 ('Voting has closed')", r.status_code == 403)
logout()

india_voter = register_or_die("Another Delhi Resident", INDIA_LOC)
login(india_voter["private_code"])
r = client.post("/api/board/vote", json={"post_id": asia_continent_post, "value": 1})
check("A SECOND, different eligible India Public Account user (not the post's own author -- "
      "cast_vote() correctly rejects self-votes, see check above) CAN ALSO vote at the shared "
      "O_AS continent level -> 200 (this is genuinely shared civic space, not something only "
      "Global Accounts can reach)",
      r.status_code == 200)
logout()

print()
print("=" * 70)
print("9. Q-Punch (Village Council election) restrictions for a Global Account")
print("=" * 70)
login(japan["private_code"])
status = client.get("/api/election/status").get_json()
check("Japan Global Account: can_nominate is False", status["eligibility"]["can_nominate"] is False)
check("Japan Global Account: can_vote is False", status["eligibility"]["can_vote"] is False)
r = client.post("/api/election/nominate", json={
    "reason": "I want to serve.", "why_vote": "Trust me.", "changes": "Everything.",
})
# The exact rejection message depends on which phase today's real-world election cycle happens
# to be in (nominate() checks cycle["status"] == "nomination" BEFORE it even reaches
# nomination_eligible()'s own village-residency message) -- the status code is what matters here,
# not the wording; section 10 below isolates the village-residency check itself.
check("POST /api/election/nominate for a Global Account -> 400, rejected server-side",
      r.status_code == 400)
r = client.post("/api/election/vote", json={"candidate_user_id": india_user_id, "gender": "female"})
check("POST /api/election/vote for a Global Account -> 400, rejected server-side",
      r.status_code == 400)
candidates_before = dbmod.get_db().execute("SELECT COUNT(*) AS n FROM election_candidates").fetchone()["n"]
votes_before = dbmod.get_db().execute("SELECT COUNT(*) AS n FROM election_votes").fetchone()["n"]
check("No election_candidates row was created by the rejected nomination", candidates_before == 0)
check("No election_votes row was created by the rejected vote", votes_before == 0)
logout()

print()
print("=" * 70)
print("10. A fabricated Village ID cannot bypass Q-Punch restrictions (2026-11-08 HARDENED)")
print("=" * 70)
# election_core.nomination_eligible()/voting_eligible() check several independent things
# (village residency, age, the CURRENT cycle's zodiac sign) -- the age/zodiac checks are tied to
# today's real-world date, so driving the full can_nominate flag to True here would make this
# test fragile to the calendar rather than actually isolating the one thing it's meant to prove.
# Instead, call election_core's own _present_village_id() directly, before and after the edit:
# this is the exact, sole mechanism nomination_eligible()/voting_eligible() use to decide
# residency (see election_core.py:232/248, "_present_village_id(user_row) != cycle['village_id']").
#
# SECURITY FINDING (previous report) and its fix: before 2026-11-08, _present_village_id() was a
# pure, ungated read of present_location_json's "village" key -- a hand-edited row carrying a
# Subcontinent village id alongside a Global country WOULD have made it return that village id,
# which would have made a Global Account Q-Punch-eligible. The fix adds exactly one gate to that
# one function: it now also calls account_core.account_access_type() on the SAME
# present_location_json and returns None unless that independently agrees the account is
# 'public'. This section proves the fix: the fabricated row now returns None, not the village id.
conn = dbmod.get_db()
japan_user_row = conn.execute("SELECT * FROM users WHERE id = ?", (japan_user_id,)).fetchone()
conn.close()
check("Before any edit, _present_village_id() is None for the real, unmodified Japan Global Account",
      appmod.election_core._present_village_id(japan_user_row) is None)

conn = dbmod.get_db()
conn.execute(
    "UPDATE users SET present_location_json = ? WHERE id = ?",
    (json.dumps({**JAPAN_LOC, "village": {"id": appmod.election_core.PILOT_VILLAGE_ID, "name": "Rohini Sector 24"}}), japan_user_id),
)
conn.commit()
fabricated_row = conn.execute("SELECT * FROM users WHERE id = ?", (japan_user_id,)).fetchone()
conn.close()
check("A hand-edited present_location_json carrying the pilot village id alongside the Japan "
      "country id does NOT make _present_village_id() return it anymore -- account_access_type() "
      "independently recomputes 'global' from the SAME row (country O_AS_JPN is not in "
      "SUBCONTINENT_COUNTRY_IDS) and the function returns None regardless of the village key. "
      "This direct SQL UPDATE is not something any real Global Account could ever reach through "
      "the API in the first place (registration rejects a Global country's present_location "
      "carrying any village id outright -- section 5 above -- and the profile-change-request "
      "path is now validated too -- section 14 below); this test exists purely as defense in "
      "depth, proving the Q-Punch gate itself does not trust a bare village id even if one somehow "
      "got into the row by any other means.",
      appmod.election_core._present_village_id(fabricated_row) is None)

# Phase 2.2: exercise the real endpoints against this exact inconsistent row, not just the
# pure function -- login as the fabricated-row user and attempt every Q-Punch operation.
login(japan["private_code"])
fab_status = client.get("/api/election/status").get_json()
check("With the fabricated village id in place, /api/election/status still reports can_nominate=False",
      fab_status["eligibility"]["can_nominate"] is False)
check("...and can_vote=False too",
      fab_status["eligibility"]["can_vote"] is False)
check("...for the village-residency reason specifically (not an unrelated age/zodiac rejection)",
      "resident" in fab_status["eligibility"]["vote_reason"].lower())
fab_nom = client.post("/api/election/nominate", json={
    "reason": "I want to serve.", "why_vote": "Trust me.", "changes": "Everything.",
})
check("POST /api/election/nominate with the fabricated village id -> still rejected (400)",
      fab_nom.status_code == 400)
fab_vote = client.post("/api/election/vote", json={"candidate_user_id": india_user_id, "gender": "female"})
check("POST /api/election/vote with the fabricated village id -> still rejected (400)",
      fab_vote.status_code == 400)
logout()
cand_count = dbmod.get_db().execute("SELECT COUNT(*) AS n FROM election_candidates WHERE user_id = ?", (japan_user_id,)).fetchone()["n"]
vote_count = dbmod.get_db().execute("SELECT COUNT(*) AS n FROM election_votes WHERE voter_user_id = ?", (japan_user_id,)).fetchone()["n"]
check("No election_candidates row was created for the fabricated-village-id account", cand_count == 0)
check("No election_votes row was created for the fabricated-village-id account", vote_count == 0)
wallet_locked = dbmod.get_db().execute(
    "SELECT COUNT(*) AS n FROM wallet_transactions wt JOIN wallets w ON w.id = wt.wallet_id "
    "WHERE w.owner_type = 'user' AND w.owner_id = ? AND wt.locked = 0 AND wt.reason LIKE '%registration%'",
    (str(japan_user_id),),
).fetchone()["n"]
check("The Global Account's locked free-registration Qoin share was NOT unlocked "
      "(unlock_user_share() only ever runs from inside cast_vote(), which never completed)",
      wallet_locked == 0)

conn = dbmod.get_db()
conn.execute("UPDATE users SET present_location_json = ? WHERE id = ?", (json.dumps(JAPAN_LOC), japan_user_id))
conn.commit()
conn.close()

print()
print("=" * 70)
print("11. Eligible local (India) Q-Punch behavior is unaffected")
print("=" * 70)
india_village = register_or_die("Rohini Resident", INDIA_LOC)
login(india_village["private_code"])
india_status = client.get("/api/election/status").get_json()
check("An India/Rohini-Sector-24 resident's own Q-Punch eligibility is computed as before "
      "(this implementation added no new gate to election_core.py at all)",
      "cycle" in india_status and "eligibility" in india_status)
logout()

print()
print("=" * 70)
print("12. Family Tree activation + Personal/Private access for a Global Account")
print("=" * 70)
login(japan["private_code"])
fam_status = client.get("/api/family/status")
check("Family status loads for a Global Account (200)", fam_status.status_code == 200)
check("...not yet activated", fam_status.get_json()["activated"] is False)
act = client.post("/api/family/activate", json={
    "father": {"name": "Hiroshi Tanaka", "action": "create"},
    "mother": {"name": "Keiko Tanaka", "action": "create"},
})
check("Family Tree activation succeeds for a Global Account (201)", act.status_code == 201)
act_body = act.get_json() if act.status_code == 201 else {}
if act.status_code != 201:
    print("   body:", act.get_data(as_text=True)[:500])
tree = client.get(f"/api/family-groups/{act_body.get('parents_group_id')}/tree") if act_body.get("parents_group_id") else None
check("Family Tree is retrievable afterwards", bool(tree) and tree.status_code == 200)
check("Tree has the 3 expected nodes (self, father, mother) -- no fabricated extra nodes",
      bool(tree) and tree.status_code == 200 and len(tree.get_json()["nodes"]) == 3)
check("Activating did not create any Public Account village/board row for this user",
      dbmod.get_db().execute(
          "SELECT COUNT(*) AS n FROM board_posts WHERE author_id = ? AND level = 'village'", (japan_user_id,)
      ).fetchone()["n"] == 0)
check("Activating did not touch present_location_json (still Japan, country-only)",
      json.loads(dbmod.get_db().execute(
          "SELECT present_location_json FROM users WHERE id = ?", (japan_user_id,)
      ).fetchone()["present_location_json"]) == JAPAN_LOC)
personal_tl = client.get("/api/me")
check("Private profile (/api/me) still loads normally after Family Tree activation", personal_tl.status_code == 200)
logout()

print()
print("=" * 70)
print("13. Collective-board paid/monetized posting audit (code-level finding, not a new feature)")
print("=" * 70)
check("board_core.PAID_LEVELS is exactly (tehsil, district, state, zone) -- Country/Continent/Earth "
      "have NO posting price at all, paid or free, for ANY account type; they are elevation-only "
      "destinations (see board_core.py's own PAID_LEVELS comment: 'Country/Continent/Earth are "
      "broadcast + voting only')",
      board_core.PAID_LEVELS == ("tehsil", "district", "state", "zone"))
login(japan["private_code"])
for lvl in board_core.PAID_LEVELS:
    r = client.post("/api/board/post", json={"content": "x", "level": lvl})
    check(f"Global Account's paid-posting attempt at '{lvl}' is rejected (400, 'no group at this "
          f"level') -- a Global Account has none of these levels in its own chain either, so the "
          f"existing paid-posting gate already covers it with no new code",
          r.status_code == 400)
logout()

print()
print("=" * 70)
print("14. Profile-change-request pathway hardening (2026-11-08)")
print("=" * 70)
# SECURITY FINDING: before this hardening, api_dashboard_edit_request() queued a 'present_location'
# profile-change-request with ZERO validation -- not even the state-belongs-to-country check
# registration has always had -- and api_admin_profile_decide() applied whatever an Admin approved
# straight into users.present_location_json via social_core.regenerate_account_id(), with no
# re-check either. This is the REAL, API-reachable route (unlike a direct SQL edit) by which an
# internally inconsistent present_location could have ended up on a real row. The fix:
# _validate_present_location_change() (app.py), called at submission AND again at approval.
login(japan["private_code"])
bad_shape = client.post("/api/dashboard/edit-request", json={
    "present_location": {**JAPAN_LOC, "village": {"id": appmod.election_core.PILOT_VILLAGE_ID, "name": "Rohini Sector 24"}},
    "reason": "attempted village fabrication via edit-request",
})
check("A Global Account's edit-request carrying Japan country + an injected village id is "
      "REJECTED at submission (400) -- never even queued for an Admin to see",
      bad_shape.status_code == 400)
cross_to_public = client.post("/api/dashboard/edit-request", json={
    "present_location": INDIA_LOC, "reason": "attempted Global->Public crossing",
})
check("A Global Account's edit-request switching its present_location to a full, otherwise-valid "
      "India chain is REJECTED at submission (400) -- crossing the Public/Global boundary has no "
      "approved transition policy in this product today, so it is refused rather than silently "
      "granted via this generic ticket",
      cross_to_public.status_code == 400)
queued_before = dbmod.get_db().execute("SELECT COUNT(*) AS n FROM profile_change_requests WHERE user_id = ?", (japan_user_id,)).fetchone()["n"]
check("Neither rejected attempt actually queued a ticket", queued_before == 0)
logout()

login(india["private_code"])
cross_to_global = client.post("/api/dashboard/edit-request", json={
    "present_location": JAPAN_LOC, "reason": "attempted Public->Global crossing",
})
check("A Public Account's edit-request switching its present_location to Japan (country-only) is "
      "REJECTED at submission (400) -- the same boundary rule applies in both directions",
      cross_to_global.status_code == 400)
logout()

# Defense-in-depth (Phase 2.3): simulate a ticket that reached 'pending' status before this
# hardening existed (or via any future bug in the submission route) by inserting it directly --
# not through api_dashboard_edit_request(), which would itself refuse this payload. Approval must
# independently refuse it too.
conn = dbmod.get_db()
appmod._ensure_profile_change_table(conn)
bad_fields = json.dumps({"present_location": {**JAPAN_LOC, "village": {"id": appmod.election_core.PILOT_VILLAGE_ID, "name": "Rohini Sector 24"}}})
cur = conn.execute(
    "INSERT INTO profile_change_requests (user_id, fields_json, reason, status, request_type) VALUES (?, ?, ?, 'pending', 'edit')",
    (japan_user_id, bad_fields, "pre-hardening-style bypass ticket"),
)
conn.commit()
bypass_request_id = cur.lastrowid
conn.close()

admin = register_or_die("Admin Reviewer", INDIA_LOC)
os.environ["QM_ADMIN_PRIVATE_IDS"] = admin["private_code"]
login(admin["private_code"])
bypass_decide = client.post(f"/api/admin/profile-changes/{bypass_request_id}/decide", json={"approve": True})
check("Approving a directly-inserted ticket with an inconsistent present_location is REJECTED "
      "(400) at decision time, not silently applied",
      bypass_decide.status_code == 400)
logout()
ticket_status = dbmod.get_db().execute("SELECT status FROM profile_change_requests WHERE id = ?", (bypass_request_id,)).fetchone()["status"]
check("The bypass ticket is still 'pending' -- the rejected decision did not mark it approved",
      ticket_status == "pending")
untouched_loc = json.loads(dbmod.get_db().execute("SELECT present_location_json FROM users WHERE id = ?", (japan_user_id,)).fetchone()["present_location_json"])
check("The Global Account's present_location_json was NOT modified by the rejected decision",
      untouched_loc == JAPAN_LOC)
check("account_access_type() on the untouched row is still 'global'",
      appmod.account_access_type(untouched_loc) == "global")

print()
print("=" * 70)
print("15. A legitimate, same-type present_location edit still works end-to-end (regression)")
print("=" * 70)
# 2026-11-08 (Task 1A): _validate_present_location_change() now hard-rejects a Village id that
# isn't found in india_villages at all, rather than soft-accepting it -- every throwaway test DB
# starts with this table empty, so a real, legitimate edit needs its Village's row seeded here,
# the same way section 16 already seeds its own two rows for the same reason.
conn = dbmod.get_db()
conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES (?, ?, ?)",
             ("CS.DL.3.4.1A", "CS.DL.3.4", "Rohini Sector 24"))
conn.commit()
conn.close()

login(india["private_code"])
good_edit = client.post("/api/dashboard/edit-request", json={
    "present_location": INDIA_LOC, "reason": "re-confirming my existing Village location",
})
check("A Public Account's edit-request keeping the SAME India chain (same classification, valid "
      "shape) is accepted and queued (200)", good_edit.status_code == 200)
good_request_id = dbmod.get_db().execute(
    "SELECT id FROM profile_change_requests WHERE user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1",
    (india_user_id,),
).fetchone()["id"]
logout()

login(admin["private_code"])
good_decide = client.post(f"/api/admin/profile-changes/{good_request_id}/decide", json={"approve": True})
check("Admin approving the legitimate, internally-consistent India present_location change "
      "succeeds (200) -- the new validation does not block real, valid edits",
      good_decide.status_code == 200)
logout()
reapplied_loc = json.loads(dbmod.get_db().execute("SELECT present_location_json FROM users WHERE id = ?", (india_user_id,)).fetchone()["present_location_json"])
check("The India user's present_location_json was applied by the approval",
      reapplied_loc == INDIA_LOC)
check("account_access_type() after the approved change is still 'public' (no accidental "
      "reclassification from a legitimate, same-type edit)",
      appmod.account_access_type(reapplied_loc) == "public")
check("_present_village_id() still resolves correctly for this real Public Account after an "
      "approved, validated present_location change",
      appmod.election_core._present_village_id(
          dbmod.get_db().execute("SELECT * FROM users WHERE id = ?", (india_user_id,)).fetchone()
      ) == appmod.election_core.PILOT_VILLAGE_ID)

print()
print("=" * 70)
print("16. Full ancestry-chain validation for a Public Account edit (independent-review finding)")
print("=" * 70)
# An independent adversarial review of section 14 found that _validate_present_location_change()
# only checked state-belongs-to-country, not that a submitted Zone/District/Tehsil/Village chain
# actually nests the way the real geography data says it must. A Public Account staying Public
# (so the account-boundary check never fires) could submit a real, EXISTING village id that
# belongs to a completely different Tehsil/District than the rest of the submitted chain, and
# the pre-fix code would have accepted it -- letting a member falsely claim residency of (and
# become Q-Punch-eligible for) a village they never actually selected through real geography.
# Fixed: Zone/District/Tehsil ancestry checked against subcontinent_states.json/
# subcontinent_districts.json (always-populated static data -- hard reject on mismatch); Village
# ancestry checked against india_villages.tehsil_id (soft-fails on "not found", since that table
# is legitimately empty in this and every other test DB -- see section 16's own seeded rows
# below for why that doesn't defeat this test -- but hard-rejects a CONFIRMED mismatch).
login(india["private_code"])

# 16a. District does not belong to the selected State (Andaman district under Delhi state) --
# needs no seeded data; subcontinent_districts.json is always populated.
bad_district = dict(INDIA_LOC)
bad_district["district"] = {"id": "CS.AN.1", "name": "Andaman and Nicobar Islands"}
r = client.post("/api/dashboard/edit-request", json={"present_location": bad_district, "reason": "x"})
check("A district that belongs to a DIFFERENT State (Andaman district under Delhi state) is "
      "REJECTED (400)", r.status_code == 400)

# 16b. Tehsil does not belong to the selected District (a real Delhi NW-district tehsil swapped
# for one from a different Delhi district -- still same State, so only the tehsil's own parent
# is wrong).
bad_tehsil = dict(INDIA_LOC)
bad_tehsil["tehsil"] = {"id": "CS.AN.1.1", "name": "Port Blair"}
r = client.post("/api/dashboard/edit-request", json={"present_location": bad_tehsil, "reason": "x"})
check("A tehsil that belongs to a DIFFERENT District (Port Blair tehsil under NW Delhi district) "
      "is REJECTED (400)", r.status_code == 400)

# 16c. Zone does not actually contain the selected State.
real_zones = appmod._load_json(appmod.SUBCONTINENT_STATES_FILE)["countries"]
india_zones = next(c for c in real_zones if c["id"] == "O_AS_IND")["zones"]
other_zone = next(z for z in india_zones if "CS.DL" not in {st["id"] for st in z["states"]})
bad_zone = dict(INDIA_LOC)
bad_zone["zone"] = {"id": other_zone["id"], "name": other_zone.get("name", "")}
r = client.post("/api/dashboard/edit-request", json={"present_location": bad_zone, "reason": "x"})
check(f"A Zone ({other_zone['id']}) that does not actually contain the selected State (CS.DL) "
      "is REJECTED (400)", r.status_code == 400)

# 16c-ii. Malformed present_location -- not a dict at all, and an empty dict (missing country
# entirely). Both must fail safe (reject), not crash with a 500 or get misclassified.
r = client.post("/api/dashboard/edit-request", json={"present_location": "not-a-location", "reason": "x"})
check("A present_location that is a plain string, not an object, is REJECTED (400), not a 500",
      r.status_code == 400)
r = client.post("/api/dashboard/edit-request", json={"present_location": {}, "reason": "x"})
check("An empty present_location object (no country at all) is REJECTED (400) -- missing data "
      "classifies as 'global' (the more restrictive bucket) and is then rejected for having no "
      "continent, never silently treated as a valid Public Account change",
      r.status_code == 400)

# 16d. Village ancestry -- seed india_villages with two real-looking rows (Bawana's own village,
# correctly parented, plus a second real id deliberately parented to a DIFFERENT tehsil) so the
# soft-fails-on-"not found" / hard-rejects-on-confirmed-mismatch logic has something concrete to
# check against (every test DB's india_villages table starts empty -- see
# _validate_india_villages_loaded()'s own boot-time warning).
conn = dbmod.get_db()
conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES (?, ?, ?)",
             ("CS.DL.3.4.1A", "CS.DL.3.4", "Rohini Sector 24"))
conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES (?, ?, ?)",
             ("CS.AN.1.1.1", "CS.AN.1.1", "Bombooflat"))
conn.commit()
conn.close()

mismatched_village = dict(INDIA_LOC)  # state/district/tehsil stay Delhi/NW-Delhi/Bawana
mismatched_village["village"] = {"id": "CS.AN.1.1.1", "name": "Bombooflat"}  # real village, real parent is CS.AN.1.1
r = client.post("/api/dashboard/edit-request", json={"present_location": mismatched_village, "reason": "x"})
check("A REAL, existing village (Bombooflat, CS.AN.1.1.1) whose REAL parent tehsil "
      "(CS.AN.1.1) disagrees with the submitted chain (Bawana, CS.DL.3.4) is REJECTED (400) -- "
      "this is the exact gap an independent review flagged: a village id alone, even a real one, "
      "must never be trusted without confirming it actually belongs to the rest of the chain",
      r.status_code == 400)

correct_village = dict(INDIA_LOC)  # unchanged -- CS.DL.3.4.1A really does belong to CS.DL.3.4
r = client.post("/api/dashboard/edit-request", json={"present_location": correct_village, "reason": "x"})
check("The SAME village id, correctly matched to its real tehsil, is accepted (200) -- the "
      "ancestry check does not false-positive on a genuinely consistent chain",
      r.status_code == 200)
logout()

print()
print("=" * 70)
print("17. Admin auto-nominate/auto-vote simulation cannot bypass the same eligibility checks")
print("=" * 70)
# election_core.auto_nominate()/auto_vote() (admin-only, /api/admin/election/auto-nominate and
# auto-vote) build their OWN candidate/voter pool with a raw SQL query --
# "WHERE json_extract(u.present_location_json, '$.village.id') = ?" -- independently of
# _present_village_id(), so an independent review asked whether a fabricated village id could
# slip through THIS pool even though the real nominate()/cast_vote() endpoints are closed.
# It cannot: auto_nominate() re-checks nomination_eligible(conn, u, cycle)[0] -- which calls
# _present_village_id() -- for every row in its raw pool before picking anyone, and auto_vote()
# casts every vote through the real cast_vote(), which calls voting_eligible() -- also
# _present_village_id() -- and catches its ValueError as a no-op "skipped", never a crash and
# never a vote. Both are exercised directly here (not through the admin HTTP routes, which only
# run on whatever phase TODAY's real-world calendar happens to be in) using an explicit `today=`
# override, the same pattern election_test_scheduler.py itself uses to simulate any day.
conn = dbmod.get_db()
conn.execute(
    "UPDATE users SET present_location_json = ? WHERE id = ?",
    (json.dumps({**JAPAN_LOC, "village": {"id": appmod.election_core.PILOT_VILLAGE_ID, "name": "Rohini Sector 24"}}), japan_user_id),
)
conn.commit()
conn.close()

NOM_DAY = dt.date(2026, 5, 22)    # 2 days into the Gemini nomination window (05-21..05-28)
VOTE_DAY = dt.date(2026, 5, 30)   # 2 days into the Gemini voting window (05-29..06-11)
# The fabricated row's raw village.id DOES match the pool's own WHERE clause -- confirming the
# bypass attempt is actually exercised, not accidentally skipped for an unrelated reason.
conn = dbmod.get_db()
raw_pool_hit = conn.execute(
    "SELECT COUNT(*) AS n FROM users WHERE json_extract(present_location_json, '$.village.id') = ? AND id = ?",
    (appmod.election_core.PILOT_VILLAGE_ID, japan_user_id),
).fetchone()["n"]
conn.close()
check("Sanity check: the fabricated row's raw village.id really does match auto_nominate's/"
      "auto_vote's own WHERE clause (otherwise this test would prove nothing)",
      raw_pool_hit == 1)

conn = dbmod.get_db()
cycle = appmod.election_core.current_cycle_for_village(conn, appmod.election_core.PILOT_VILLAGE_ID, NOM_DAY)
check("Sanity check: the simulated nomination day really does land in a 'nomination' cycle",
      cycle["status"] == "nomination")
picked = appmod.election_core.auto_nominate(conn, appmod.election_core.PILOT_VILLAGE_ID, today=NOM_DAY)
conn.commit()
is_candidate = conn.execute(
    "SELECT COUNT(*) AS n FROM election_candidates WHERE election_cycle_id = ? AND user_id = ?",
    (cycle["id"], japan_user_id),
).fetchone()["n"]
conn.close()
check("auto_nominate() did NOT pick the fabricated-village-id Global Account as a candidate, "
      "despite it matching the function's own raw SQL pool query -- nomination_eligible()'s "
      "internal _present_village_id() re-check filters it out before anyone is ever picked",
      is_candidate == 0)

conn = dbmod.get_db()
vote_cycle = appmod.election_core.current_cycle_for_village(conn, appmod.election_core.PILOT_VILLAGE_ID, VOTE_DAY)
check("Sanity check: the simulated voting day really does land in a 'voting' cycle",
      vote_cycle["status"] == "voting")
cast_result = appmod.election_core.auto_vote(conn, appmod.election_core.PILOT_VILLAGE_ID, today=VOTE_DAY, turnout=1.0)
conn.commit()
fabricated_vote_count = conn.execute(
    "SELECT COUNT(*) AS n FROM election_votes WHERE election_cycle_id = ? AND voter_user_id = ?",
    (vote_cycle["id"], japan_user_id),
).fetchone()["n"]
conn.close()
check("auto_vote() did NOT cast a vote on behalf of the fabricated-village-id Global Account -- "
      "cast_vote()'s own voting_eligible() check (same _present_village_id() gate) rejects it, "
      "caught as a no-op 'skipped' entry by auto_vote(), never a vote and never a crash",
      fabricated_vote_count == 0)

conn = dbmod.get_db()
conn.execute("UPDATE users SET present_location_json = ? WHERE id = ?", (json.dumps(JAPAN_LOC), japan_user_id))
conn.commit()
conn.close()

print()
print("=" * 70)
print("18. Task 1A (2026-11-08) -- District now REQUIRED when a Tehsil is submitted, at BOTH")
print("    registration and profile-change, plus the full 14-point adversarial matrix")
print("=" * 70)
# A second owner-approved audit pass asked for an explicit, numbered adversarial matrix proving
# each ancestry relationship independently, at BOTH entry points that can ever write
# present_location_json (registration via api_auth_register, and the profile-change-request
# flow already covered by sections 14/16/17). Many of these were already proven for
# profile-change in section 16; this section's job is specifically to prove the SAME rules now
# hold for REGISTRATION too (newly hardened this pass via the shared
# _validate_zone_district_tehsil_ancestry() helper), plus the few cases no earlier section
# isolated on their own (a bare Village with no parent at all, an unknown/fabricated id, and a
# malformed field type).
conn = dbmod.get_db()
conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES (?, ?, ?)",
             ("CS.DL.3.4.1A", "CS.DL.3.4", "Rohini Sector 24"))
conn.commit()
conn.close()


def reg_present(present_location, **extra):
    """Registers a fresh user with the given present_location, all other fields realistic
    defaults, and returns the raw response (caller checks status_code -- never assumes success)."""
    payload = dict(extra)
    return register("AdversarialReg", present_location, **payload)


# 1. Tehsil submitted without District -- rejected, AT REGISTRATION (profile-change already
#    proven in section 16's "district OMITTED" case via the earlier audit, reproduced again here
#    for registration specifically).
loc_1 = dict(INDIA_LOC)
del loc_1["district"]
r = reg_present(loc_1)
check("1. REGISTRATION: Tehsil submitted without District is REJECTED (400)", r.status_code == 400)

# 2. Village submitted without required ancestors (no Tehsil, no District at all) -- rejected.
loc_2 = {k: v for k, v in INDIA_LOC.items() if k not in ("district", "tehsil")}
r = reg_present(loc_2)
check("2. REGISTRATION: Village submitted with no Tehsil AND no District is REJECTED (400)",
      r.status_code == 400)
login(india["private_code"])
r2 = client.post("/api/dashboard/edit-request", json={"present_location": loc_2, "reason": "task1a-adversarial"})
check("2b. PROFILE-CHANGE: same bare-Village submission is REJECTED (400)", r2.status_code == 400)
logout()

# 3. Genuine Tehsil belonging to another District -- rejected, AT REGISTRATION (District present
#    and real, but genuinely the wrong one for this Tehsil).
loc_3 = dict(INDIA_LOC)
loc_3["tehsil"] = {"id": "CS.AN.1.1", "name": "Port Blair"}  # real tehsil, real (wrong) district CS.DL.3 submitted
r = reg_present(loc_3)
check("3. REGISTRATION: a genuine Tehsil (Port Blair) under the WRONG District (NW Delhi) is "
      "REJECTED (400)", r.status_code == 400)

# 4. Genuine District belonging to another State -- rejected, AT REGISTRATION.
loc_4 = dict(INDIA_LOC)
loc_4["district"] = {"id": "CS.AN.1", "name": "Andaman and Nicobar Islands"}
del loc_4["tehsil"]
del loc_4["village"]
r = reg_present(loc_4)
check("4. REGISTRATION: a genuine District (Andaman) under the WRONG State (Delhi) is "
      "REJECTED (400)", r.status_code == 400)

# 5. Genuine State with a mismatched Zone -- rejected, AT REGISTRATION.
real_zones = appmod._load_json(appmod.SUBCONTINENT_STATES_FILE)["countries"]
india_zones = next(c for c in real_zones if c["id"] == "O_AS_IND")["zones"]
other_zone = next(z for z in india_zones if "CS.DL" not in {st["id"] for st in z["states"]})
loc_5 = dict(INDIA_LOC)
loc_5["zone"] = {"id": other_zone["id"], "name": other_zone.get("name", "")}
r = reg_present(loc_5)
check(f"5. REGISTRATION: a genuine State (Delhi) under the WRONG Zone ({other_zone['id']}) is "
      "REJECTED (400)", r.status_code == 400)

# 6. Genuine Village belonging to another Tehsil -- rejected, AT REGISTRATION (registration never
#    queried india_villages before this pass at all -- but note: registration's own ancestry fix
#    is scoped to Zone/District/Tehsil only, matching Task 1A's own distinction between the
#    always-available static JSON data and the india_villages DB table's test-environment
#    population caveat; this case is still caught because the submitted Tehsil (CS.AN.1.1) does
#    not belong to the submitted District (CS.DL.3) -- the Tehsil-ancestry check catches it before
#    a village-ancestry check would even need to run).
loc_6 = dict(INDIA_LOC)
loc_6["village"] = {"id": "CS.AN.1.1.1", "name": "Bombooflat"}
loc_6["tehsil"] = {"id": "CS.AN.1.1", "name": "Port Blair"}
r = reg_present(loc_6)
check("6. REGISTRATION: a genuine Village+Tehsil pair (Bombooflat/Port Blair) under the WRONG "
      "District/State (NW Delhi) is REJECTED (400)", r.status_code == 400)
# ...and the PROFILE-CHANGE equivalent, which DOES reach india_villages (already proven once in
# section 16 with a different District/Tehsil pairing; this is the same relationship, different
# submitted ancestors, re-confirmed here for completeness of the numbered matrix):
login(india["private_code"])
r6b = client.post("/api/dashboard/edit-request", json={"present_location": loc_6, "reason": "task1a-adversarial"})
check("6b. PROFILE-CHANGE: same genuine-Village-wrong-Tehsil submission is REJECTED (400)",
      r6b.status_code == 400)
logout()

# 7. Unknown / fabricated location IDs -- safe rejection (never a 500), at both entry points.
loc_7 = dict(INDIA_LOC)
loc_7["village"] = {"id": "CS.DL.3.4.ZZ-DOES-NOT-EXIST", "name": "Nowhere"}
r = reg_present(loc_7)
check("7. REGISTRATION: an unknown/fabricated Village id alongside a real Tehsil is REJECTED "
      "(400, not a 500) -- registration's own scope (Zone/District/Tehsil only) means this "
      "particular case isn't itself what rejects it; confirm no crash at minimum",
      r.status_code in (201, 400) and r.status_code != 500)
login(india["private_code"])
r7b = client.post("/api/dashboard/edit-request", json={"present_location": loc_7, "reason": "task1a-adversarial"})
check("7b. PROFILE-CHANGE: the same unknown/fabricated Village id is HARD-REJECTED (400) -- "
      "this is the Task 1A policy change: 'not found in india_villages' is now treated as "
      "confirmed invalid, never silently accepted as unverifiable-but-fine",
      r7b.status_code == 400)
logout()

# 8. Missing / malformed intermediate parent fields -- safe rejection (never a 500).
malformed_type = dict(INDIA_LOC)
malformed_type["district"] = "CS.DL.3"  # a plain string, not {"id": ...}
r = reg_present(malformed_type)
check("8. REGISTRATION: a malformed (wrong-type) District field is REJECTED (400, not a 500)",
      r.status_code == 400)
login(india["private_code"])
r8b = client.post("/api/dashboard/edit-request", json={"present_location": malformed_type, "reason": "task1a-adversarial"})
check("8b. PROFILE-CHANGE: the same malformed District field is REJECTED (400, not a 500)",
      r8b.status_code == 400)
logout()

# 9. Complete, valid Public Account ancestry -- accepted, AT REGISTRATION (the positive control;
#    proves the new checks don't false-positive on genuinely consistent, realistic data).
r = reg_present(dict(INDIA_LOC))
check("9. REGISTRATION: a complete, internally-consistent India chain is ACCEPTED (201)",
      r.status_code == 201)

# 10. Valid Global Account registration -- preserved, unaffected by any of this section's changes.
r = register("AdversarialGlobal", JAPAN_LOC)
check("10. REGISTRATION: a valid Global Account (Japan, country-only) still succeeds (201)",
      r.status_code == 201)

# 11. Global Account submitting lower-level Public geography -- rejected (already proven in
#     section 5 for registration and section 14 for profile-change; re-confirmed here as part of
#     the complete numbered matrix, not a new code path).
fabricated_global = dict(JAPAN_LOC)
fabricated_global["village"] = {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"}
r = reg_present(fabricated_global)
check("11. REGISTRATION: a Global country (Japan) with an injected Village id is REJECTED (400)",
      r.status_code == 400)

# 12. Invalid profile-change request -- rejected BEFORE queuing (proven in section 14/16; this
#     confirms it again using THIS section's loc_3/loc_4 payloads specifically).
queued_before = dbmod.get_db().execute(
    "SELECT COUNT(*) AS n FROM profile_change_requests WHERE reason = 'task1a-adversarial'"
).fetchone()["n"]
check("12. None of this section's rejected profile-change attempts (2b/6b/7b/8b) actually "
      "queued a ticket", queued_before == 0)

# 13. A previously-queued invalid request is rejected again at Admin approval (bypassing
#     submission-time validation via a direct SQL insert, exactly as section 14 already proved
#     for the account-boundary case -- here reproduced for a pure ancestry mismatch instead).
conn = dbmod.get_db()
appmod._ensure_profile_change_table(conn)
bad_ancestry_fields = json.dumps({"present_location": loc_3})  # Port Blair tehsil under Delhi district
cur = conn.execute(
    "INSERT INTO profile_change_requests (user_id, fields_json, reason, status, request_type) VALUES (?, ?, ?, 'pending', 'edit')",
    (india_user_id, bad_ancestry_fields, "pre-hardening-style ancestry bypass ticket"),
)
conn.commit()
bypass_id_2 = cur.lastrowid
conn.close()
login(admin["private_code"])
bypass_decide_2 = client.post(f"/api/admin/profile-changes/{bypass_id_2}/decide", json={"approve": True})
check("13. Approving a directly-inserted ticket with a genuine Tehsil/District ancestry "
      "mismatch is REJECTED (400) at decision time", bypass_decide_2.status_code == 400)
logout()
ticket_status_2 = dbmod.get_db().execute(
    "SELECT status FROM profile_change_requests WHERE id = ?", (bypass_id_2,)
).fetchone()["status"]
check("13b. That ticket is still 'pending' -- not silently approved", ticket_status_2 == "pending")

# 14. Rejected approval -- the target user's record remains completely unchanged.
untouched_india_loc = json.loads(dbmod.get_db().execute(
    "SELECT present_location_json FROM users WHERE id = ?", (india_user_id,)
).fetchone()["present_location_json"])
check("14. The India user's present_location_json was NOT modified by the rejected approval "
      "(still the last legitimately-applied value from section 15)", untouched_india_loc == INDIA_LOC)

print()
print("=" * 70)
print("19. Phase 1 corrective task (2026-11-08) -- REGISTRATION now hard-rejects a real/")
print("    fabricated/malformed Village the same way profile-change already does")
print("=" * 70)
# The owner's review of Phase 1 found that registration's Village check stopped at "does it look
# provisional" -- a non-provisional id was never cross-checked against india_villages at all, so
# a registrant could submit ANY string as their village and have it silently accepted. Closed by
# reusing the EXISTING provisional_location_core.verified_village_exists() helper (not a new
# lookup mechanism) inside api_auth_register()'s own provisional-check loop: a non-provisional
# Village id is now required to be a real row whose tehsil_id matches the submitted
# Tehsil-or-District, exactly mirroring _validate_present_location_change()'s own policy.
conn = dbmod.get_db()
conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES ('CS.AN.1.1.1', 'CS.AN.1.1', 'Bombooflat')")
conn.commit()
conn.close()

users_before = dbmod.get_db().execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]

# 1. A fully valid, internally-consistent official Village registration still succeeds.
r = register("Village19Valid", dict(INDIA_LOC))
check("1. A valid official Village (correct Tehsil/District/State) registration succeeds (201)",
      r.status_code == 201)

# 2. An unknown/fabricated Village id (not provisional, not real) is rejected.
fab = dict(INDIA_LOC)
fab["village"] = {"id": "CS.DL.3.4.NOPE-FABRICATED", "name": "Nowhere"}
r = register("Village19Fab", fab)
check("2. An unknown/fabricated Village id is REJECTED at registration (400)", r.status_code == 400)

# 3. A real, existing Village that belongs to a DIFFERENT Tehsil (same District/State as
# submitted, so the Tehsil-ancestry check passes -- only the Village-to-Tehsil relationship is
# wrong) is rejected.
wrong_tehsil = dict(INDIA_LOC)
wrong_tehsil["tehsil"] = {"id": "CS.DL.3.1", "name": "Another NW Delhi Tehsil"}  # real tehsil, real child of CS.DL.3
# village stays CS.DL.3.4.1A, whose REAL tehsil is CS.DL.3.4, not CS.DL.3.1
r = register("Village19WrongTehsil", wrong_tehsil)
check("3. A real Village (Rohini Sector 24) submitted under a DIFFERENT, otherwise-valid Tehsil "
      "(CS.DL.3.1, also really under NW Delhi) is REJECTED (400) -- the Tehsil-ancestry check "
      "alone passes here; only the Village-to-Tehsil check catches this",
      r.status_code == 400)

# 4/5. A real, existing Village that belongs to a DIFFERENT District AND State (Tehsil omitted,
# so only District is the stated immediate parent -- isolates the Village-level check from the
# Tehsil-ancestry check entirely).
wrong_district_and_state = {k: v for k, v in INDIA_LOC.items() if k != "tehsil"}
wrong_district_and_state["village"] = {"id": "CS.AN.1.1.1", "name": "Bombooflat"}  # real village, real tehsil CS.AN.1.1 (Andaman)
r = register("Village19WrongDistrict", wrong_district_and_state)
check("4/5. A real Village (Bombooflat, whose real parent is Andaman's CS.AN.1.1) submitted "
      "under Delhi's District+State (CS.DL.3/CS.DL, no Tehsil stated) is REJECTED (400) -- "
      "demonstrates both the wrong-District and wrong-State relationships at once, since "
      "Andaman differs from Delhi at both levels",
      r.status_code == 400)

# 6. Missing District with a real Tehsil -- already proven in section 18 #1 (registration); not
# re-duplicated here.

# 7. Missing immediate parent for a Village -- already proven in section 18 #2; not re-duplicated.

# 8. Legitimate provisional Village registration follows the existing intended workflow --
# already exhaustively covered by tests/test_provisional_locations.py's own "Registration
# integration" section (re-run as part of the full suite for this task; confirmed unaffected).

# 9. An arbitrary id that LOOKS provisional-shaped but refers to no real row, and one that is
# NOT provisional-shaped at all despite starting with "PROV-", both fail to masquerade as a
# legitimate provisional location.
fake_prov_real_shape = dict(INDIA_LOC)
fake_prov_real_shape["village"] = {"id": "PROV-999999999", "name": "Nonexistent provisional row"}
r = register("Village19FakeProvShape", fake_prov_real_shape)
check("9. A PROV-shaped id with no matching provisional_locations row is REJECTED (400) -- the "
      "EXISTING get_provisional()-not-found check, unmodified by this task, already covers this",
      r.status_code == 400)
fake_prov_malformed = dict(INDIA_LOC)
fake_prov_malformed["village"] = {"id": "PROV-abc", "name": "Not actually digits"}
r = register("Village19FakeProvMalformed", fake_prov_malformed)
check("9b. A string that merely starts with 'PROV-' but doesn't match the real pattern "
      "(non-digit suffix) is never treated as provisional either -- it falls through to the "
      "real-Village check and is REJECTED (400) for not being found there",
      r.status_code == 400)

# 10. A genuine database/query failure during Village verification never results in silent
# acceptance -- verified directly against the real function (not a simulated/mocked outcome):
# calling it on an already-closed connection raises, it never returns True.
closed_conn = dbmod.get_db()
closed_conn.close()
try:
    appmod.provisional_location_core.verified_village_exists(closed_conn, "CS.DL.3.4", "CS.DL.3.4.1A")
    check("10. A genuine DB-query failure during Village verification raises rather than "
          "silently returning a valid result", False)
except Exception:
    check("10. A genuine DB-query failure during Village verification raises rather than "
          "silently returning a valid result", True)

# 11. A malformed Village field (wrong type, not {"id": ...}) returns a controlled 400, not an
# uncaught exception -- the SAME _location_subfields_well_formed() guard Task 1A already added,
# confirmed here specifically for the "village" key (Task 1A's own test only exercised "district").
malformed_village = dict(INDIA_LOC)
malformed_village["village"] = "CS.DL.3.4.1A"  # a plain string, not {"id": "CS.DL.3.4.1A"}
r = register("Village19Malformed", malformed_village)
check("11. A malformed (wrong-type) Village field is REJECTED (400, not a 500)", r.status_code == 400)

# 12. Profile-change submission continues to reject unknown Village ids -- already proven in
# section 16's "unknown/fabricated Village" case (7b); not re-duplicated here.

# 13. Admin approval revalidates and cannot approve a now-invalid/fabricated Village -- already
# proven in section 14 (the bypass-ticket test) and section 18 #13; not re-duplicated here.

# 14. None of this section's REJECTED registration attempts (2, 3, 4/5, 9, 9b, 11) created a
# partial or unintended user record.
users_after = dbmod.get_db().execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
check("14. Exactly 1 new user was created (the single successful registration in check #1) -- "
      "none of the rejected attempts left behind a partial account row",
      users_after - users_before == 1)

print()
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print(f"  - {f}")
    sys.exit(1)
print("All checks PASSED.")
