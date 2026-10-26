"""Verifies the Family Tree backend under the Nuclear Family Node architecture (2026-10-20): a
family_groups row is a MARRIAGE UNIT (husband_node_id/wife_node_id), not a generic container.
Covers activate_timeline() (father+mother -> find-or-create their couple-unit, the activating user
added as a plain child-member), marry_timeline() (self+spouse -> find-or-create THEIR OWN
couple-unit, children added as its child-members), the single alive-and-eldest naming rule,
is_deceased, admin derivation (founders are admins; the creator of a freshly-founded unit is also
always granted admin, additive, for when both founder slots start out as unclaimed placeholders),
a spousal join claiming an empty founder slot directly (no more family_spouse_links writes), the
neighborhood endpoint, tree_for_group()'s scoped 404 and spouse-link synthesis, and that
activating twice is rejected.

Standalone script, no test framework (none installed in this project): throwaway DB built
through the real Flask app and its real routes, PASS/FAIL printing, exit 1 on failure. Follows
the same pattern as tests/test_identity_correction.py and tests/test_admin_panel_council_scope.py.

Run with: python3 tests/test_family_tree.py (not -I -- isolated mode hides this machine's Flask
install).
"""
from __future__ import annotations

import io
import os
import sys
import tempfile

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

_fd, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_fd)
os.environ["QM_DB_PATH"] = _DB_PATH
os.environ["QM_DISABLE_SCHEDULER"] = "1"

import app as appmod  # noqa: E402
import db as dbmod  # noqa: E402
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


def register(name_prefix, dob="1990-06-15"):
    _n[0] += 1
    payload = {
        "name": f"{name_prefix} {_n[0]}", "gender": "male", "dob": dob, "tob": "06:00",
        "language": "English", "email": "", "phone": "", "pin": "12345",
        "birth_location": VILLAGE_A, "present_location": VILLAGE_A, "assisted": False,
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


def set_married(private_code):
    login(private_code)
    res = client.post("/api/profile/personal-details", json={"relationship_status": "married", "has_children": True, "sons_count": 1, "daughters_count": 1})
    check("set relationship_status=married", res.status_code == 200)


print("=" * 70)
print("1. Basic activation: father+mother only -> find-or-create their couple-unit")
print("=" * 70)

alice = register("Alice Sharma", dob="2000-01-01")
login(alice["private_code"])
res = client.get("/api/family/status")
check("not yet activated", res.status_code == 200 and res.get_json()["activated"] is False)

res = client.post("/api/family/activate", json={
    "father": {"name": "Pardeep Sharma", "action": "create"},
    "mother": {"name": "Sunita Sharma", "action": "create"},
})
check("activation succeeds (201)", res.status_code == 201)
if res.status_code != 201:
    print("   body:", res.get_data(as_text=True)[:500])
body = res.get_json()
check("self_node_id present", "self_node_id" in body)
check("parents' unit created", "parents_group_id" in body)
check("no marital unit created (single, no spouse yet)", "marital_group_id" not in body)
check("unit named via the husband+wife naming code (2026-10-20 format)", body.get("parents_group_name") == "PAMA-SUMA-Sharma Family")

res = client.get("/api/family/status")
check("now activated", res.get_json()["activated"] is True)
check("status shows the new unit, admin=True (creator grant, since neither founder is claimed yet)",
      any(g["id"] == body["parents_group_id"] and g["is_admin"] for g in res.get_json()["groups"]))

res = client.post("/api/family/activate", json={"father": {"name": "X", "action": "create"}, "mother": {"name": "Y", "action": "create"}})
check("re-activating is rejected (400)", res.status_code == 400)

tree = client.get(f"/api/family-groups/{body['parents_group_id']}/tree").get_json()
check("unit's legacy tree view has 3 nodes (self, father, mother)", len(tree["nodes"]) == 3)
check("unit kind is 'unit'", tree["kind"] == "unit")
check("activating user IS admin of their own freshly-founded unit (creator grant)", tree["is_admin"] is True)

neighborhood = client.get(f"/api/family/node/{body['parents_group_id']}/neighborhood").get_json()
check("neighborhood reports the two founders (father, mother)",
      neighborhood["husband"]["name"] == "Pardeep Sharma" and neighborhood["wife"]["name"] == "Sunita Sharma")
check("neighborhood lists alice as an unmarried child-member", any(c["is_viewer"] for c in neighborhood["unmarried_children"]))
check("neighborhood is not dormant (both founders alive)", neighborhood["is_dormant"] is False)
check("neighborhood has no parent units (father/mother have no known birth units)", neighborhood["parent_groups"] == [])

print()
print("=" * 70)
print("2. Deceased father: naming still combines both founders regardless of alive/deceased status")
print("=" * 70)

greg = register("Greg Patel")
login(greg["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Deceased Patel", "action": "create", "is_deceased": True},
    "mother": {"name": "Living Mother Patel", "action": "create"},
})
check("activation with a deceased father succeeds", res.status_code == 201)
greg_body = res.get_json()
check("naming combines BOTH founders' codes regardless of alive/deceased status (2026-10-20 format) "
      "-- unlike eldest_node_id, which still prefers the alive founder for its own, separate purpose",
      greg_body["parents_group_name"] == "DEEL-LIEL-Patel Family")
greg_tree = client.get(f"/api/family-groups/{greg_body['parents_group_id']}/tree").get_json()
father_node = next(n for n in greg_tree["nodes"] if n["name"] == "Deceased Patel")
check("father node is flagged is_deceased", father_node["is_deceased"] is True)
check("the living child (greg) is still admin of his own freshly-founded unit (creator grant)", greg_tree["is_admin"] is True)

print()
print("=" * 70)
print("3. Missing father/mother is rejected")
print("=" * 70)

bob_check = register("Bob Kumar")
login(bob_check["private_code"])
res = client.post("/api/family/activate", json={"mother": {"name": "M", "action": "create"}})
check("missing father -> 400", res.status_code == 400)
res = client.post("/api/family/activate", json={"father": {"name": "F", "action": "create"}})
check("missing mother -> 400", res.status_code == 400)

print()
print("=" * 70)
print("4. Marriage: a SEPARATE call creates (or finds) the couple's OWN unit")
print("=" * 70)

carl = register("Carl Mehta")
set_married(carl["private_code"])
login(carl["private_code"])
res = client.post("/api/family/marry", json={"spouse": {"name": "Diana Mehta", "action": "create"}})
check("marry before activation is rejected (400)", res.status_code == 400)

res = client.post("/api/family/activate", json={
    "father": {"name": "Carl Sr Mehta", "action": "create"},
    "mother": {"name": "Carla Mehta", "action": "create"},
})
check("carl activates (parents' unit only)", res.status_code == 201)
carl_activate_body = res.get_json()

res = client.post("/api/family/marry", json={
    "spouse": {"name": "Diana Mehta", "action": "create"},
    "children": [{"name": "Evan Mehta", "action": "create"}, {"name": "Fiona Mehta", "action": "create"}],
})
check("marry succeeds and creates carl's own unit", res.status_code == 201)
carl_body = res.get_json()
check("marital unit created", "marital_group_id" in carl_body)
carl_tree = client.get(f"/api/family-groups/{carl_body['marital_group_id']}/tree").get_json()
check("marital unit's legacy tree kind is 'unit'", carl_tree["kind"] == "unit")
check("marital unit has 4 nodes (self, spouse, 2 children)", len(carl_tree["nodes"]) == 4)
check("legacy tree synthesizes 1 spouse link from husband/wife_node_id (family_spouse_links is deprecated)",
      len(carl_tree["spouse_links"]) == 1)
check("marital tree has 4 parent links (2 children x 2 parents)", len(carl_tree["parent_links"]) == 4)

carl_group_row = raw("SELECT husband_node_id, wife_node_id FROM family_groups WHERE id = ?", (carl_body["marital_group_id"],))
check("carl's own unit has both founder slots filled", carl_group_row["husband_node_id"] and carl_group_row["wife_node_id"])

res = client.post("/api/family/marry", json={"spouse": {"name": "Someone Else", "action": "create"}})
check("marrying again while already active is rejected (400)", res.status_code == 400)

print()
print("=" * 70)
print("5. Three-way search: unactivated real user match")
print("=" * 70)

logout()
pardeep_real = register("Pardeep Sharma")  # a REAL registered user sharing the father's exact name, never activated
login(alice["private_code"])
res = client.get("/api/family/suggest", query_string={"name": "Pardeep Sharma"})
check("suggest succeeds", res.status_code == 200)
results = res.get_json()["results"]
check("finds the unactivated real user", any(r["type"] == "unactivated_user" and r["user_id"] == pardeep_real["user_id"] for r in results))
check("does NOT suggest alice's own unit back to herself (already a member)",
      not any(r["type"] == "group" and r["group_name"] == "PAMA-SUMA-Sharma Family" for r in results))

res = client.get("/api/family/suggest", query_string={"name": "Nobody At All Xyz"})
check("no-match search returns type=none", res.get_json()["results"] == [{"type": "none"}])

