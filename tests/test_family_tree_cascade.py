"""Covers the Family Tree Phase 1 backend repair (2026-11-01, see
docs/family_tree/PHASE_1_BACKEND_REPAIR_REPORT.md) that tests/test_family_tree.py (the
pre-existing, much larger suite -- left untouched) doesn't already exercise:

  1. The activation-blocker fix: request_join_group() is now idempotent (returns the existing
     pending request / membership instead of raising "A join request is already waiting" / "You
     are already a member"), and _resolve_slot()'s "join" branch never lets ANY ValueError from it
     abort the rest of activate_timeline()/marry_timeline().
  2. cascade_for_node(): parents, siblings, grandparent units, spouse, children and child units
     discovered automatically once an existing member is linked into the tree.
  3. The three person-centric relationship primitives: add_sibling_to_node(), add_child_to_node(),
     add_spouse_to_node() -- and their routes, /api/family/person/<node_id>/{sibling,child,spouse}.
  4. The Phase 2 backend preflight fixes (2026-11-01, see
     docs/family_tree/PHASE_2_BACKEND_PREFLIGHT.md): the top-level has_join_errors flag, the
     is_deceased passthrough on Add Sibling/Add Child, and add_child_to_group() echoing group_id.

Standalone script, no test framework (none installed in this project): throwaway DB built through
the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure -- same conventions
as tests/test_family_tree.py.

Run with: python3 tests/test_family_tree_cascade.py (not -I)
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

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402

# 2026-11-08 (Phase 1 corrective task): registration now verifies a real (non-provisional)
# Village against india_villages, the same way profile-change already does -- every throwaway
# test DB starts with that table empty, so any test registering a real village through the real
# /api/auth/register route must seed its row here first (same pattern as
# tests/test_global_account.py's section 16/18).
_seed_conn = dbmod.get_db()
_seed_conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES ('CS.DL.3.4.1A', 'CS.DL.3.4', 'Rohini Sector 24')")
_seed_conn.execute("INSERT OR REPLACE INTO india_villages (id, tehsil_id, name) VALUES ('CS.DL.3.4.1B', 'CS.DL.3.4', 'Rohini Sector 25')")
_seed_conn.commit()
_seed_conn.close()

import family_core  # noqa: E402

FAILS = []


def check(label, cond):
    ok = bool(cond)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        FAILS.append(label)


client = appmod.app.test_client()

VILLAGE_A = {
    "continent": {"id": "O_AS", "name": "Asia"}, "country": {"id": "O_AS_IND", "name": "India"},
    "zone": {"id": "IND/CS", "name": "Central State"}, "state": {"id": "CS.DL", "name": "Delhi"},
    "district": {"id": "CS.DL.3", "name": "North West Delhi"}, "tehsil": {"id": "CS.DL.3.4", "name": "Bawana"},
    "village": {"id": "CS.DL.3.4.1A", "name": "Rohini Sector 24"},
}

_n = [0]


def register(name_prefix):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "male", "dob": "1990-06-15", "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": VILLAGE_A, "present_location": VILLAGE_A, "assisted": False,
    }
    res = client.post("/api/auth/register", json=payload)
    if res.status_code != 201:
        sys.exit(f"REGISTER FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")
    return res.get_json()


def login(private_code):
    res = client.post("/login", json={"private_id": private_code, "pin": "12345"})
    if res.status_code != 200:
        sys.exit(f"LOGIN FAILED: {res.status_code} {res.get_data(as_text=True)[:500]}")


def logout():
    client.get("/logout")  # /logout is GET-only (app.py) -- POST would 405 and never clear the session


def raw(sql, params=()):
    conn = dbmod.get_db()
    row = conn.execute(sql, params).fetchone()
    conn.close()
    return row


print("=" * 70)
print("1. request_join_group() is idempotent: duplicate pending request is REUSED, not rejected")
print("=" * 70)

bob_sibling = register("Bob Sibling")
login(bob_sibling["private_code"])
res = client.post("/api/family/activate", json={"father": {"name": "Bob Father", "action": "create"}, "mother": {"name": "Bob Mother", "action": "create"}})
bob_birth_unit_id = res.get_json()["parents_group_id"]

logout()
bob_cousin = register("Bob Cousin")
login(bob_cousin["private_code"])
res = client.post("/api/family/activate", json={"father": {"name": "Cousin Father", "action": "create"}, "mother": {"name": "Cousin Mother", "action": "create"}})

# Direct "Find & Connect"-style join-request, independent of the activation wizard.
res = client.post(f"/api/family-groups/{bob_birth_unit_id}/join-request", json={})
check("first direct join-request is newly created (201, status=created)", res.status_code == 201 and res.get_json()["status"] == "created")
first_request_id = res.get_json()["request_id"]

res = client.post(f"/api/family-groups/{bob_birth_unit_id}/join-request", json={})
check("an IMMEDIATE repeat of the same join-request no longer raises 400 -- it's idempotent (200, status=already_pending)",
      res.status_code == 200 and res.get_json()["status"] == "already_pending")
check("the SAME existing request_id is returned, not a new row", res.get_json()["request_id"] == first_request_id)
check("no second pending people_requests row was created",
      raw("SELECT COUNT(*) AS n FROM people_requests WHERE from_user_id=? AND group_id=? AND kind='family_group_join' AND status='pending'",
          (bob_cousin["user_id"], bob_birth_unit_id))["n"] == 1)

print()
print("=" * 70)
print("2. THE ACTIVATION-BLOCKER FIX ITSELF: a grandparent slot matching a group that ALREADY has a")
print("   pending request from this user no longer aborts the entire activate_timeline() call")
print("=" * 70)

logout()
gp_owner = register("GP Owner")
login(gp_owner["private_code"])
res = client.post("/api/family/activate", json={"father": {"name": "GP Father", "action": "create"}, "mother": {"name": "GP Mother", "action": "create"}})
gp_group_id = res.get_json()["parents_group_id"]

logout()
griever = register("Griever Kid")
login(griever["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Griever Father", "action": "create"}, "mother": {"name": "Griever Mother", "action": "create"},
    "relationship": "married",
})

# griever ALREADY sent a direct join-request to gp_owner's parents' unit (e.g. via the old
# "Find & Connect" search) -- this is the REPRODUCIBLE, real-world trigger for "A join request is
# already waiting": the SAME group later gets matched again inside an activation/marriage payload.
res = client.post(f"/api/family-groups/{gp_group_id}/join-request", json={})
check("griever's own direct join-request to gp_owner's unit succeeds first", res.status_code == 201)

# Now griever runs ANOTHER activation-style operation (add-parents, reusing _resolve_slot's "join"
# action) targeting the SAME group+node pair that already has a pending request from them.
res = client.get("/api/family/suggest", query_string={"name": "GP Father"})
gp_match = next(r for r in res.get_json()["results"] if r["type"] == "group" and r["group_id"] == gp_group_id)
res = client.post("/api/family/marry", json={
    "spouse": {"name": "Griever Spouse", "action": "create"},
    "spouse_father": {"name": "GP Father", "action": "join", "group_id": gp_match["group_id"], "matched_node_id": gp_match["matched_node_id"]},
})
check("BEFORE the fix this call would abort entirely (400) the instant _resolve_slot() hit the "
      "already-pending request for the exact same group; AFTER the fix it completes (201) and the "
      "rest of the marriage (spouse creation, marital unit) is NOT discarded just because one "
      "already-pending grandparent-side join couldn't be queued twice",
      res.status_code == 201)
marry_body = res.get_json()
check("marital_group_id is present -- the marriage was NOT silently dropped", "marital_group_id" in marry_body)
spouse_father_entry = next((e for e in marry_body["joined_requests"] if e["label"] == "spouse_father"), None)
check("the spouse_father slot's join is recorded with status=already_pending, not silently lost",
      spouse_father_entry is not None and spouse_father_entry["status"] == "already_pending")

print()
print("=" * 70)
print("3. Idempotency: retrying the EXACT same activation payload a second time behaves safely")
print("=" * 70)

logout()
retry_owner = register("Retry Owner")
login(retry_owner["private_code"])
res = client.post("/api/family/activate", json={"father": {"name": "Retry Father", "action": "create"}, "mother": {"name": "Retry Mother", "action": "create"}})
retry_owner_group_id = res.get_json()["parents_group_id"]

logout()
retry_user = register("Retry User")
login(retry_user["private_code"])
res = client.get("/api/family/suggest", query_string={"name": "Retry Father"})
retry_match = next(r for r in res.get_json()["results"] if r["type"] == "group")
activate_payload = {
    "father": {"name": "Retry Father", "action": "join", "group_id": retry_match["group_id"], "matched_node_id": retry_match["matched_node_id"]},
    "mother": {"name": "Retry Mother 2", "action": "create"},
}
res1 = client.post("/api/family/activate", json=activate_payload)
check("first activation attempt succeeds (201)", res1.status_code == 201)
res2 = client.post("/api/family/activate", json=activate_payload)
check("retrying activation after it already succeeded is rejected cleanly (400, already activated) "
      "-- not a crash and not a silent duplicate", res2.status_code == 400)
check("the rejection names the real reason", "already activated" in res2.get_json().get("error", "").lower())
check("no duplicate self_node was created for retry_user",
      raw("SELECT COUNT(*) AS n FROM family_nodes WHERE claimed_user_id = ?", (retry_user["user_id"],))["n"] == 1)
check("no duplicate pending family_group_join request exists for retry_user -> retry_owner",
      raw("SELECT COUNT(*) AS n FROM people_requests WHERE from_user_id=? AND to_user_id=? AND kind='family_group_join' AND status='pending'",
          (retry_user["user_id"], retry_owner["user_id"]))["n"] == 1)

print()
print("=" * 70)
print("4. cascade_for_node(): discovering a linked person's own parents/siblings/spouse/children")
print("=" * 70)

logout()
dad = register("Cascade Dad")
login(dad["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Cascade Grandpa", "action": "create"}, "mother": {"name": "Cascade Grandma", "action": "create"},
    "relationship": "married",
})
dad_body = res.get_json()
res = client.post("/api/family/marry", json={
    "spouse": {"name": "Cascade Mom", "action": "create"},
    "children": [{"name": "Cascade Sibling One", "action": "create", "gender": "female"}],
})
dad_marry_body = res.get_json()
dad_self_node_id = dad_body["self_node_id"]
dad_search_code = client.get("/api/people/me").get_json()["search_code"]

logout()
viewer = register("Cascade Viewer")
login(viewer["private_code"])
res = client.post("/api/family/activate", json={"father": {"name": "Placeholder Dad", "action": "create"}, "mother": {"name": "Viewer Mother", "action": "create"}})
viewer_tree = client.get(f"/api/family-groups/{res.get_json()['parents_group_id']}/tree").get_json()
placeholder_father_node = next(n for n in viewer_tree["nodes"] if n["name"] == "Placeholder Dad")

res = client.post(f"/api/family/node/{placeholder_father_node['id']}/link", json={"user_id": dad_search_code})
check("viewer links their real father (dad) by Public ID", res.status_code == 200)

res = client.get(f"/api/family/person/{dad_self_node_id}/cascade")
check("cascade endpoint succeeds for the just-linked father's node (200)", res.status_code == 200)
cascade = res.get_json()
check("cascade finds dad's own father (the viewer's grandfather)",
      cascade["parents"] is not None and cascade["parents"]["father"]["name"] == "Cascade Grandpa")
check("cascade finds dad's own mother (the viewer's grandmother)",
      cascade["parents"]["mother"]["name"] == "Cascade Grandma")
check("cascade finds dad's spouse (Cascade Mom, the viewer's actual mother)",
      cascade["spouse"] is not None and cascade["spouse"]["name"] == "Cascade Mom")
check("cascade finds dad's OTHER child (Cascade Sibling One, the viewer's real sibling)",
      any(c["name"] == "Cascade Sibling One" for c in cascade["children"]))
check("cascade does not duplicate the viewer themself in the children list "
      "(viewer's OWN node, not dad's placeholder, is the one now in dad's unit)",
      len([c for c in cascade["children"] if c["name"].startswith("Cascade Viewer")]) <= 1)

# Phase 2 preflight-adjacent additions (2026-11-01, the Profile Card's header fields): relationship
# label, age, account_id -- all computed relative to VIEWER, who is still logged in here.
check("dad's relationship_to_viewer is Father (computed from the actual graph, not visual position)",
      cascade["node"]["relationship_to_viewer"] == "Father")
# Cascade Mom is dad's wife in HIS OWN separate marital unit, not Viewer Mother (the OTHER founder
# of viewer's OWN birth unit, in a second, never-unified unit -- link_node_to_user() deliberately
# never reconciles the two, see its own docstring) -- so Cascade Mom is correctly OUTSIDE the
# bounded relationship categories relative to viewer, not a (wrong) "Mother".
check("Cascade Mom (dad's wife in his OWN separate, unreconciled unit) is correctly NOT labeled "
      "Mother for viewer -- outside the bounded categories, not a guess",
      cascade["spouse"]["relationship_to_viewer"] is None)
viewer_mother_node = next(n for n in viewer_tree["nodes"] if n["name"] == "Viewer Mother")
res = client.get(f"/api/family/person/{viewer_mother_node['id']}/cascade")
check("Viewer Mother (the actual other founder of viewer's OWN birth unit) correctly IS labeled Mother",
      res.status_code == 200 and res.get_json()["node"]["relationship_to_viewer"] == "Mother")
# Same root cause as Cascade Mom above: Cascade Grandpa/Grandma are dad's OWN parents in his
# separate unit, and Cascade Sibling One is dad's child WITH Cascade Mom in that same separate
# unit -- none of them are reachable from viewer's OWN (never-unified) birth unit, so all three are
# correctly None here too. Section 7 below covers Grandfather/Sibling labels on a fully-connected
# fixture instead, where they resolve correctly.
check("Cascade Grandpa is correctly NOT labeled Grandfather for viewer (dad's own separate unit, never unified)",
      cascade["parents"]["father"]["relationship_to_viewer"] is None)
check("Cascade Sibling One is correctly NOT labeled Sister for viewer (dad's child WITH Cascade Mom, same separate unit)",
      next(c for c in cascade["children"] if c["name"] == "Cascade Sibling One")["relationship_to_viewer"] is None)
check("dad (a real, claimed, registered member) has a non-null account_id, never a Private ID/PIN",
      cascade["node"]["claimed"] is True and cascade["node"]["account_id"])
check("dad's age is computed live from his own registered DOB (every test user registers with one), not approximate",
      cascade["node"]["age_years"] is not None and cascade["node"]["age_is_approx"] is False)
check("Cascade Grandpa (an unclaimed placeholder, no approximate age set yet) has age_years=None, age_is_approx=True",
      cascade["parents"]["father"]["age_years"] is None and cascade["parents"]["father"]["age_is_approx"] is True)

logout()
stranger = register("Cascade Stranger")
login(stranger["private_code"])
res = client.get(f"/api/family/person/{dad_self_node_id}/cascade")
check("a stranger sharing no group with this node gets 404, not the family's data", res.status_code == 404)

print()
print("=" * 70)
print("5. Person-centric Add Sibling / Add Child / Add Spouse")
print("=" * 70)

# Acting as DAD himself, not viewer: dad is admin of his OWN birth unit (he created it at his own
# activation -- create_group()'s creator-admin grant) and a FOUNDER of his own marital unit, so
# he's authorized to grow both. Viewer, who merely linked dad's Public ID into their OWN tree,
# gets no such standing over dad's pre-existing units -- see section 4's "stranger" check below for
# that distinction being enforced, not an oversight.
logout()
login(dad["private_code"])

res = client.post(f"/api/family/person/{dad_self_node_id}/sibling", json={"name": "Dad's Brother", "gender": "male"})
check("Add Sibling on dad's node succeeds (201)", res.status_code == 201)
sibling_node_id = res.get_json()["node_id"]
check("the new sibling was added to dad's OWN birth unit (Grandpa+Grandma's), not dad's marital unit",
      bool(raw("SELECT 1 FROM family_group_nodes WHERE group_id = ? AND node_id = ?", (dad_body["parents_group_id"], sibling_node_id))))
check("the new sibling is NOT a member of dad's marital unit (would wrongly make them dad's own child)",
      not raw("SELECT 1 FROM family_group_nodes WHERE group_id = ? AND node_id = ?", (dad_marry_body["marital_group_id"], sibling_node_id)))

res = client.post(f"/api/family/person/{dad_self_node_id}/child", json={"name": "Dad's New Kid", "gender": "female"})
check("by now dad is a founder of TWO active units (his own marriage, AND -- since section 4 "
      "linked his Public ID into the founder slot of viewer's own parents' unit -- that unit too, "
      "which link_node_to_user() never reconciles into one marriage, see its own docstring); Add "
      "Child with no group_id is correctly rejected as ambiguous (400) rather than silently "
      "guessing which unit was meant", res.status_code == 400)
check("...the error says to disambiguate with group_id", "group_id" in res.get_json().get("error", ""))

res = client.post(f"/api/family/person/{dad_self_node_id}/child",
                   json={"name": "Dad's New Kid", "gender": "female", "group_id": dad_marry_body["marital_group_id"]})
check("passing the explicit group_id resolves the ambiguity and succeeds (201)", res.status_code == 201)
new_kid_node_id = res.get_json()["node_id"]
check("the new child was added to the SPECIFIED unit (dad's real marital unit), not guessed", bool(raw(
    "SELECT 1 FROM family_group_nodes WHERE group_id = ? AND node_id = ?", (dad_marry_body["marital_group_id"], new_kid_node_id))))

res = client.post(f"/api/family/person/{dad_self_node_id}/child",
                   json={"name": "Should Fail", "group_id": 999999999})
check("passing a group_id that ISN'T one of this node's own active units is rejected (400), not silently accepted", res.status_code == 400)

# viewer merely linked dad's Public ID into their OWN tree -- that grants viewer no admin standing
# over dad's PRE-EXISTING units (grandpa's birth unit, dad's own marital unit). Confirms linking
# someone in is discovery/visibility (cascade_for_node(), section 4), never an authorization
# shortcut for mutating units the viewer was never actually invited into.
logout()
login(viewer["private_code"])
res = client.post(f"/api/family/person/{dad_self_node_id}/sibling", json={"name": "Viewer Overreach"})
check("viewer (no admin standing on dad's birth unit, just linked his Public ID) is refused (403)", res.status_code == 403)
logout()
login(dad["private_code"])

fresh_person = register("Fresh Lone Person")
login(fresh_person["private_code"])
res = client.post("/api/family/activate", json={"father": {"name": "Fresh Father", "action": "create"}, "mother": {"name": "Fresh Mother", "action": "create"}})
fresh_tree = client.get(f"/api/family-groups/{res.get_json()['parents_group_id']}/tree").get_json()
fresh_father_node = next(n for n in fresh_tree["nodes"] if n["name"] == "Fresh Father")

# "Fresh Father" was created AS a founder of fresh_person's own parents' unit (father+mother are
# ALWAYS a couple by construction in activate_timeline()) -- so he does, correctly, already have a
# birth-unit-less but spouse-having node: Add Sibling fails (his OWN parents aren't known), but
# Add Child/Add Spouse on him are legitimately NOT "no spouse yet" cases. Use sibling_node_id
# ("Dad's Brother", section 5's own earlier Add Sibling result) instead for those two -- a genuine
# plain child-member placeholder with no founder status and no marriage of its own at all.
res = client.post(f"/api/family/person/{fresh_father_node['id']}/sibling", json={"name": "Should Fail No Parents", "gender": "female"})
check("Add Sibling on a node whose OWN parents aren't known yet is correctly rejected with a clear reason",
      res.status_code == 400)
check("...the error explains what's missing, doesn't fabricate a parent pair",
      "parents" in res.get_json().get("error", "").lower())

login(dad["private_code"])
res = client.post(f"/api/family/person/{sibling_node_id}/child", json={"name": "No Spouse Yet Kid"})
check("Add Child on a plain placeholder with no spouse of its own is rejected with a clear reason (400)", res.status_code == 400)
check("...the error explains a spouse is needed first", "spouse" in res.get_json().get("error", "").lower())

res = client.post(f"/api/family/person/{sibling_node_id}/spouse", json={"name": "Dad's Brother's Wife", "gender": "female"})
check("Add Spouse on that same spouse-less placeholder succeeds (201)", res.status_code == 201)
new_spouse_group_id = res.get_json()["group_id"]
check("the new unit has sibling_node_id as one of its two founders", bool(raw(
    "SELECT 1 FROM family_groups WHERE id = ? AND (husband_node_id = ? OR wife_node_id = ?)",
    (new_spouse_group_id, sibling_node_id, sibling_node_id))))

res = client.post(f"/api/family/person/{sibling_node_id}/spouse", json={"name": "A Second Wife"})
check("Add Spouse is rejected once an ACTIVE marriage already exists for that node (400)", res.status_code == 400)
check("...the error names the existing marriage", "already has an active marriage" in res.get_json().get("error", ""))

logout()
login(stranger["private_code"])
res = client.post(f"/api/family/person/{dad_self_node_id}/sibling", json={"name": "Intruder Sibling"})
check("a stranger with no admin standing on this node's (resolvable) birth unit is refused (403, not 201)", res.status_code == 403)

print()
print("=" * 70)
print("6. Phase 2 preflight (2026-11-01, docs/family_tree/PHASE_2_BACKEND_PREFLIGHT.md): "
      "has_join_errors, is_deceased passthrough, group_id echoed back")
print("=" * 70)

# has_join_errors=False on a merely NON-fatal, already-pending/already-member join status --
# section 2's griever/marry_body case already proved status=already_pending is recorded; confirm
# the new top-level flag correctly treats that as "not an error."
check("has_join_errors is False when every joined_requests entry is already_pending, not an error",
      marry_body.get("has_join_errors") is False)

# has_join_errors=True on a GENUINE, non-recoverable request_join_group() error (section 2.1's
# concern: these must stay a VISIBLE failure, not get absorbed into an apparently-clean 201).
# bob_sibling (section 1) owns bob_birth_unit_id outright (its creator) -- matching a "join" slot
# to his OWN group during marry_timeline() hits request_join_group()'s "You already own this
# group" ValueError, which _resolve_slot() correctly does NOT let abort the whole call, but which
# must still be visible at the top level.
logout()
login(bob_sibling["private_code"])
res = client.post("/api/profile/personal-details", json={"relationship_status": "married"})
check("bob_sibling's relationship_status is set to married (test setup)", res.status_code == 200)
bob_birth_unit = raw("SELECT husband_node_id FROM family_groups WHERE id = ?", (bob_birth_unit_id,))
res = client.post("/api/family/marry", json={
    "spouse": {"name": "Bob's Spouse", "action": "create"},
    "spouse_father": {"name": "Bob Father", "action": "join", "group_id": bob_birth_unit_id,
                       "matched_node_id": bob_birth_unit["husband_node_id"]},
})
check("the whole marry_timeline() call still succeeds (201) despite the one slot's genuine error -- "
      "the rest of the tree (spouse, marital unit) is still built", res.status_code == 201)
own_group_marry_body = res.get_json()
check("marital_group_id is present -- not discarded", "marital_group_id" in own_group_marry_body)
own_group_entry = next((e for e in own_group_marry_body["joined_requests"] if e["label"] == "spouse_father"), None)
check("the spouse_father slot is recorded with status=error (a genuine, non-recoverable request_join_group() failure)",
      own_group_entry is not None and own_group_entry["status"] == "error")
check("...the error names the real reason (you already own this group)",
      "already own" in (own_group_entry or {}).get("error", "").lower())
check("has_join_errors is True at the top level -- impossible to miss by checking the HTTP status alone",
      own_group_marry_body.get("has_join_errors") is True)

# is_deceased passthrough (2026-11-01 preflight fix): previously accepted by add_sibling_to_node()/
# add_child_to_node()'s own signatures but silently dropped before reaching create_node() -- and
# never even read from the request body by their routes. Add Spouse already worked; all three are
# now consistent.
login(dad["private_code"])
res = client.post(f"/api/family/person/{dad_self_node_id}/sibling",
                   json={"name": "Dad's Late Brother", "gender": "male", "is_deceased": True})
check("Add Sibling with is_deceased=True succeeds (201)", res.status_code == 201)
late_sibling_node_id = res.get_json()["node_id"]
check("the new sibling placeholder is actually stored as deceased, not silently dropped",
      bool(raw("SELECT is_deceased FROM family_nodes WHERE id = ?", (late_sibling_node_id,))["is_deceased"]))
check("add_child_to_group()'s result now echoes the group_id it actually used",
      res.get_json().get("group_id") == dad_body["parents_group_id"])

res = client.post(f"/api/family/person/{late_sibling_node_id}/spouse",
                   json={"name": "Late Brother's Widow", "gender": "female", "is_deceased": False})
check("Add Spouse on the deceased sibling still succeeds (a deceased founder can still have a recorded spouse)",
      res.status_code == 201)

print()
print("=" * 70)
print("7. relationship_to_viewer labels (Phase 2, the Profile Card header): a single person's own, "
      "fully-connected activation -- covers every bounded category, including Uncle/Cousin/Nephew")
print("=" * 70)

logout()
rel_self = register("Rel Self")
login(rel_self["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Rel Father", "action": "create"}, "mother": {"name": "Rel Mother", "action": "create"},
    "father_father": {"name": "Rel Grandfather", "action": "create"}, "father_mother": {"name": "Rel Grandmother", "action": "create"},
    "relationship": "married",
})
rel_body = res.get_json()
rel_self_node_id = rel_body["self_node_id"]
parents_tree = client.get(f"/api/family-groups/{rel_body['parents_group_id']}/tree").get_json()
rel_father_node_id = next(n["id"] for n in parents_tree["nodes"] if n["name"] == "Rel Father")
rel_mother_node_id = next(n["id"] for n in parents_tree["nodes"] if n["name"] == "Rel Mother")

# Both done BEFORE marrying: once rel_self marries, _sync_family_membership() moves their own
# birth- and grandparent-unit membership to 'left' (rule 2/3) -- these additions, and the labels
# that depend on shared membership below, need rel_self to still be a plain, approved member of
# both right now.
res = client.post(f"/api/family/person/{rel_father_node_id}/sibling", json={"name": "Rel Uncle", "gender": "male"})
check("Add Sibling on Rel Father's node succeeds (creates an uncle, a sibling of Rel Father)", res.status_code == 201)
rel_uncle_node_id = res.get_json()["node_id"]
res = client.post(f"/api/family/person/{rel_uncle_node_id}/spouse", json={"name": "Rel Aunt By Marriage", "gender": "female"})
check("Add Spouse on the uncle succeeds", res.status_code == 201)
rel_uncle_group_id = res.get_json()["group_id"]
res = client.post(f"/api/family/person/{rel_uncle_node_id}/child",
                   json={"name": "Rel Cousin", "gender": "female", "group_id": rel_uncle_group_id})
check("Add Child on the uncle's new unit succeeds (creates a cousin)", res.status_code == 201)
rel_cousin_node_id = res.get_json()["node_id"]

res = client.post(f"/api/family/person/{rel_self_node_id}/sibling", json={"name": "Rel Brother", "gender": "male"})
check("Add Sibling on Rel Self's own node succeeds (creates a brother)", res.status_code == 201)
rel_brother_node_id = res.get_json()["node_id"]
res = client.post(f"/api/family/person/{rel_brother_node_id}/spouse", json={"name": "Rel Sister-in-law", "gender": "female"})
check("Add Spouse on the brother succeeds", res.status_code == 201)
rel_brother_group_id = res.get_json()["group_id"]
res = client.post(f"/api/family/person/{rel_brother_node_id}/child",
                   json={"name": "Rel Nephew", "gender": "male", "group_id": rel_brother_group_id})
check("Add Child on the brother's new unit succeeds (creates a nephew)", res.status_code == 201)
rel_nephew_node_id = res.get_json()["node_id"]

def viewer_cascade_label(node_id):
    r = client.get(f"/api/family/person/{node_id}/cascade")
    return r.status_code, (r.get_json().get("node", {}).get("relationship_to_viewer") if r.status_code == 200 else None)

status, label = viewer_cascade_label(rel_father_node_id)
check("Rel Father's relationship_to_viewer is Father (via the real /cascade endpoint, normally authorized)", status == 200 and label == "Father")
status, label = viewer_cascade_label(rel_mother_node_id)
check("Rel Mother's relationship_to_viewer is Mother", status == 200 and label == "Mother")

parents_nbh = client.get(f"/api/family/node/{rel_body['parents_group_id']}/neighborhood").get_json()
grandparent_side = next(g for g in parents_nbh["parent_groups"] if g["side"] == "husband")
rel_grandfather_node_id = grandparent_side["husband"]["id"]
rel_grandmother_node_id = grandparent_side["wife"]["id"]
status, label = viewer_cascade_label(rel_grandfather_node_id)
check("Rel Grandfather's relationship_to_viewer is Grandfather", status == 200 and label == "Grandfather")
status, label = viewer_cascade_label(rel_grandmother_node_id)
check("Rel Grandmother's relationship_to_viewer is Grandmother", status == 200 and label == "Grandmother")
status, label = viewer_cascade_label(rel_uncle_node_id)
check("Rel Uncle's relationship_to_viewer is Uncle (shares the grandparent unit's membership with rel_self)",
      status == 200 and label == "Uncle")
status, label = viewer_cascade_label(rel_brother_node_id)
check("Rel Brother's relationship_to_viewer is Brother", status == 200 and label == "Brother")

# rel_self is also AUTOMATICALLY an approved admin member of the uncle's and brother's own new
# units (create_group() always grants the creator -- here, whoever ran Add Spouse -- admin, so
# every freshly-founded unit has someone who can manage it even before either slot is a real,
# claimed user; see create_group()'s own docstring), so these ARE visible via the real endpoint.
status, label = viewer_cascade_label(rel_cousin_node_id)
check("Rel Cousin's relationship_to_viewer is Cousin", status == 200 and label == "Cousin")
status, label = viewer_cascade_label(rel_nephew_node_id)
check("Rel Nephew's relationship_to_viewer is Nephew", status == 200 and label == "Nephew")

res = client.post(f"/api/family/node/{rel_grandfather_node_id}/details",
                   json={"approximate_age": 88})
check("update_node_details() sets an unclaimed node's approximate_age (201/200)", res.status_code == 200)
status, label = viewer_cascade_label(rel_grandfather_node_id)
res2 = client.get(f"/api/family/person/{rel_grandfather_node_id}/cascade")
check("the newly-set approximate_age is reflected in age_years/age_is_approx",
      res2.get_json()["node"]["age_years"] == 88 and res2.get_json()["node"]["age_is_approx"] is True)

res = client.post(f"/api/family/node/{rel_grandfather_node_id}/details",
                   json={"name": "Rel Grandfather Senior", "gender": "male"})
check("update_node_details() also updates name/gender together, preserving the SAME node id (not a new one)",
      res.status_code == 200 and
      raw("SELECT display_name FROM family_nodes WHERE id = ?", (rel_grandfather_node_id,))["display_name"] == "Rel Grandfather Senior")
check("the previously-set approximate_age survives a later edit that didn't touch it (no silent reset)",
      client.get(f"/api/family/person/{rel_grandfather_node_id}/cascade").get_json()["node"]["age_years"] == 88)

logout()
login(stranger["private_code"])
res = client.post(f"/api/family/node/{rel_grandfather_node_id}/details", json={"name": "Hijacked"})
check("a stranger with no admin standing on this node is refused (403), not allowed to edit it", res.status_code == 403)
logout()
login(rel_self["private_code"])

res = client.post(f"/api/family/node/{rel_self_node_id}/details", json={"name": "Should Fail"})
check("update_node_details() refuses to edit a CLAIMED node's details (400) -- their real profile is authoritative, "
      "even for rel_self editing their OWN node (admin of the unit, but it's still claimed)",
      res.status_code == 400)
check("...the error explains why", "real Qumanity account" in res.get_json().get("error", ""))

print()
print("=" * 70)
print("8. Full direct-roster cascade after link_node_to_user() (2026-11-XX, Package C, Option A)")
print("=" * 70)

# Fixture: "Roster Parent" founds a marital unit S with a placeholder spouse and THREE child
# placeholders. Two of the three children (One, Two) are then independently claimed by real,
# separately-registered Qumanity users -- Roster Real1 and Roster Real2 -- via link_node_to_user()
# (the "fresh claim" branch, no pre-existing node yet). The third child stays an unclaimed
# placeholder throughout, to prove placeholder-safety (Case G).
logout()
roster_parent = register("Roster Parent")
login(roster_parent["private_code"])
client.post("/api/family/activate", json={"father": {"name": "Roster Grandpa", "action": "create"},
                                           "mother": {"name": "Roster Grandma", "action": "create"}})
client.post("/api/profile/personal-details", json={"relationship_status": "married"})
marry_res = client.post("/api/family/marry", json={
    "spouse": {"name": "Roster Spouse", "action": "create"},
    "children": [
        {"name": "Roster Child One", "action": "create", "gender": "female"},
        {"name": "Roster Child Two", "action": "create", "gender": "male"},
        {"name": "Roster Child Three", "action": "create", "gender": "female"},
    ],
})
roster_group_id = marry_res.get_json()["marital_group_id"]
roster_tree = client.get(f"/api/family-groups/{roster_group_id}/tree").get_json()
child_one_node = next(n for n in roster_tree["nodes"] if n["name"] == "Roster Child One")
child_two_node = next(n for n in roster_tree["nodes"] if n["name"] == "Roster Child Two")
child_three_node = next(n for n in roster_tree["nodes"] if n["name"] == "Roster Child Three")

logout()
real1 = register("Roster Real1")
login(real1["private_code"])
real1_public_id = client.get("/api/people/me").get_json()["search_code"]
logout()
real2 = register("Roster Real2")
login(real2["private_code"])
real2_public_id = client.get("/api/people/me").get_json()["search_code"]
logout()

login(roster_parent["private_code"])
# link_node_to_user() takes the target's 12-digit PUBLIC ID (search_code), not their 9-digit
# Private ID/PIN login credential -- confirmed against section 4's existing fixture above.
link1 = client.post(f"/api/family/node/{child_one_node['id']}/link", json={"user_id": real1_public_id})
link2 = client.post(f"/api/family/node/{child_two_node['id']}/link", json={"user_id": real2_public_id})
check("Roster Child One is claimed by Roster Real1 (fresh claim, no pre-existing node)", link1.status_code == 200)
check("Roster Child Two is claimed by Roster Real2 (fresh claim, no pre-existing node)", link2.status_code == 200)
logout()

real1_user_id = raw("SELECT id FROM users WHERE private_id_9digit = ?", (real1["private_code"],))[0]
real2_user_id = raw("SELECT id FROM users WHERE private_id_9digit = ?", (real2["private_code"],))[0]
roster_parent_user_id = raw("SELECT id FROM users WHERE private_id_9digit = ?", (roster_parent["private_code"],))[0]

# A SEPARATE, unrelated group G: "Outside Admin" activates their own tree and adds an "Unknown
# Sibling" placeholder to their OWN birth unit. This placeholder is then linked to Roster Real1 --
# who ALREADY has a node (Roster Child One, in S) -- exercising link_node_to_user()'s
# existing_self_node branch, the one this package's cascade fix is about.
outside_admin = register("Outside Admin")
login(outside_admin["private_code"])
outside_activate = client.post("/api/family/activate", json={
    "father": {"name": "Outside Father", "action": "create"}, "mother": {"name": "Outside Mother", "action": "create"},
})
outside_self_node_id = outside_activate.get_json()["self_node_id"]
sibling_res = client.post(f"/api/family/person/{outside_self_node_id}/sibling", json={"name": "Unknown Sibling", "gender": "female"})
unknown_sibling_node_id = sibling_res.get_json()["node_id"]

link3 = client.post(f"/api/family/node/{unknown_sibling_node_id}/link", json={"user_id": real1_public_id})
check("Roster Real1 (who already has a node in S) is linked into G too (existing_self_node branch)",
      link3.status_code == 200)
cascade = link3.get_json().get("cascade")
check("the link response carries the new, additive 'cascade' field", cascade is not None)

print()
print("Case A/B: the FULL direct roster is processed, not just a single spouse hop")
check("cascade.synced_user_ids includes Roster Real1 (the linked person) themself",
      real1_user_id in cascade["synced_user_ids"])
check("cascade.synced_user_ids ALSO includes Roster Parent (S's founder) -- the fix this package is for",
      roster_parent_user_id in cascade["synced_user_ids"])
check("cascade.synced_user_ids ALSO includes Roster Real2 (S's OTHER claimed child) -- not just one hop",
      real2_user_id in cascade["synced_user_ids"])
check("exactly 3 people were synced (Roster Parent, Real1, Real2) -- the unclaimed spouse/Child "
      "Three are correctly excluded, not undercounted or overcounted",
      len(cascade["synced_user_ids"]) == 3)
check("cascade reports exactly one source group (S) was cascaded (Real1 has no birth unit of their "
      "own to also cascade -- they were a FRESH claim, never independently activated)",
      len(cascade["source_groups"]) == 1 and cascade["source_groups"][0]["group_id"] == roster_group_id)
check("that source group's reported member_count is 3 (both founders [1 claimed, 1 placeholder] + "
      "3 children [2 claimed, 1 placeholder] -- the COUNT reflects only claimed members, i.e. 3)",
      cascade["source_groups"][0]["member_count"] == 3)

print()
print("Case G: placeholder safety -- the unclaimed spouse and Child Three are never converted or counted")
check("Roster Spouse (never claimed) has no family_group_members row anywhere",
      not raw("SELECT 1 FROM family_group_members fgm JOIN family_nodes fn ON fn.claimed_user_id = fgm.user_id "
              "WHERE fn.display_name = 'Roster Spouse'"))
check("Roster Child Three (never claimed) still has status='empty', untouched",
      raw("SELECT status FROM family_nodes WHERE id = ?", (child_three_node["id"],))[0] == "empty")

print()
print("Case E/H: already-member and repeated-cascade safety -- no duplicates")
before_count = raw(
    "SELECT COUNT(*) FROM family_group_members WHERE group_id = ? AND user_id = ?",
    (roster_group_id, real2_user_id),
)[0]
conn2 = dbmod.get_db()
family_core._cascade_relatives_after_link(conn2, real1_user_id)
conn2.commit()
conn2.close()
after_count = raw(
    "SELECT COUNT(*) FROM family_group_members WHERE group_id = ? AND user_id = ?",
    (roster_group_id, real2_user_id),
)[0]
check("re-running the cascade for the same person a second time creates no duplicate membership row",
      before_count == after_count == 1)

print()
print("Case C/D: multiple active units -- ambiguous founder-side cascade is correctly SKIPPED "
      "(reusing section 4's existing 'Cascade Dad' fixture, which founds two separate active units)")
conn3 = dbmod.get_db()
dad_user_row = conn3.execute("SELECT id FROM users WHERE id = (SELECT claimed_user_id FROM family_nodes WHERE id = ?)",
                              (dad_self_node_id,)).fetchone()
dad_cascade_retry = family_core._cascade_relatives_after_link(conn3, dad_user_row["id"])
conn3.commit()
conn3.close()
check("dad (who founds two active units -- his own marriage AND, post-link, viewer's birth unit) "
      "gets the founder side SKIPPED, not guessed",
      any("ambiguous" in s.get("reason", "") for s in dad_cascade_retry["skipped"]))
check("dad himself is still synced (the skip only affects the EXTRA roster sweep, not dad's own membership)",
      dad_user_row["id"] in dad_cascade_retry["synced_user_ids"])

print()
print("=" * 70)
print("Option B: grandparent-group backfill (2026-11, approved) -- strictly capped at 2 generations")
print("=" * 70)

# Four-generation fixture, built directly via family_core (not the full activate/marry HTTP
# ceremony, to construct the exact pre-cascade topology needed): GreatGrandpa+GreatGrandma (Unit
# C) -> their child Grandpa, who founds Unit B with Grandma -> their child Dad, who founds Unit A
# with Mom -> their child Bob. Unit A/B/C are each created WITHOUT their own husband_parent_group_id
# set (the exact "deferred" state Option B exists to backfill), and Unit C itself has NO further
# parent unit at all (nothing to discover past hop 2 from Unit A).

ggp = register("GGPa"); ggp_user = ggp["user_id"]
ggm = register("GGMa"); ggm_user = ggm["user_id"]
gp = register("GPa"); gp_user = gp["user_id"]
gm = register("GMa"); gm_user = gm["user_id"]
dad = register("BackfillDad"); dad_user = dad["user_id"]
mom = register("BackfillMom"); mom_user = mom["user_id"]
bob = register("BackfillBob"); bob_user = bob["user_id"]

conn_bf = dbmod.get_db()
ggp_node = family_core.create_node(conn_bf, ggp_user, "GreatGrandpa", claimed_user_id=ggp_user)
ggm_node = family_core.create_node(conn_bf, ggm_user, "GreatGrandma", claimed_user_id=ggm_user)
gp_node = family_core.create_node(conn_bf, gp_user, "Grandpa", claimed_user_id=gp_user)
gm_node = family_core.create_node(conn_bf, gm_user, "Grandma", claimed_user_id=gm_user)
dad_node = family_core.create_node(conn_bf, dad_user, "BackfillDad", claimed_user_id=dad_user)
mom_node = family_core.create_node(conn_bf, mom_user, "BackfillMom", claimed_user_id=mom_user)
bob_node = family_core.create_node(conn_bf, bob_user, "BackfillBob", claimed_user_id=bob_user)

unit_c_id = family_core.create_group(conn_bf, ggp_user, "Unit C (great-grandparents)", None,
                                      ggp_node, ggm_node, [gp_node])  # Grandpa is Unit C's plain child member
unit_b_id = family_core.create_group(conn_bf, gp_user, "Unit B (grandparents)", None,
                                      gp_node, gm_node, [dad_node])  # Dad is Unit B's plain child member
unit_a_id = family_core.create_group(conn_bf, dad_user, "Unit A (parents)", None,
                                      dad_node, mom_node, [bob_node])  # Bob is Unit A's plain child member
conn_bf.commit()

before_unit_a = dict(conn_bf.execute("SELECT husband_parent_group_id, wife_parent_group_id FROM family_groups WHERE id = ?", (unit_a_id,)).fetchone())
before_unit_b = dict(conn_bf.execute("SELECT husband_parent_group_id, wife_parent_group_id FROM family_groups WHERE id = ?", (unit_b_id,)).fetchone())
check("Unit A starts with no parent-group link on either side (the deferred state)",
      before_unit_a["husband_parent_group_id"] is None and before_unit_a["wife_parent_group_id"] is None)
check("Unit B starts with no parent-group link on either side (the deferred state)",
      before_unit_b["husband_parent_group_id"] is None and before_unit_b["wife_parent_group_id"] is None)

cascade_bf = family_core._cascade_relatives_after_link(conn_bf, bob_user)
conn_bf.commit()

print()
print("1-2. Parent-group and grandparent-group discovery")
after_unit_a = dict(conn_bf.execute("SELECT husband_parent_group_id, wife_parent_group_id FROM family_groups WHERE id = ?", (unit_a_id,)).fetchone())
after_unit_b = dict(conn_bf.execute("SELECT husband_parent_group_id, wife_parent_group_id FROM family_groups WHERE id = ?", (unit_b_id,)).fetchone())
check("Unit A's husband_parent_group_id is backfilled to Unit B (Dad's own birth unit)",
      after_unit_a["husband_parent_group_id"] == unit_b_id)
check("Unit A's wife_parent_group_id stays NULL (Mom has no recorded birth unit in this fixture)",
      after_unit_a["wife_parent_group_id"] is None)
check("Unit B's husband_parent_group_id is backfilled to Unit C (Grandpa's own birth unit) -- the grandparent hop",
      after_unit_b["husband_parent_group_id"] == unit_c_id)
check("Unit B's wife_parent_group_id stays NULL (Grandma has no recorded birth unit in this fixture)",
      after_unit_b["wife_parent_group_id"] is None)

print()
print("3. Third-generation (great-grandparent) exclusion -- strictly capped at 2 generations above Unit A")
after_unit_c = dict(conn_bf.execute("SELECT husband_parent_group_id, wife_parent_group_id FROM family_groups WHERE id = ?", (unit_c_id,)).fetchone())
check("Unit C's OWN parent-group link is never even attempted (hop 3 from Unit A) -- stays NULL",
      after_unit_c["husband_parent_group_id"] is None and after_unit_c["wife_parent_group_id"] is None)
ancestor_hops = {a["group_id"]: a["hop"] for a in cascade_bf["ancestor_groups"]}
check("Unit B is reported as an ancestor group at hop 1", ancestor_hops.get(unit_b_id) == 1)
check("Unit C is reported as an ancestor group at hop 2", ancestor_hops.get(unit_c_id) == 2)
check("no ancestor group beyond hop 2 is ever reported", all(a["hop"] <= 2 for a in cascade_bf["ancestor_groups"]))

print()
print("4. Direct-roster-only cascade for each newly-reached ancestor group")
check("Grandpa and Grandma (Unit B's founders) are synced", gp_user in cascade_bf["synced_user_ids"] and gm_user in cascade_bf["synced_user_ids"])
check("GreatGrandpa and GreatGrandma (Unit C's founders) are synced", ggp_user in cascade_bf["synced_user_ids"] and ggm_user in cascade_bf["synced_user_ids"])
check("Dad, Mom and Bob (Unit A's own roster, hop 0, unchanged behavior) are all synced",
      {dad_user, mom_user, bob_user}.issubset(set(cascade_bf["synced_user_ids"])))

print()
print("5-6. Idempotency and no duplicate membership rows across overlapping/repeated calls")
members_before_rerun = conn_bf.execute(
    "SELECT group_id, user_id, COUNT(*) AS c FROM family_group_members WHERE user_id IN (?,?,?,?,?,?,?) GROUP BY group_id, user_id HAVING c > 1",
    (ggp_user, ggm_user, gp_user, gm_user, dad_user, mom_user, bob_user),
).fetchall()
check("no duplicate (group_id, user_id) membership rows exist after the first cascade", len(members_before_rerun) == 0)

cascade_bf_2 = family_core._cascade_relatives_after_link(conn_bf, bob_user)
conn_bf.commit()
after_unit_a_2 = dict(conn_bf.execute("SELECT husband_parent_group_id FROM family_groups WHERE id = ?", (unit_a_id,)).fetchone())
check("re-running the cascade is idempotent: Unit A's backfilled link is unchanged", after_unit_a_2["husband_parent_group_id"] == unit_b_id)
members_after_rerun = conn_bf.execute(
    "SELECT group_id, user_id, COUNT(*) AS c FROM family_group_members WHERE user_id IN (?,?,?,?,?,?,?) GROUP BY group_id, user_id HAVING c > 1",
    (ggp_user, ggm_user, gp_user, gm_user, dad_user, mom_user, bob_user),
).fetchall()
check("re-running the cascade creates no duplicate membership rows", len(members_after_rerun) == 0)

print()
print("7. Cycle protection (manufactured pathological cycle, isolated from the generation cap)")
cyc1_user = register("CycleOne")["user_id"]
cyc2_user = register("CycleTwo")["user_id"]
cyc1_node = family_core.create_node(conn_bf, cyc1_user, "CycleOneNode", claimed_user_id=cyc1_user)
cyc2_node = family_core.create_node(conn_bf, cyc2_user, "CycleTwoNode", claimed_user_id=cyc2_user)
cyc_unit_x = family_core.create_group(conn_bf, cyc1_user, "Cycle Unit X", None, cyc1_node, None, [])
cyc_unit_y = family_core.create_group(conn_bf, cyc2_user, "Cycle Unit Y", None, cyc2_node, None, [])
conn_bf.execute("UPDATE family_groups SET husband_parent_group_id = ? WHERE id = ?", (cyc_unit_y, cyc_unit_x))
conn_bf.execute("UPDATE family_groups SET husband_parent_group_id = ? WHERE id = ?", (cyc_unit_x, cyc_unit_y))
conn_bf.commit()
cycle_result = family_core._backfill_parent_group_links(conn_bf, cyc_unit_x, max_additional_hops=5, _visited=set())
check("cycle protection terminates and returns a bounded result, never hangs", isinstance(cycle_result, list) and len(cycle_result) <= 2)
check("both cyclic units are reached exactly once each, not revisited", len({r["group_id"] for r in cycle_result}) == len(cycle_result))

print()
print("8. Missing parent group: a group with no discoverable parent -- no crash, no action")
lonely_user = register("LonelyFounder")["user_id"]
lonely_node = family_core.create_node(conn_bf, lonely_user, "LonelyFounderNode", claimed_user_id=lonely_user)
lonely_unit = family_core.create_group(conn_bf, lonely_user, "Lonely Unit", None, lonely_node, None, [])
conn_bf.commit()
lonely_result = family_core._backfill_parent_group_links(conn_bf, lonely_unit, max_additional_hops=2, _visited=set())
check("a group with no discoverable parent returns just itself at hop 0, no crash", lonely_result == [{"group_id": lonely_unit, "hop": 0}])

print()
print("9. Authorization and transactional safety are unchanged -- backfill runs inside the same")
print("   caller-owned transaction as the rest of the cascade, with no separate commit of its own")
check("_backfill_parent_group_links performs no commit of its own (grep-verified, not just asserted)",
      "conn.commit()" not in __import__("inspect").getsource(family_core._backfill_parent_group_links))

print()
print("10. No writes to the deprecated family_spouse_links table from any of this")
check("_backfill_parent_group_links never references family_spouse_links",
      "family_spouse_links" not in __import__("inspect").getsource(family_core._backfill_parent_group_links))

conn_bf.close()

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
