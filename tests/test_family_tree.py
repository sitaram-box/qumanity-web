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
check("unit named after eldest founder (PSharma Family Group)", body.get("parents_group_name") == "PSharma Family Group")

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
print("2. Deceased father: naming now follows the single alive-eldest rule (the living mother wins)")
print("=" * 70)

greg = register("Greg Patel")
login(greg["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Deceased Patel", "action": "create", "is_deceased": True},
    "mother": {"name": "Living Mother Patel", "action": "create"},
})
check("activation with a deceased father succeeds", res.status_code == 201)
greg_body = res.get_json()
check("naming picks the ALIVE founder (mother), not the deceased father -- the old generation-first "
      "lineage rule is retired; under the Nuclear Node model there's one alive-and-eldest rule, "
      "applied to exactly the two founders",
      greg_body["parents_group_name"] == "LPatel Family Group")
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
      not any(r["type"] == "group" and r["group_name"] == "PSharma Family Group" for r in results))

res = client.get("/api/family/suggest", query_string={"name": "Nobody At All Xyz"})
check("no-match search returns type=none", res.get_json()["results"] == [{"type": "none"}])

print()
print("=" * 70)
print("6. Spousal join: claims the OTHER (open) founder slot directly, grants founder-admin")
print("=" * 70)

logout()
dana = register("Dana Mehta")
set_married(dana["private_code"])
login(dana["private_code"])
res = client.get("/api/family/suggest", query_string={"name": "Diana Mehta"})
spouse_match = next(r for r in res.get_json()["results"] if r["type"] == "group")
check("dana finds carl's unit via the spouse name", spouse_match["group_name"] is not None)

res = client.post("/api/family/activate", json={"father": {"name": "Dana Father", "action": "create"}, "mother": {"name": "Dana Mother", "action": "create"}})
check("dana activates (parents' unit) before marrying in", res.status_code == 201)
res = client.post("/api/family/marry", json={
    "spouse": {"name": "Diana Mehta", "action": "join", "group_id": spouse_match["group_id"], "matched_node_id": spouse_match["matched_node_id"]},
})
check("dana's marry-join request into carl's unit succeeds", res.status_code == 201)

res = client.get(f"/api/family-groups/{carl_body['marital_group_id']}/tree")
check("dana cannot see carl's unit before approval (404)", res.status_code == 404)

login(carl["private_code"])
res = client.get("/api/people/inbox")
join_req = next(r for r in res.get_json()["requests"] if r["kind"] == "family_group_join")
check("carl's inbox shows the family_group_join request", join_req is not None)
res = client.post(f"/api/people/inbox/{join_req['id']}/decide", json={"decision": "accept"})
check("carl accepts dana's join request", res.status_code == 200)

login(dana["private_code"])
res = client.get(f"/api/family-groups/{carl_body['marital_group_id']}/tree")
check("dana can now see the unit (200)", res.status_code == 200)
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
mother_node = next(n for n in greg_tree["nodes"] if n["name"] == "Living Mother Patel")
logout()
login(greg["private_code"])
res = client.post(f"/api/family/node/{mother_node['id']}/link", json={"user_id": hank["account_id"]})
check("admin can link an empty node by Account ID", res.status_code == 200)
mother_row = raw("SELECT claimed_user_id, status FROM family_nodes WHERE id = ?", (mother_node["id"],))
check("the node is now claimed by hank", mother_row["claimed_user_id"] == hank["user_id"] and mother_row["status"] == "claimed")
check("hank, having claimed a founder slot, is now also an admin of greg's parents' unit",
      bool(raw("SELECT is_admin FROM family_group_members WHERE group_id = ? AND user_id = ?",
                (greg_body["parents_group_id"], hank["user_id"]))["is_admin"]))

res = client.post(f"/api/family/node/{mother_node['id']}/link", json={"user_id": hank["account_id"]})
check("re-linking an already-claimed node is rejected (400)", res.status_code == 400)

jill = register("Jill Patel")
logout()
login(greg["private_code"])  # registering jill switched the session to jill -- switch back to the admin
res = client.post(f"/api/family/node/{father_node['id']}/link", json={"user_id": hank["account_id"]})
check("linking a user who's already claimed elsewhere is rejected (400)", res.status_code == 400)

res = client.post(f"/api/family/node/{father_node['id']}/link", json={"user_id": 999999})
check("linking a nonexistent user id is rejected (400)", res.status_code == 400)

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
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