print()
print("=" * 70)
print("6. Spousal join (2026-10-26, automatic): claims the OTHER (open) founder slot directly, no "
      "approval, grants founder-admin, auto-joins the husband's parents' unit, notifies the husband, "
      "and auto-leaves the wife's own birth unit")
print("=" * 70)

logout()
# Dana's own birth unit is created by a SIBLING first, so Dana herself joins it as a plain
# (non-admin) child-member -- the realistic case, and the one the "leave on marriage" rule needs:
# if Dana instead created the unit herself (fresh father+mother placeholders), she'd ALSO be its
# unconditional creator-admin (create_group()'s own additive grant), and _sync_family_membership()
# deliberately never revokes an admin row on marriage -- only a plain membership moves to 'left'.
dana_sibling = register("Dana Sibling")
login(dana_sibling["private_code"])
res = client.post("/api/family/activate", json={"father": {"name": "Dana Father", "action": "create"}, "mother": {"name": "Dana Mother", "action": "create"}})
dana_sibling_body = res.get_json()
dana_birth_unit_id = dana_sibling_body["parents_group_id"]

logout()
dana = register("Dana Mehta")
set_married(dana["private_code"])
login(dana["private_code"])
res = client.get("/api/family/suggest", query_string={"name": "Diana Mehta"})
spouse_match = next(r for r in res.get_json()["results"] if r["type"] == "group")
check("dana finds carl's unit via the spouse name", spouse_match["group_name"] is not None)
res = client.get("/api/family/suggest", query_string={"name": "Dana Father"})
dana_father_match = next(r for r in res.get_json()["results"] if r["type"] == "group")

res = client.post("/api/family/activate", json={
    "father": {"name": "Dana Father", "action": "join", "group_id": dana_father_match["group_id"], "matched_node_id": dana_father_match["matched_node_id"]},
    "mother": {"name": "Dana Mother 2", "action": "create"},
})
check("dana activates (joining her sibling's existing Dana Father unit, pending approval)", res.status_code == 201)

login(dana_sibling["private_code"])
res = client.get("/api/people/inbox")
dana_join_req = next(r for r in res.get_json()["requests"] if r["kind"] == "family_group_join")
res = client.post(f"/api/people/inbox/{dana_join_req['id']}/decide", json={"decision": "accept"})
check("dana's sibling accepts her join request (generic joins stay approval-gated, only marriage is automatic)", res.status_code == 200)

login(dana["private_code"])
dana_birth_member_row = raw(
    "SELECT status, is_admin FROM family_group_members WHERE group_id = ? AND user_id = ?", (dana_birth_unit_id, dana["user_id"])
)
check("dana is now an approved, PLAIN (non-admin) member of her own birth unit before marrying",
      dana_birth_member_row["status"] == "approved" and dana_birth_member_row["is_admin"] == 0)

res = client.post("/api/family/marry", json={
    "spouse": {"name": "Diana Mehta", "action": "join", "group_id": spouse_match["group_id"], "matched_node_id": spouse_match["matched_node_id"]},
})
check("dana's marry-join into carl's unit succeeds immediately (201, no pending request)", res.status_code == 201)
marry_body = res.get_json()
check("the response reports an instant auto_joined result, not a joined_requests entry", marry_body.get("auto_joined", {}).get("group_id") == carl_body["marital_group_id"])

res = client.get(f"/api/family-groups/{carl_body['marital_group_id']}/tree")
check("dana can see carl's unit immediately -- no approval wait at all", res.status_code == 200)
dana_view = res.get_json()
check("dana is flagged as admin (her own self-node now fills the open founder slot)", dana_view["is_admin"] is True)
placeholder_row = raw("SELECT claimed_user_id FROM family_nodes WHERE id = ?", (spouse_match["matched_node_id"],))
check("the original 'Diana Mehta' placeholder stays unclaimed -- dana's real self-node replaced it "
      "in the group's founder slot, rather than trying to claim a second node for the same person "
      "(claimed_user_id is globally unique: dana already has her own self-node from activation)",
      placeholder_row["claimed_user_id"] is None)
dana_self_node_row = raw(
    "SELECT wife_node_id FROM family_groups WHERE id = ?", (carl_body["marital_group_id"],)
)
check("the unit's wife_node_id now points at dana's OWN self-node, not the old placeholder",
      dana_self_node_row["wife_node_id"] != spouse_match["matched_node_id"])

dana_birth_member_row = raw(
    "SELECT status FROM family_group_members WHERE group_id = ? AND user_id = ?", (dana_birth_unit_id, dana["user_id"])
)
check("dana's membership in her OWN birth unit moved to 'left' now that she's founded her marital unit",
      dana_birth_member_row["status"] == "left")
dana_birth_tree_row = raw(
    "SELECT 1 FROM family_group_nodes fgn JOIN family_nodes fn ON fn.id = fgn.node_id "
    "WHERE fgn.group_id = ? AND fn.claimed_user_id = ?", (dana_birth_unit_id, dana["user_id"]),
)
check("dana's node is still VISIBLE in her birth unit's tree -- only chat membership moved, never the genealogy",
      dana_birth_tree_row is not None)

dana_inlaw_member_row = raw(
    "SELECT status, is_admin FROM family_group_members WHERE group_id = ? AND user_id = ?",
    (carl_activate_body["parents_group_id"], dana["user_id"]),
)
check("dana automatically joined carl's PARENTS' unit (her in-laws) as a plain member -- no request, no approval",
      dana_inlaw_member_row is not None and dana_inlaw_member_row["status"] == "approved")
check("...and that membership is NOT admin -- joining as an in-law, not a founder",
      dana_inlaw_member_row["is_admin"] == 0)

login(carl["private_code"])
res = client.get("/api/people/inbox")
notify_req = next((r for r in res.get_json()["requests"] if r["kind"] == "message" and r["from_user_id"] == dana["user_id"]), None)
check("carl received a notification that dana joined, not a blocking approval request", notify_req is not None)
check("the notification text names dana and says she joined as his spouse",
      notify_req is not None and "joined your family unit as your spouse" in notify_req["first_message"])

# Contrast: a CHILD joining their PARENTS' unit must stay a plain member, never admin.
logout()
erin = register("Erin Patel")
login(erin["private_code"])
res = client.get("/api/family/suggest", query_string={"name": "Deceased Patel"})
lineage_match = next(r for r in res.get_json()["results"] if r["type"] == "group")
res = client.post("/api/family/activate", json={
    "father": {"name": "Deceased Patel", "action": "join", "group_id": lineage_match["group_id"], "matched_node_id": lineage_match["matched_node_id"]},
    "mother": {"name": "Erin Mother", "action": "create"},
})
check("erin's activation (joining greg's parents' unit as a sibling) succeeds", res.status_code == 201)

login(greg["private_code"])
res = client.get("/api/people/inbox")
sib_req = next(r for r in res.get_json()["requests"] if r["kind"] == "family_group_join")
client.post(f"/api/people/inbox/{sib_req['id']}/decide", json={"decision": "accept"})

login(erin["private_code"])
res = client.get(f"/api/family-groups/{greg_body['parents_group_id']}/tree")
check("erin (a child, not a founder) is NOT admin after joining the unit", res.get_json()["is_admin"] is False)

print()
print("=" * 70)
print("7. Exact-Public-ID spouse notify links to the REAL self-node, never a duplicate placeholder")
print("=" * 70)
# A real bug caught by live browser testing (2026-10-20): the 'notify' action used to always
# create a brand-new empty placeholder node, even when the caller supplied an EXACT, already-
# verified user_id (via social_core.find_person()) whose own self-node already exists -- leaving
# the parent/child edge pointing at a disconnected, same-named duplicate instead of the real person.

logout()
finn = register("Finn Noble")
login(finn["private_code"])
res = client.post("/api/family/activate", json={"father": {"name": "Finn Father", "action": "create"}, "mother": {"name": "Finn Mother", "action": "create"}})
finn_self_node_id = res.get_json()["self_node_id"]

logout()
grace = register("Grace Noble")
set_married(grace["private_code"])
login(grace["private_code"])
client.post("/api/family/activate", json={"father": {"name": "Grace Father", "action": "create"}, "mother": {"name": "Grace Mother", "action": "create"}})
res = client.post("/api/family/marry", json={"spouse": {"name": "Finn Noble", "action": "notify", "user_id": finn["user_id"]}})
check("grace's marry (notify, exact id) succeeds", res.status_code == 201)
grace_marry_body = res.get_json()
check("no NEW node was created for the exact-id spouse (linked_existing)",
      any(n.get("linked_existing") and n["node_id"] == finn_self_node_id for n in grace_marry_body["created_node_ids"]))

grace_group_row = raw(
    "SELECT husband_node_id, wife_node_id FROM family_groups WHERE id = ?", (grace_marry_body["marital_group_id"],)
)
check("the new unit's founder pair points at finn's REAL claimed self-node, not a duplicate (family_spouse_links is "
      "deprecated -- the marriage itself IS the unit's husband/wife_node_id pair now)",
      finn_self_node_id in (grace_group_row["husband_node_id"], grace_group_row["wife_node_id"]))
duplicate_count = raw("SELECT COUNT(*) AS n FROM family_nodes WHERE display_name LIKE 'Finn Noble%'")
check("exactly one 'Finn Noble*' node exists in the whole DB (no duplicate placeholder)", duplicate_count["n"] == 1)

print()
print("=" * 70)
print("8. Node editing: rename an empty node, link it to a real user (Pass 1 routes)")
print("=" * 70)

# Reuse greg's unit (father node "Deceased Patel") from section 2.
father_node = next(n for n in greg_tree["nodes"] if n["name"] == "Deceased Patel")

logout()
login(greg["private_code"])
res = client.post(f"/api/family/node/{father_node['id']}/name", json={"name": "Deceased Patel Sr."})
check("admin can rename an empty node", res.status_code == 200)
greg_tree2 = client.get(f"/api/family-groups/{greg_body['parents_group_id']}/tree").get_json()
check("the rename is reflected in the tree", any(n["name"] == "Deceased Patel Sr." for n in greg_tree2["nodes"]))

res = client.post(f"/api/family/node/{father_node['id']}/name", json={"name": ""})
check("renaming to an empty string is rejected (400)", res.status_code == 400)

logout()
login(erin["private_code"])  # erin is a plain member (not admin) of greg's unit, from section 6
res = client.post(f"/api/family/node/{father_node['id']}/name", json={"name": "Hijacked"})
check("a non-admin cannot rename a node (403)", res.status_code == 403)

hank = register("Hank Patel")  # a real, unclaimed-elsewhere user, to link into greg's mother node
hank_search_code = client.get("/api/people/me").get_json()["search_code"]  # session is hank's right after registering
check("hank has a real 12-digit Public Search ID", hank_search_code is not None and len(hank_search_code) == 12)
mother_node = next(n for n in greg_tree["nodes"] if n["name"] == "Living Mother Patel")
logout()
login(greg["private_code"])
# Formatted exactly like a user would paste it (spaces, like the UI's "4060 2408 5969" example) --
# the normalization bug this covers: the backend must strip them before matching search_code.
formatted_code = hank_search_code[:4] + " " + hank_search_code[4:8] + " " + hank_search_code[8:]
res = client.post(f"/api/family/node/{mother_node['id']}/link", json={"user_id": formatted_code})
check("admin can link an empty node by a SPACE-FORMATTED 12-digit Public ID", res.status_code == 200)
mother_row = raw("SELECT claimed_user_id, status FROM family_nodes WHERE id = ?", (mother_node["id"],))
check("the node is now claimed by hank", mother_row["claimed_user_id"] == hank["user_id"] and mother_row["status"] == "claimed")
check("hank, having claimed a founder slot, is now also an admin of greg's parents' unit",
      bool(raw("SELECT is_admin FROM family_group_members WHERE group_id = ? AND user_id = ?",
                (greg_body["parents_group_id"], hank["user_id"]))["is_admin"]))

res = client.post(f"/api/family/node/{mother_node['id']}/link", json={"user_id": hank_search_code})
check("re-linking an already-claimed node is rejected (400)", res.status_code == 400)

jill = register("Jill Patel")
logout()
login(greg["private_code"])  # registering jill switched the session to jill -- switch back to the admin

# 2026-10-25: linking a FOUNDER-SLOT placeholder to a target who already has their own node
# elsewhere no longer blocks with "already has their own profile node elsewhere" -- it re-points
# every reference to the placeholder at the target's real node instead (the exact bug report
# scenario: a father's Public ID can't be linked because he already activated independently).
res = client.post(f"/api/family/node/{father_node['id']}/link", json={"user_id": hank_search_code})
check("linking a founder-slot node to an already-claimed target now SUCCEEDS (merge, not block) (200)", res.status_code == 200)

hank_self_node = raw("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (hank["user_id"],))
greg_group_row = raw("SELECT husband_node_id FROM family_groups WHERE id = ?", (greg_body["parents_group_id"],))
check("the unit's husband_node_id now points at hank's REAL self-node, not the old placeholder",
      greg_group_row["husband_node_id"] == hank_self_node["id"])
check("hank's real node inherits the placeholder's family_parent_links row (parent of greg's self-node)",
      bool(raw("SELECT 1 FROM family_parent_links WHERE parent_node_id = ? AND child_node_id = ?",
                (hank_self_node["id"], greg_body["self_node_id"]))))
check("the OLD placeholder no longer carries that parent_link",
      not raw("SELECT 1 FROM family_parent_links WHERE parent_node_id = ? AND child_node_id = ?",
               (father_node["id"], greg_body["self_node_id"])))
check("the old placeholder is left in the database but orphaned -- no family_group_nodes row references it any more",
      not raw("SELECT 1 FROM family_group_nodes WHERE node_id = ?", (father_node["id"],)))
check("the target (hank) gets the same courtesy 'might be related' ping as any other identity match",
      bool(raw("SELECT 1 FROM people_requests WHERE from_user_id = ? AND to_user_id = ? AND kind = 'message'",
                (greg["user_id"], hank["user_id"]))))

# The Public-ID validation checks need a FRESH, still-attached empty node -- father_node above is
# now deliberately orphaned by the merge, so re-using it here would hit the "not an admin of any
# group this node belongs to" 403 instead of the validation path being tested.
validation_user = register("Validation Parent Test")
login(validation_user["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Validation Father", "action": "create"}, "mother": {"name": "Validation Mother", "action": "create"},
})
validation_tree = client.get(f"/api/family-groups/{res.get_json()['parents_group_id']}/tree").get_json()
validation_father_node = next(n for n in validation_tree["nodes"] if n["name"] == "Validation Father")

res = client.post(f"/api/family/node/{validation_father_node['id']}/link", json={"user_id": "999999999999"})
check("a well-formed but non-existent 12-digit Public ID is rejected (400)", res.status_code == 400)

res = client.post(f"/api/family/node/{validation_father_node['id']}/link", json={"user_id": "4060-2408"})
check("an incomplete/malformed Public ID is rejected (400)", res.status_code == 400)

# A PLAIN child-member placeholder (not a founder slot) takes the generalized swap path --
# _swap_node_references() only; no family_groups column to touch, and -- unlike the founder-slot
# case above -- no founder-admin grant, since the target isn't becoming a unit founder.
plain_parent = register("Plain Member Parent")
login(plain_parent["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Plain Father", "action": "create"}, "mother": {"name": "Plain Mother", "action": "create"},
    "relationship": "married",
})
res = client.post("/api/family/marry", json={"spouse": {"name": "Plain Spouse", "action": "create"}, "marriage_status": "active"})
plain_marital_id = res.get_json()["marital_group_id"]
res = client.post(f"/api/family/node/{plain_marital_id}/add-child", json={"name": "Plain Child Placeholder", "gender": "female"})
plain_child_node_id = res.get_json()["node_id"]

independent_user = register("Independent Already Activated")
login(independent_user["private_code"])
res = client.post("/api/family/activate", json={"father": {"name": "Indep Father", "action": "create"}, "mother": {"name": "Indep Mother", "action": "create"}})
independent_self_node_id = res.get_json()["self_node_id"]
independent_search_code = client.get("/api/people/me").get_json()["search_code"]

logout()
login(plain_parent["private_code"])
res = client.post(f"/api/family/node/{plain_child_node_id}/link", json={"user_id": independent_search_code})
check("linking a PLAIN (non-founder) placeholder to an already-claimed target also succeeds (200)", res.status_code == 200)
check("the plain-member placeholder's family_group_nodes row moved to the real self-node",
      bool(raw("SELECT 1 FROM family_group_nodes WHERE group_id = ? AND node_id = ?", (plain_marital_id, independent_self_node_id))))
check("the old placeholder no longer appears in that unit's family_group_nodes",
      not raw("SELECT 1 FROM family_group_nodes WHERE group_id = ? AND node_id = ?", (plain_marital_id, plain_child_node_id)))
check("linking a plain (non-founder) node grants no founder-admin -- no family_group_members row was created for the target",
      raw("SELECT 1 FROM family_group_members WHERE group_id = ? AND user_id = ?", (plain_marital_id, independent_user["user_id"])) is None)

logout()
login(greg["private_code"])

print()
print("=" * 70)
print("9. Neighborhood endpoint: parent units and child units around a given unit")
print("=" * 70)

logout()
login(carl["private_code"])
neighborhood2 = client.get(f"/api/family/node/{carl_body['marital_group_id']}/neighborhood").get_json()
check("carl's own unit's neighborhood lists its parent unit (Carl Sr + Carla)",
      any(pg["husband"]["name"] == "Carl Sr Mehta" for pg in neighborhood2["parent_groups"]))
check("carl's own unit's neighborhood lists its 2 unmarried children", len(neighborhood2["unmarried_children"]) == 2)

logout()
login(bob_check["private_code"])  # bob never joined alice's unit
res = client.get(f"/api/family/node/{body['parents_group_id']}/neighborhood")
check("a non-member gets 404 (not 403) on the neighborhood endpoint", res.status_code == 404)

print()
print("=" * 70)
print("10. The dynamic Activation wizard: relationship sync, marriage_status, child gender")
print("=" * 70)

logout()
ivy = register("Ivy Kapoor")
login(ivy["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Ivy Father", "action": "create"},
    "mother": {"name": "Ivy Mother", "action": "create"},
    "relationship": "divorced",
})
check("activation with relationship=divorced succeeds", res.status_code == 201)
ivy_row = raw("SELECT relationship_status FROM users WHERE id = ?", (ivy["user_id"],))
check("divorced maps to users.relationship_status='divorced_widowed' (the legacy 3-value enum)",
      ivy_row["relationship_status"] == "divorced_widowed")

res = client.post("/api/family/marry", json={
    "spouse": {"name": "Ivy Ex", "action": "create"},
    "children": [
        {"name": "Ivy Child", "action": "create", "gender": "female"},
        {"name": "Ivy Second Child", "action": "create", "gender": "both"},
    ],
    "marriage_status": "dissolved",
})
check("marry succeeds straight off the relationship-sync, no separate profile call needed (201)", res.status_code == 201)
ivy_marry_body = res.get_json()
ivy_group_row = raw("SELECT marriage_status FROM family_groups WHERE id = ?", (ivy_marry_body["marital_group_id"],))
check("the unit's marriage_status is 'dissolved', not the old hardcoded 'active'", ivy_group_row["marriage_status"] == "dissolved")

ivy_child_node_id = next(n["node_id"] for n in ivy_marry_body["created_node_ids"] if n["name"] == "Ivy Child")
ivy_child_row = raw("SELECT gender FROM family_nodes WHERE id = ?", (ivy_child_node_id,))
check("the child's gender ('female', a Daughter) is saved on the placeholder node", ivy_child_row["gender"] == "female")

ivy_second_child_node_id = next(n["node_id"] for n in ivy_marry_body["created_node_ids"] if n["name"] == "Ivy Second Child")
ivy_second_child_row = raw("SELECT gender FROM family_nodes WHERE id = ?", (ivy_second_child_node_id,))
check("'both' (Third Gender) -- the SAME value registration itself offers, not a different 4th option -- is "
      "accepted for a child too", ivy_second_child_row["gender"] == "both")

res = client.get(f"/api/family/node/{ivy_marry_body['marital_group_id']}/neighborhood")
ivy_nbh = res.get_json()
ivy_child_summary = next(c for c in ivy_nbh["unmarried_children"] if c["name"] == "Ivy Child")
check("the neighborhood reports the placeholder child's gender as 'female'", ivy_child_summary["gender"] == "female")

# Claim that child node with a REAL user of a DIFFERENT gender ('both', third gender) -- the
# neighborhood must then show the LIVE claimed gender, not the stale placeholder guess.
logout()
jade = register("Jade NonBinary")  # register() always sends gender=male -- overwrite directly for this check
jade_search_code = client.get("/api/people/me").get_json()["search_code"]
_conn = dbmod.get_db()
_conn.execute("UPDATE users SET gender = 'both' WHERE id = ?", (jade["user_id"],))
_conn.commit()
_conn.close()

login(ivy["private_code"])
res = client.post(f"/api/family/node/{ivy_child_node_id}/link", json={"user_id": jade_search_code})
check("admin can link the child placeholder to jade's real account", res.status_code == 200)

res = client.get(f"/api/family/node/{ivy_marry_body['marital_group_id']}/neighborhood")
ivy_nbh2 = res.get_json()
jade_summary = next(c for c in ivy_nbh2["unmarried_children"] if c["id"] == ivy_child_node_id)
check("once claimed, the node's gender resolves LIVE from users.gender ('both'), not the stale 'female' placeholder",
      jade_summary["gender"] == "both")
check("the node's name also now resolves live, to jade's own registered name", jade_summary["name"].startswith("Jade NonBinary"))

# Single is rejected at the backend layer too, not just skipped by the frontend.
logout()
kay = register("Kay Solo")
login(kay["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Kay Father", "action": "create"},
    "mother": {"name": "Kay Mother", "action": "create"},
    "relationship": "single",
})
check("activation with relationship=single succeeds", res.status_code == 201)
kay_row = raw("SELECT relationship_status FROM users WHERE id = ?", (kay["user_id"],))
check("single maps to users.relationship_status='single'", kay_row["relationship_status"] == "single")
res = client.post("/api/family/marry", json={"spouse": {"name": "Should Not Work", "action": "create"}})
check("marry_timeline itself rejects a single user (400), not just the wizard skipping the call", res.status_code == 400)

# Invalid wizard inputs are rejected cleanly, not silently accepted.
logout()
leo = register("Leo Invalid")
login(leo["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Leo Father", "action": "create"},
    "mother": {"name": "Leo Mother", "action": "create"},
    "relationship": "engaged",
})
check("an unknown relationship value is rejected (400)", res.status_code == 400)
res = client.post("/api/family/activate", json={
    "father": {"name": "Leo Father", "action": "create"},
    "mother": {"name": "Leo Mother", "action": "create"},
    "relationship": "married",
})
check("activation retried with a valid relationship succeeds", res.status_code == 201)
res = client.post("/api/family/marry", json={
    "spouse": {"name": "Leo Spouse", "action": "create"},
    "children": [{"name": "Leo Child", "action": "create", "gender": "unknown_value"}],
})
check("an unknown child gender value is rejected (400)", res.status_code == 400)
res = client.post("/api/family/marry", json={
    "spouse": {"name": "Leo Spouse", "action": "create"},
    "marriage_status": "not_a_real_status",
})
check("an unknown marriage_status value is rejected (400)", res.status_code == 400)

print()
print("=" * 70)
print("11. Grandparents (Step 1) and Spouse's Parents (Step 3): link to husband/wife_parent_group_id")
print("=" * 70)

noah = register("Noah Grandkid")
login(noah["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Noah Father", "action": "create"}, "mother": {"name": "Noah Mother", "action": "create"},
    "father_father": {"name": "Noah PGF", "action": "create"}, "father_mother": {"name": "Noah PGM", "action": "create"},
    "mother_father": {"name": "Noah MGF", "action": "create"}, "mother_mother": {"name": "Noah MGM", "action": "create"},
    "relationship": "married",
})
check("activation with all 4 grandparents succeeds", res.status_code == 201)
noah_body = res.get_json()
noah_parents_row = raw("SELECT husband_parent_group_id, wife_parent_group_id FROM family_groups WHERE id = ?", (noah_body["parents_group_id"],))
check("the parents' unit's husband_parent_group_id (paternal grandparents) is set", noah_parents_row["husband_parent_group_id"] is not None)
check("the parents' unit's wife_parent_group_id (maternal grandparents) is set", noah_parents_row["wife_parent_group_id"] is not None)

pgf_unit = raw("SELECT name FROM family_groups WHERE id = ?", (noah_parents_row["husband_parent_group_id"],))
check("the paternal grandparents' unit is named via the husband+wife code", pgf_unit["name"] == "NOGF-NOGM-PGF & PGM Family")

# A sibling activating into the SAME parents' unit, supplying DIFFERENT grandparent names, must
# NOT overwrite the already-known grandparent links.
logout()
noah_sib = register("Noah Sibling")
login(noah_sib["private_code"])
res = client.get("/api/family/suggest", query_string={"name": "Noah Father"})
match = next(r for r in res.get_json()["results"] if r["type"] == "group")
res = client.post("/api/family/activate", json={
    "father": {"name": "Noah Father", "action": "join", "group_id": match["group_id"], "matched_node_id": match["matched_node_id"]},
    "mother": {"name": "Sib Mother", "action": "create"},
    "father_father": {"name": "Someone Else Entirely", "action": "create"},
})
check("sibling's activation (joining, with a DIFFERENT grandfather name) succeeds", res.status_code == 201)
noah_parents_row2 = raw("SELECT husband_parent_group_id FROM family_groups WHERE id = ?", (noah_body["parents_group_id"],))
check("the ORIGINAL paternal grandparents link is unchanged -- never silently overwritten",
      noah_parents_row2["husband_parent_group_id"] == noah_parents_row["husband_parent_group_id"])

logout()
login(noah["private_code"])
res = client.post("/api/family/marry", json={
    "spouse": {"name": "Noah Spouse", "action": "create"},
    "spouse_father": {"name": "Noah SF", "action": "create"}, "spouse_mother": {"name": "Noah SM", "action": "create"},
    "marriage_status": "active",
})
check("marry with spouse's parents succeeds", res.status_code == 201)
noah_marry_body = res.get_json()
# Noah registers male (register()'s own fixture) -> Noah is husband_node_id, spouse is wife_node_id
# -> the spouse's parents fill wife_parent_group_id, not husband_parent_group_id.
noah_marital_row = raw("SELECT wife_parent_group_id FROM family_groups WHERE id = ?", (noah_marry_body["marital_group_id"],))
check("the spouse's parents are linked on the SPOUSE'S side (wife_parent_group_id)", noah_marital_row["wife_parent_group_id"] is not None)
sf_unit = raw("SELECT name FROM family_groups WHERE id = ?", (noah_marital_row["wife_parent_group_id"],))
check("the spouse's parents' unit is named correctly", sf_unit["name"] == "NOSF-NOSM-SF & SM Family")

print()
print("=" * 70)
print("12. Name + location search for already-activated members, and the join-request it sends")
print("=" * 70)

logout()
mira = register("Mira Findme")
login(mira["private_code"])
client.post("/api/family/activate", json={"father": {"name": "Mira Father", "action": "create"}, "mother": {"name": "Mira Mother", "action": "create"}})
mira_parents_group_id = client.get("/api/family/status").get_json()["groups"][0]["id"]

logout()
zara = register("Zara Searcher")
login(zara["private_code"])
client.post("/api/family/activate", json={"father": {"name": "Zara Father", "action": "create"}, "mother": {"name": "Zara Mother", "action": "create"}})
res = client.get("/api/family/suggest", query_string={"name": "Mira Findme"})
real_user_hits = [r for r in res.get_json()["results"] if r["type"] == "real_user"]
check("the search finds the real, already-activated Mira (same district)", any(r["name"].startswith("Mira Findme") for r in real_user_hits))
mira_hit = next(r for r in real_user_hits if r["name"].startswith("Mira Findme"))
check("the result carries a joinable group_id (her parents' unit)", mira_hit["group_id"] == mira_parents_group_id)

res = client.post(f"/api/family-groups/{mira_hit['group_id']}/join-request", json={})
check("clicking the result sends a Join Family Group request (201)", res.status_code == 201)

logout()
login(mira["private_code"])
res = client.get("/api/people/inbox")
check("Mira (the unit's admin) receives the join request", any(r["kind"] == "family_group_join" for r in res.get_json()["requests"]))

# hide_identity exclusion: a real, name-matching, activated user who's hidden must not be returned.
logout()
hidden_user = register("Mira Hiddenone")
_conn = dbmod.get_db()
_conn.execute("UPDATE users SET hide_identity = 1 WHERE id = ?", (hidden_user["user_id"],))
_conn.commit()
_conn.close()
login(hidden_user["private_code"])
client.post("/api/family/activate", json={"father": {"name": "Hidden Father", "action": "create"}, "mother": {"name": "Hidden Mother", "action": "create"}})

logout()
login(zara["private_code"])
res = client.get("/api/family/suggest", query_string={"name": "Mira Hiddenone"})
check("a hide_identity user is excluded from name search results (not yet an established family member)",
      not any(r["type"] == "real_user" for r in res.get_json()["results"]))

print()
print("=" * 70)
print("13. Leave Group: blocked while parents/children are active members, succeeds otherwise")
print("=" * 70)

# Noah's SIBLING being a member does NOT block Noah's own leave -- a sibling is neither Noah's
# parent nor his child, and the rule is literally "parents OR children", not "any relative". The
# real blocking case needs a CLAIMED child who is an approved family_group_members row of the
# SAME group as their CLAIMED parent -- constructed fresh here, since link_node_to_user() alone
# (used above) deliberately does NOT grant group membership (that still needs a real join+approve).
logout()
blocker_parent = register("Blocker Parent")
login(blocker_parent["private_code"])
client.post("/api/family/activate", json={
    "father": {"name": "BP Father", "action": "create"}, "mother": {"name": "BP Mother", "action": "create"},
    "relationship": "married",
})
res = client.post("/api/family/marry", json={"spouse": {"name": "BP Spouse", "action": "create"}, "marriage_status": "active"})
if "marital_group_id" not in res.get_json():
    sys.exit(f"SETUP FAILED (blocker_parent marry): {res.status_code} {res.get_data(as_text=True)[:500]}")
blocker_group_id = res.get_json()["marital_group_id"]

logout()
blocker_child = register("Blocker Child")
login(blocker_child["private_code"])
res = client.get("/api/family/suggest", query_string={"name": "Blocker Parent"})
bp_match = next(r for r in res.get_json()["results"] if r["type"] == "group" and r["group_id"] == blocker_group_id)
res = client.post("/api/family/activate", json={
    "father": {"name": "Blocker Parent", "action": "join", "group_id": bp_match["group_id"], "matched_node_id": bp_match["matched_node_id"]},
    "mother": {"name": "BC Mother", "action": "create"},
})
check("blocker_child's activation (joining as blocker_parent's claimed child) succeeds", res.status_code == 201)

logout()
login(blocker_parent["private_code"])
res = client.get("/api/people/inbox")
join_req = next(r for r in res.get_json()["requests"] if r["kind"] == "family_group_join")
client.post(f"/api/people/inbox/{join_req['id']}/decide", json={"decision": "accept"})

res = client.post(f"/api/family-groups/{blocker_group_id}/leave", json={})
check("blocker_parent cannot leave their OWN unit (400)", res.status_code == 400)
check("blocker_parent is blocked as a FOUNDER first (even though their child is also an active "
      "member here) -- the founder-block check wins over the parent/child-block check",
      res.get_json().get("error", "") == "You cannot leave your own family group.")

# The parent/child-block message specifically, for a NON-founder: blocker_child (a plain joined
# member, not a founder) gets their OWN child added to the SAME unit, then tries to leave.
logout()
blocker_grandchild = register("Blocker Grandchild")
login(blocker_grandchild["private_code"])
res = client.get("/api/family/suggest", query_string={"name": "Blocker Child"})
bc_match = next(r for r in res.get_json()["results"] if r["type"] == "group" and r["group_id"] == blocker_group_id)
res = client.post("/api/family/activate", json={
    "father": {"name": "Blocker Child", "action": "join", "group_id": bc_match["group_id"], "matched_node_id": bc_match["matched_node_id"]},
    "mother": {"name": "BG Mother", "action": "create"},
})
check("blocker_grandchild's activation (joining as blocker_child's claimed child) succeeds", res.status_code == 201)

logout()
login(blocker_parent["private_code"])  # the unit's creator approves, per request_join_group()
res = client.get("/api/people/inbox")
gc_req = next(r for r in res.get_json()["requests"] if r["kind"] == "family_group_join")
client.post(f"/api/people/inbox/{gc_req['id']}/decide", json={"decision": "accept"})

logout()
login(blocker_child["private_code"])
res = client.post(f"/api/family-groups/{blocker_group_id}/leave", json={})
check("blocker_child (NOT a founder) is blocked by the parent/child-block instead (400)", res.status_code == 400)
check("the error message names parents/children specifically for a non-founder block",
      "parents/children" in res.get_json().get("error", ""))

# A lone user with no parent/child co-members in their OWN freshly-created unit can leave freely.
logout()
loner = register("Loner Solo")
login(loner["private_code"])
res = client.post("/api/family/activate", json={"father": {"name": "Loner Father", "action": "create"}, "mother": {"name": "Loner Mother", "action": "create"}})
loner_group_id = res.get_json()["parents_group_id"]
res = client.post(f"/api/family-groups/{loner_group_id}/leave", json={})
check("a user with no active parent/child co-members can leave (200)", res.status_code == 200)
left_row = raw("SELECT status FROM family_group_members WHERE group_id = ? AND user_id = ?", (loner_group_id, loner["user_id"]))
check("their membership status is 'left', not deleted", left_row["status"] == "left")
res = client.get(f"/api/family/node/{loner_group_id}/neighborhood")
check("a 'left' member no longer sees the unit's neighborhood (404)", res.status_code == 404)

print()
print("=" * 70)
print("14. Chat list: dormancy filter, is_founder tagging, and the D3 tree keeping dormant units")
print("=" * 70)

dormant_user = register("Dormant Test User")
login(dormant_user["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Dead Grandad", "action": "create", "is_deceased": True},
    "mother": {"name": "Dead Grandma", "action": "create", "is_deceased": True},
    "relationship": "married",
})
dormant_body = res.get_json()
res = client.post("/api/family/marry", json={"spouse": {"name": "Dormant Test Spouse", "action": "create"}, "marriage_status": "active"})
dormant_marital_id = res.get_json()["marital_group_id"]

status = client.get("/api/family/status").get_json()
group_ids_in_list = {g["id"] for g in status["groups"]}
check("the dormant parents' unit (both founders deceased) does NOT appear in the chat list",
      dormant_body["parents_group_id"] not in group_ids_in_list)
check("the user's own (non-dormant) marital unit DOES appear in the chat list",
      dormant_marital_id in group_ids_in_list)

own_unit_row = next(g for g in status["groups"] if g["id"] == dormant_marital_id)
check("is_founder=True for the user's own founded unit ('My Family')", own_unit_row["is_founder"] is True)

nbh = client.get(f"/api/family/node/{dormant_marital_id}/neighborhood").get_json()
dormant_parent_entry = next(pg for pg in nbh["parent_groups"] if pg["group_id"] == dormant_body["parents_group_id"])
check("the dormant unit STILL appears in the D3 neighborhood view (as a faded root ancestor)",
      dormant_parent_entry is not None)
check("the D3 view correctly flags it as dormant", dormant_parent_entry["is_dormant"] is True)

# is_founder=False for a plain joined unit (the parents' unit a child is a member of, not a founder
# of) -- reusing an earlier, non-dormant scenario (greg, from section 2/8, still has living parents).
greg_status = None
logout()
login(greg["private_code"])
greg_status = client.get("/api/family/status").get_json()
greg_parents_row = next(g for g in greg_status["groups"] if g["id"] == greg_body["parents_group_id"])
check("is_founder=False for a plain child-member's parents' unit ('Joined Family')", greg_parents_row["is_founder"] is False)

print()
print("=" * 70)
print("15. Explicit tree growth: the '+Add' parents/child routes")
print("=" * 70)

grower = register("Grower Self")
login(grower["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Grower Father", "action": "create"}, "mother": {"name": "Grower Mother", "action": "create"},
    "relationship": "married",
})
grower_body = res.get_json()
grower_parents_id = grower_body["parents_group_id"]  # husband=father, wife=mother -- neither side's own parents known yet
res = client.post("/api/family/marry", json={"spouse": {"name": "Grower Spouse", "action": "create"}, "marriage_status": "active"})
grower_marital_id = res.get_json()["marital_group_id"]

# "+ Add Father's Family": fills husband_parent_group_id on grower's PARENTS' unit (i.e. the
# paternal grandparents).
res = client.post(f"/api/family/node/{grower_parents_id}/add-parents",
                   json={"side": "husband", "father": {"name": "Paternal Grandpa"}, "mother": {"name": "Paternal Grandma"}})
check("add-parents (husband side, both names) succeeds (201)", res.status_code == 201)
grandparents_group_id = res.get_json()["parent_group_id"]
check("a new grandparents' unit was created", grandparents_group_id is not None)
row = raw("SELECT husband_parent_group_id FROM family_groups WHERE id = ?", (grower_parents_id,))
check("grower's parents' unit now has husband_parent_group_id set", row["husband_parent_group_id"] == grandparents_group_id)
nbh = client.get(f"/api/family/node/{grower_parents_id}/neighborhood").get_json()
check("the new grandparents' unit shows up in the neighborhood view, tagged side=husband",
      any(pg["group_id"] == grandparents_group_id and pg["side"] == "husband" for pg in nbh["parent_groups"]))

# Repeating on the SAME side is rejected -- additive only, never an overwrite.
res = client.post(f"/api/family/node/{grower_parents_id}/add-parents",
                   json={"side": "husband", "father": {"name": "Someone Else"}, "mother": None})
check("add-parents on an already-filled side is rejected (400)", res.status_code == 400)
check("...with a clear 'already added' message", "already added" in res.get_json().get("error", ""))

res = client.post(f"/api/family/node/{grower_parents_id}/add-parents", json={"side": "sideways", "father": {"name": "X"}})
check("an unknown side is rejected (400)", res.status_code == 400)

res = client.post(f"/api/family/node/{grower_parents_id}/add-parents", json={"side": "wife", "father": None, "mother": None})
check("add-parents with neither parent named is rejected (400)", res.status_code == 400)

# A stranger (not an admin of this unit) cannot grow someone else's tree.
stranger = register("Stranger NoAccess")
login(stranger["private_code"])
res = client.post(f"/api/family/node/{grower_parents_id}/add-parents",
                   json={"side": "wife", "father": {"name": "Intruder Father"}, "mother": None})
check("a non-admin stranger is refused with 403, not 400/201", res.status_code == 403)

# "+ Add Child": a plain placeholder child of grower's OWN marital unit.
login(grower["private_code"])
res = client.post(f"/api/family/node/{grower_marital_id}/add-child", json={"name": "Grower Child One", "gender": "female"})
check("add-child on grower's own unit succeeds (201)", res.status_code == 201)
child_node_id = res.get_json()["node_id"]
nbh = client.get(f"/api/family/node/{grower_marital_id}/neighborhood").get_json()
check("the new child appears in unmarried_children", any(p["id"] == child_node_id for p in nbh["unmarried_children"]))

# "+ Add Sibling" is the EXACT SAME primitive, just targeting a different unit's group_id (here,
# the grandparents' unit from above) -- proving the one-primitive-two-buttons design, not a
# second code path.
res = client.post(f"/api/family/node/{grandparents_group_id}/add-child", json={"name": "Grower Uncle", "gender": "male"})
check("the same add-child route, targeted at the grandparents' unit, adds a 'sibling-in-law' there (201)", res.status_code == 201)

res = client.post(f"/api/family/node/{grower_marital_id}/add-child", json={"name": "", "gender": "male"})
check("add-child with a blank name is rejected (400)", res.status_code == 400)
res = client.post(f"/api/family/node/{grower_marital_id}/add-child", json={"name": "Bad Gender Kid", "gender": "nonbinary-typo"})
check("add-child with an invalid gender value is rejected (400)", res.status_code == 400)

logout()
login(stranger["private_code"])
res = client.post(f"/api/family/node/{grower_marital_id}/add-child", json={"name": "Intruder Kid"})
check("a non-admin stranger cannot add-child to someone else's unit either (403)", res.status_code == 403)

print()
print("=" * 70)
print("16. Profile pictures: upload, Pillow processing, serving, and the hide_identity gate")
print("=" * 70)


def _tiny_image_bytes(fmt="PNG", size=(40, 30), color=(200, 60, 10)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=fmt)
    return buf.getvalue()


logout()
login(grower["private_code"])

res = client.post("/api/profile/picture", data={"picture": (io.BytesIO(_tiny_image_bytes()), "me.png", "image/png")})
check("uploading a valid PNG succeeds (200)", res.status_code == 200)

res = client.get(f"/api/users/{grower['user_id']}/profile-picture")
check("the picture is served back (200)", res.status_code == 200)
check("served as image/jpeg (always re-encoded, whatever the upload format was)", res.mimetype == "image/jpeg")
check("nosniff header present", res.headers.get("X-Content-Type-Options") == "nosniff")
served_img = Image.open(io.BytesIO(res.data))
check("stored thumbnail is exactly 256x256", served_img.size == (256, 256))
check("EXIF was stripped (no exif data block on the re-saved JPEG)", not served_img.getexif())

res = client.get("/api/me")
check("/api/me now reports has_profile_picture = true", res.get_json()["has_profile_picture"] is True)

# A non-rectangular upload still comes out 256x256 (center-cropped, not squashed).
res = client.post("/api/profile/picture", data={"picture": (io.BytesIO(_tiny_image_bytes(size=(300, 90))), "wide.png", "image/png")})
check("re-uploading a wide (non-square) image still succeeds (200)", res.status_code == 200)
served_img2 = Image.open(io.BytesIO(client.get(f"/api/users/{grower['user_id']}/profile-picture").data))
check("a wide upload is still stored as a 256x256 square (center-cropped)", served_img2.size == (256, 256))

# Type allowlist: extension/content-type must both be an allowed image type, and must agree.
res = client.post("/api/profile/picture", data={"picture": (io.BytesIO(b"not really an image"), "shell.svg", "image/svg+xml")})
check("an .svg upload is rejected (400)", res.status_code == 400)
res = client.post("/api/profile/picture", data={"picture": (io.BytesIO(_tiny_image_bytes()), "me.png", "image/gif")})
check("a .png filename declared as image/gif is rejected -- extension and type disagree (400)", res.status_code == 400)

# Size cap: 3MB raw-upload ceiling. A file this far over also trips Flask's own global
# MAX_CONTENT_LENGTH (set to the same 3MB, app.py line ~168) before our view even runs, so the
# response here is werkzeug's own 413, not our friendly 400 -- both are "rejected, not stored",
# which is what matters; profile_picture_core.save_profile_picture()'s own ValueError path (for a
# body that slips in just under werkzeug's cap but over ours) is covered directly below instead.
oversized = b"\xff" * (3 * 1024 * 1024 + 1)
res = client.post("/api/profile/picture", data={"picture": (io.BytesIO(oversized), "huge.png", "image/png")})
check("an upload well over 3MB is rejected, not stored (400 or 413)", res.status_code in (400, 413))

import profile_picture_core as _ppc  # noqa: E402  (imported here, not at module top, purely for this one direct-unit check)
_conn2 = dbmod.get_db()
try:
    _ppc.save_profile_picture(_conn2, grower["user_id"], "huge.png", "image/png", oversized)
    check("save_profile_picture() itself rejects an oversized image with ValueError", False)
except ValueError as e:
    check("save_profile_picture() itself rejects an oversized image with ValueError", True)
    check("...with a message naming the limit", "3 MB" in str(e))
finally:
    _conn2.close()

res = client.post("/api/profile/picture", data={})
check("a request with no file at all is rejected cleanly (400), not a 500", res.status_code == 400)

# hide_identity gate: the SAME rule that already masks a hidden user's name also hides their
# picture, for anyone who isn't an established family member.
hidden_pic_user = register("HiddenPic Person")
_conn = dbmod.get_db()
_conn.execute("UPDATE users SET hide_identity = 1 WHERE id = ?", (hidden_pic_user["user_id"],))
_conn.commit()
_conn.close()
login(hidden_pic_user["private_code"])
client.post("/api/profile/picture", data={"picture": (io.BytesIO(_tiny_image_bytes()), "hidden.png", "image/png")})
res = client.get(f"/api/users/{hidden_pic_user['user_id']}/profile-picture")
check("the hidden user can still see their own picture (200)", res.status_code == 200)

logout()
login(stranger["private_code"])
res = client.get(f"/api/users/{hidden_pic_user['user_id']}/profile-picture")
check("a stranger gets 404 for a hide_identity user's picture, same as their masked name", res.status_code == 404)

# Search suggestions now carry gender + profile_picture_url for a real, already-activated match.
logout()
login(grower["private_code"])
res = client.get("/api/family/suggest", query_string={"name": "Stranger NoAccess"})
suggest_hits = [r for r in res.get_json()["results"] if r["type"] in ("real_user", "unactivated_user")]
check("a search match (unactivated, no picture) carries gender and a null profile_picture_url",
      any(h.get("gender") == "male" and h.get("profile_picture_url") is None for h in suggest_hits))

print()
print("=" * 70)
print("17. Family Group naming: the husband+wife code, verified against every worked example")
print("=" * 70)


def _expected_name(husband_name, wife_name, husband_middle=None, wife_middle=None):
    hf, hm, hl = family_core._split_name_parts(husband_name, husband_middle)
    wf, wm, wl = family_core._split_name_parts(wife_name, wife_middle)
    h_code = family_core._name_code(hf, hm, hl) if hf else ""
    w_code = family_core._name_code(wf, wm, wl, fallback_last=hl) if wf else ""
    codes = "-".join(c for c in (h_code, w_code) if c)
    if hl and wl:
        surname = hl if hl.lower() == wl.lower() else f"{hl} & {wl}"
    else:
        surname = hl or wl
    return f"{codes}-{surname} Family" if surname else f"{codes} Family"


check("_name_code: 'A'/'P J Abdul'/'Kalam' -> APAM", family_core._name_code("A", "P J Abdul", "Kalam") == "APAM")
check("_name_code: 'Vishal'/-/'Kumar' -> VIAR", family_core._name_code("Vishal", "", "Kumar") == "VIAR")
check("_name_code: 'Sakshi' (no last, fallback=Kumar) -> SAAR", family_core._name_code("Sakshi", "", "", fallback_last="Kumar") == "SAAR")
check("_name_code: 'Rohit'/-/'Mudgal' -> ROAL", family_core._name_code("Rohit", "", "Mudgal") == "ROAL")
check("_name_code: 'Ria' (no last, fallback=Mudgal) -> RIAL", family_core._name_code("Ria", "", "", fallback_last="Mudgal") == "RIAL")
check("_name_code: 'Amit' (no last, no fallback) self-pads -> AMIT", family_core._name_code("Amit", "", "") == "AMIT")
check("_name_code: 'Priya'/-/'Sharma' -> PRMA", family_core._name_code("Priya", "", "Sharma") == "PRMA")

naming_codex = register("Codex Husband")
login(naming_codex["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Sunil Thakur", "action": "create"}, "mother": {"name": "Priya Thakur", "action": "create"},
})
check("shared-surname couple names the unit without '&' (Thakur, not 'Thakur & Thakur')",
      res.get_json()["parents_group_name"] == _expected_name("Sunil Thakur", "Priya Thakur") == "SUUR-PRUR-Thakur Family")

logout()
naming_codex2 = register("Codex Husband Two")
login(naming_codex2["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Amit Sharma", "action": "create"}, "mother": {"name": "Priya Verma", "action": "create"},
})
check("differing surnames join with '&' (husband's last name first)",
      res.get_json()["parents_group_name"] == _expected_name("Amit Sharma", "Priya Verma") == "AMMA-PRMA-Sharma & Verma Family")

logout()
naming_codex3 = register("Codex Husband Three")
login(naming_codex3["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Amit", "action": "create"}, "mother": {"name": "Priya Sharma", "action": "create"},
})
check("husband with no last name at all: only the wife's surname trails the group name",
      res.get_json()["parents_group_name"] == _expected_name("Amit", "Priya Sharma") == "AMIT-PRMA-Sharma Family")

print()
print("=" * 70)
print("18. Middle name: optional field, carried through registration, and self-service edit")
print("=" * 70)

mn_user = register("Middlename Carrier")
_conn3 = dbmod.get_db()
_conn3.execute("UPDATE users SET middle_name = ? WHERE id = ?", ("Kumar", mn_user["user_id"]))
_conn3.commit()
_conn3.close()
login(mn_user["private_code"])
res = client.get("/api/me")
check("middle_name round-trips through /api/me", res.get_json()["middle_name"] == "Kumar")

# A fresh registration with no middle name at all leaves it blank, not some placeholder.
no_mn_user = register("No Middlename Person")
login(no_mn_user["private_code"])
res = client.get("/api/me")
check("a user who never set a middle name reports an empty string, not null/error", res.get_json()["middle_name"] == "")

# Editing it goes through the SAME council-approval queue as name/email/phone -- never applied
# immediately, consistent with every other PROFILE_CHANGE_FIELDS entry.
res = client.post("/api/dashboard/edit-request", json={"middle_name": "Prasad", "reason": "Adding my middle name"})
check("middle_name edit is queued, not applied immediately (201)", res.status_code == 200 and res.get_json()["status"] == "queued")
res = client.get("/api/me")
check("the queued middle_name has NOT applied yet", res.get_json()["middle_name"] == "")

req_row = raw("SELECT id FROM profile_change_requests WHERE user_id = ? AND status = 'pending' ORDER BY id DESC LIMIT 1", (no_mn_user["user_id"],))
os.environ["QM_ADMIN_PRIVATE_IDS"] = no_mn_user["private_code"]  # self-approval is fine here -- only exercising the generic apply path, not scope rules (already covered by test_admin_panel_council_scope.py)
res = client.post(f"/api/admin/profile-changes/{req_row['id']}/decide", json={"approve": True})
check("admin approval applies the queued middle_name change (200)", res.status_code == 200)
res = client.get("/api/me")
check("middle_name now reflects the approved change", res.get_json()["middle_name"] == "Prasad")
del os.environ["QM_ADMIN_PRIVATE_IDS"]

# The claimed founder's naming code must use their OWN users.middle_name (just approved above),
# not a between-tokens guess off their display name -- the DB join _name_parts_for_node() does.
res = client.post("/api/family/activate", json={
    "father": {"name": "NMN Father", "action": "create"}, "mother": {"name": "NMN Mother", "action": "create"},
    "relationship": "married",
})
check("the middle-name-bearing user's own activation succeeds", res.status_code == 201)
res = client.post("/api/family/marry", json={"spouse": {"name": "NMN Spouse", "action": "create"}, "marriage_status": "active"})
check("marrying succeeds", res.status_code == 201)
marital_name = res.get_json()["marital_group_name"]
no_mn_user_name = raw("SELECT name FROM users WHERE id = ?", (no_mn_user["user_id"],))["name"]
expected = _expected_name(no_mn_user_name, "NMN Spouse", husband_middle="Prasad")
check("the claimed founder's approved middle_name feeds the naming code via the DB join, not a guess",
      marital_name == expected)

print()
print("=" * 70)
print("19. Grandparent auto-membership (2026-10-26): a claimed child joins BOTH sets of grandparents")
print("=" * 70)

hubby = register("Hubby Rao")
login(hubby["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Hubby Father", "action": "create"}, "mother": {"name": "Hubby Mother", "action": "create"},
    "relationship": "married",
})
hubby_body = res.get_json()
paternal_grandparents_group_id = hubby_body["parents_group_id"]

res = client.post("/api/family/marry", json={
    "spouse": {"name": "Wifey Rao", "action": "create"},
    "spouse_father": {"name": "Wifey Father", "action": "create"}, "spouse_mother": {"name": "Wifey Mother", "action": "create"},
    "children": [{"name": "Kid Placeholder", "action": "create"}],
    "marriage_status": "active",
})
check("hubby marries, sets BOTH sides' parent units, and adds a child placeholder in one call", res.status_code == 201)
marry_body = res.get_json()
marital_group_id = marry_body["marital_group_id"]
marital_row = raw("SELECT husband_parent_group_id, wife_parent_group_id FROM family_groups WHERE id = ?", (marital_group_id,))
maternal_grandparents_group_id = marital_row["wife_parent_group_id"]
check("husband_parent_group_id (paternal grandparents) is set", marital_row["husband_parent_group_id"] == paternal_grandparents_group_id)
check("wife_parent_group_id (maternal grandparents) is set", maternal_grandparents_group_id is not None)

child_node = raw("SELECT id FROM family_nodes WHERE display_name = 'Kid Placeholder'")

logout()
kid = register("Kid Rao")
kid_search_code = client.get("/api/people/me").get_json()["search_code"]  # session is kid's right after registering

login(hubby["private_code"])
res = client.post(f"/api/family/node/{child_node['id']}/link", json={"user_id": kid_search_code})
check("hubby (admin of the marital unit) links the child placeholder to kid's real account", res.status_code == 200)

kid_paternal_row = raw(
    "SELECT status, is_admin FROM family_group_members WHERE group_id = ? AND user_id = ?",
    (paternal_grandparents_group_id, kid["user_id"]),
)
check("kid automatically joined the PATERNAL grandparents' unit as a plain member",
      kid_paternal_row is not None and kid_paternal_row["status"] == "approved" and kid_paternal_row["is_admin"] == 0)
kid_maternal_row = raw(
    "SELECT status, is_admin FROM family_group_members WHERE group_id = ? AND user_id = ?",
    (maternal_grandparents_group_id, kid["user_id"]),
)
check("kid automatically joined the MATERNAL grandparents' unit as a plain member",
      kid_maternal_row is not None and kid_maternal_row["status"] == "approved" and kid_maternal_row["is_admin"] == 0)
kid_marital_row = raw(
    "SELECT status, is_admin FROM family_group_members WHERE group_id = ? AND user_id = ?", (marital_group_id, kid["user_id"])
)
check("kid is also a plain member of their own parents' (hubby+wifey's) marital unit",
      kid_marital_row is not None and kid_marital_row["status"] == "approved" and kid_marital_row["is_admin"] == 0)

print()
print("=" * 70)
print("20. The three real-world exit rules (2026-10-26): in-laws unit (voluntary leave), birth unit "
      "(locked while unmarried), founder (never), and the admin-initiated rejoin flow")
print("=" * 70)

# 20a. THE IN-LAWS UNIT (voluntary leave) -- the exact bug scenario: a wife auto-joins her
# husband's parents' unit, her own child is LATER auto-joined there too (as a grandchild), and she
# must still be free to leave it -- the old unscoped parent/child-block would have refused this.
ravi = register("Ravi Founder")
login(ravi["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Ravi Father", "action": "create"}, "mother": {"name": "Ravi Mother", "action": "create"},
    "relationship": "married",
})
ravi_body = res.get_json()
ravi_birth_unit_id = ravi_body["parents_group_id"]  # Ravi's OWN parents' unit -- Meera's future in-laws unit
res = client.post("/api/family/marry", json={
    "spouse": {"name": "Meera Wife", "action": "create"},
    "children": [{"name": "Arjun Kid", "action": "create"}],
    "marriage_status": "active",
})
ravi_marry_body = res.get_json()
ravi_marital_id = ravi_marry_body["marital_group_id"]
meera_placeholder_node = raw("SELECT id FROM family_nodes WHERE display_name = 'Meera Wife'")
arjun_placeholder_node = raw("SELECT id FROM family_nodes WHERE display_name = 'Arjun Kid'")

logout()
meera = register("Meera Wife Real")
login(meera["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Meera Father", "action": "create"}, "mother": {"name": "Meera Mother", "action": "create"},
    "relationship": "married",
})
res = client.post("/api/family/marry", json={
    "spouse": {"name": "Meera Wife", "action": "join", "group_id": ravi_marital_id, "matched_node_id": meera_placeholder_node["id"]},
})
check("meera auto-joins ravi's unit as his wife (instant, no approval)", res.status_code == 201)
meera_inlaw_row = raw("SELECT status, is_admin FROM family_group_members WHERE group_id = ? AND user_id = ?", (ravi_birth_unit_id, meera["user_id"]))
check("meera automatically joined ravi's PARENTS' unit (her in-laws) as a plain member",
      meera_inlaw_row is not None and meera_inlaw_row["status"] == "approved" and meera_inlaw_row["is_admin"] == 0)

logout()
arjun = register("Arjun Kid Real")
arjun_search_code = client.get("/api/people/me").get_json()["search_code"]  # session is arjun's right after registering
login(ravi["private_code"])  # ravi (admin of his own marital unit) links the child placeholder
res = client.post(f"/api/family/node/{arjun_placeholder_node['id']}/link", json={"user_id": arjun_search_code})
check("ravi links arjun's placeholder to his real account", res.status_code == 200)
arjun_inlaw_row = raw("SELECT status FROM family_group_members WHERE group_id = ? AND user_id = ?", (ravi_birth_unit_id, arjun["user_id"]))
check("arjun (the grandchild) is ALSO now an active member of ravi's parents' unit -- the exact "
      "condition that used to wrongly block meera from leaving it",
      arjun_inlaw_row is not None and arjun_inlaw_row["status"] == "approved")

login(meera["private_code"])
res = client.post(f"/api/family-groups/{ravi_birth_unit_id}/leave", json={})
check("meera CAN voluntarily leave her in-laws' unit, even though her own child is also active there (the fix)",
      res.status_code == 200)
meera_inlaw_row = raw("SELECT status FROM family_group_members WHERE group_id = ? AND user_id = ?", (ravi_birth_unit_id, meera["user_id"]))
check("meera's in-laws membership is now 'left'", meera_inlaw_row["status"] == "left")

# 20c. THE FOUNDER (never) -- meera cannot leave her OWN marital unit, the one her marriage founded.
res = client.post(f"/api/family-groups/{ravi_marital_id}/leave", json={})
check("meera (a founder of her OWN marital unit) cannot leave it (400)", res.status_code == 400)
check("the error names the founder rule specifically", res.get_json().get("error") == "You cannot leave your own family group.")

# 20b. THE BIRTH UNIT (cannot leave voluntarily while unmarried) -- a plain, unmarried child-member
# whose real, claimed parent is also active in that SAME unit (the technique section 13 already
# established: match a FOUNDER's own self-node as "father", so the parent is a real family_group_members
# row, not an unclaimed placeholder the blocking JOIN could never match).
priya = register("Priya Solo")
login(priya["private_code"])
res = client.get("/api/family/suggest", query_string={"name": "Ravi Founder"})
ravi_match = next(r for r in res.get_json()["results"] if r["type"] == "group" and r["group_id"] == ravi_marital_id)
res = client.post("/api/family/activate", json={
    "father": {"name": "Ravi Founder", "action": "join", "group_id": ravi_match["group_id"], "matched_node_id": ravi_match["matched_node_id"]},
    "mother": {"name": "Priya Solo Mother", "action": "create"},
})
check("priya's activation (joining ravi's marital unit as his child) succeeds", res.status_code == 201)
login(ravi["private_code"])
res = client.get("/api/people/inbox")
priya_req = next(r for r in res.get_json()["requests"] if r["kind"] == "family_group_join")
client.post(f"/api/people/inbox/{priya_req['id']}/decide", json={"decision": "accept"})

login(priya["private_code"])
res = client.post(f"/api/family-groups/{ravi_marital_id}/leave", json={})
check("priya (unmarried, plain member of her BIRTH unit, her real father still active there) cannot leave it (400)",
      res.status_code == 400)
check("the error names parents/children specifically", "parents/children" in res.get_json().get("error", ""))

# 20d. THE REJOIN FLOW -- a removed member cannot self-request back in; only an admin invite (which
# flips their row to 'pending', not silently leaving it at 'left') followed by their own acceptance
# restores 'approved'.
res = client.post(f"/api/family-groups/{ravi_marital_id}/remove-member", json={"user_id": priya["user_id"]})
check("priya cannot remove herself via remove-member (403, not admin)", res.status_code == 403)

login(ravi["private_code"])
res = client.post(f"/api/family-groups/{ravi_marital_id}/remove-member", json={"user_id": priya["user_id"]})
check("ravi (admin of his own unit) removes priya", res.status_code == 200)
priya_row = raw("SELECT status FROM family_group_members WHERE group_id = ? AND user_id = ?", (ravi_marital_id, priya["user_id"]))
check("priya's membership is now 'left'", priya_row["status"] == "left")

login(meera["private_code"])  # meera is still a co-admin of ravi's unit via her own founder grant
res = client.post(f"/api/family-groups/{ravi_marital_id}/remove-member", json={"user_id": ravi["user_id"]})
check("removing a founder is rejected, even by a co-admin (400)", res.status_code == 400)
check("the error names the founder-removal rule specifically",
      res.get_json().get("error") == "A founder cannot be removed from their own family group.")

login(priya["private_code"])
res = client.post(f"/api/family-groups/{ravi_marital_id}/join-request", json={})
check("priya cannot self-request back in after being removed (400) -- rejoin is admin-initiated only",
      res.status_code == 400)

login(ravi["private_code"])
res = client.post(f"/api/family-groups/{ravi_marital_id}/invite", json={"user_id": priya["user_id"]})
check("ravi invites priya back", res.status_code == 201)
priya_row = raw("SELECT status FROM family_group_members WHERE group_id = ? AND user_id = ?", (ravi_marital_id, priya["user_id"]))
check("priya's row flips from 'left' to 'pending' the moment the invite is sent, not silently left at 'left'",
      priya_row["status"] == "pending")

login(priya["private_code"])
res = client.get("/api/people/inbox")
rejoin_req = next(r for r in res.get_json()["requests"] if r["kind"] == "family_group_invite")
res = client.post(f"/api/people/inbox/{rejoin_req['id']}/decide", json={"decision": "accept"})
check("priya accepts the re-invite", res.status_code == 200)
priya_row = raw("SELECT status FROM family_group_members WHERE group_id = ? AND user_id = ?", (ravi_marital_id, priya["user_id"]))
check("priya's membership is 'approved' again", priya_row["status"] == "approved")

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
