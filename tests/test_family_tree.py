"""Verifies the Family Tree / Family Groups backend, Phase 1 + the 2026-10-20 lineage/marital
restructure: activate_timeline() (pure lineage -- father/mother only), marry_timeline() (spouse +
children, a separate later call), the two different naming algorithms (generation-rank for
lineage, alive-and-eldest for marital), is_deceased, the family_group_members.is_admin derivation
on an approved join (spouse edge to an existing admin -> admin; anything else -> plain member),
tree_for_group()'s scoped 404, and that activating twice is rejected.

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

ROOT = "/Users/macmudgal/Desktop/Qumanity_DPG"
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
print("1. Basic activation: father+mother only (pure lineage, no spouse)")
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
check("lineage group created", "lineage_group_id" in body)
check("no marital group created (single, no spouse yet)", "marital_group_id" not in body)
check("lineage group named after eldest father (PSharma Family Group)", body.get("lineage_group_name") == "PSharma Family Group")

res = client.get("/api/family/status")
check("now activated", res.get_json()["activated"] is True)
check("status shows the new lineage group, admin=True", any(g["id"] == body["lineage_group_id"] and g["is_admin"] for g in res.get_json()["groups"]))

res = client.post("/api/family/activate", json={"father": {"name": "X", "action": "create"}, "mother": {"name": "Y", "action": "create"}})
check("re-activating is rejected (400)", res.status_code == 400)

tree = client.get(f"/api/family-groups/{body['lineage_group_id']}/tree").get_json()
check("lineage tree has 3 nodes (self, father, mother)", len(tree["nodes"]) == 3)
check("lineage tree kind is 'lineage'", tree["kind"] == "lineage")
check("activating user IS admin of their own lineage group (acting custodian)", tree["is_admin"] is True)

print()
print("=" * 70)
print("2. Deceased father: lineage naming still uses his name; the living child is still admin")
print("=" * 70)

greg = register("Greg Patel")
login(greg["private_code"])
res = client.post("/api/family/activate", json={
    "father": {"name": "Deceased Patel", "action": "create", "is_deceased": True},
    "mother": {"name": "Living Mother Patel", "action": "create"},
})
check("activation with a deceased father succeeds", res.status_code == 201)
greg_body = res.get_json()
check("lineage name still comes from the (deceased) father", greg_body["lineage_group_name"] == "DPatel Family Group")
greg_tree = client.get(f"/api/family-groups/{greg_body['lineage_group_id']}/tree").get_json()
father_node = next(n for n in greg_tree["nodes"] if n["name"] == "Deceased Patel")
check("father node is flagged is_deceased", father_node["is_deceased"] is True)
check("the living child (greg) is still the group's admin, not the deceased father", greg_tree["is_admin"] is True)

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
print("4. Marriage: a SEPARATE call creates a marital group; spouse join grants co-admin")
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
check("carl activates (lineage only)", res.status_code == 201)

res = client.post("/api/family/marry", json={
    "spouse": {"name": "Diana Mehta", "action": "create"},
    "children": [{"name": "Evan Mehta", "action": "create"}, {"name": "Fiona Mehta", "action": "create"}],
})
check("marry succeeds and creates a marital group", res.status_code == 201)
carl_body = res.get_json()
check("marital group created", "marital_group_id" in carl_body)
carl_tree = client.get(f"/api/family-groups/{carl_body['marital_group_id']}/tree").get_json()
check("marital tree kind is 'marital'", carl_tree["kind"] == "marital")
check("marital tree has 4 nodes (self, spouse, 2 children)", len(carl_tree["nodes"]) == 4)
check("marital tree has 1 spouse link", len(carl_tree["spouse_links"]) == 1)
check("marital tree has 4 parent links (2 children x 2 parents)", len(carl_tree["parent_links"]) == 4)

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
check("does NOT suggest alice's own group back to herself (already a member)",
      not any(r["type"] == "group" and r["group_name"] == "PSharma Family Group" for r in results))

res = client.get("/api/family/suggest", query_string={"name": "Nobody At All Xyz"})
check("no-match search returns type=none", res.get_json()["results"] == [{"type": "none"}])

print()
print("=" * 70)
print("6. Join-request admin derivation: spouse joining -> admin; child joining -> plain member")
print("=" * 70)

logout()
dana = register("Dana Mehta")
set_married(dana["private_code"])
login(dana["private_code"])
res = client.get("/api/family/suggest", query_string={"name": "Diana Mehta"})
spouse_match = next(r for r in res.get_json()["results"] if r["type"] == "group" and r["group_kind"] == "marital")
check("dana finds carl's marital group via the spouse name", spouse_match["group_name"] is not None)

res = client.post("/api/family/activate", json={"father": {"name": "Dana Father", "action": "create"}, "mother": {"name": "Dana Mother", "action": "create"}})
check("dana activates (lineage) before marrying in", res.status_code == 201)
res = client.post("/api/family/marry", json={
    "spouse": {"name": "Diana Mehta", "action": "join", "group_id": spouse_match["group_id"], "matched_node_id": spouse_match["matched_node_id"]},
})
check("dana's marry-join into carl's marital group succeeds", res.status_code == 201)

res = client.get(f"/api/family-groups/{carl_body['marital_group_id']}/tree")
check("dana cannot see carl's marital tree before approval (404)", res.status_code == 404)

login(carl["private_code"])
res = client.get("/api/people/inbox")
join_req = next(r for r in res.get_json()["requests"] if r["kind"] == "family_group_join")
check("carl's inbox shows the family_group_join request", join_req is not None)
res = client.post(f"/api/people/inbox/{join_req['id']}/decide", json={"decision": "accept"})
check("carl accepts dana's join request", res.status_code == 200)

login(dana["private_code"])
res = client.get(f"/api/family-groups/{carl_body['marital_group_id']}/tree")
check("dana can now see the marital tree (200)", res.status_code == 200)
dana_view = res.get_json()
check("dana is flagged as admin of the marital group (spouse-edge derivation)", dana_view["is_admin"] is True)

# Contrast: a CHILD joining a LINEAGE group must stay a plain member, never admin.
logout()
erin = register("Erin Patel")
login(erin["private_code"])
res = client.get("/api/family/suggest", query_string={"name": "Deceased Patel"})
lineage_match = next(r for r in res.get_json()["results"] if r["type"] == "group" and r["group_kind"] == "lineage")
res = client.post("/api/family/activate", json={
    "father": {"name": "Deceased Patel", "action": "join", "group_id": lineage_match["group_id"], "matched_node_id": lineage_match["matched_node_id"]},
    "mother": {"name": "Erin Mother", "action": "create"},
})
check("erin's activation (joining greg's lineage group as a sibling) succeeds", res.status_code == 201)

login(greg["private_code"])
res = client.get("/api/people/inbox")
sib_req = next(r for r in res.get_json()["requests"] if r["kind"] == "family_group_join")
client.post(f"/api/people/inbox/{sib_req['id']}/decide", json={"decision": "accept"})

login(erin["private_code"])
res = client.get(f"/api/family-groups/{greg_body['lineage_group_id']}/tree")
check("erin (a child, no spouse edge) is NOT admin after joining the lineage group", res.get_json()["is_admin"] is False)

print()
print("=" * 70)
print("7. Exact-Public-ID spouse notify links to the REAL self-node, never a duplicate placeholder")
print("=" * 70)
# A real bug caught by live browser testing (2026-10-20): the 'notify' action used to always
# create a brand-new empty placeholder node, even when the caller supplied an EXACT, already-
# verified user_id (via social_core.find_person()) whose own self-node already exists -- leaving
# the spouse edge pointing at a disconnected, same-named duplicate instead of the real person.

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

spouse_link_row = raw(
    "SELECT node_lo_id, node_hi_id FROM family_spouse_links WHERE node_lo_id = ? OR node_hi_id = ? ORDER BY id DESC LIMIT 1",
    (finn_self_node_id, finn_self_node_id),
)
check("the spouse_link points at finn's REAL claimed self-node, not a duplicate",
      spouse_link_row is not None and finn_self_node_id in (spouse_link_row["node_lo_id"], spouse_link_row["node_hi_id"]))
duplicate_count = raw("SELECT COUNT(*) AS n FROM family_nodes WHERE display_name LIKE 'Finn Noble%'")
check("exactly one 'Finn Noble*' node exists in the whole DB (no duplicate placeholder)", duplicate_count["n"] == 1)

print()
print("=" * 70)
if FAILS:
    print(f"{len(FAILS)} check(s) FAILED:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("All checks PASSED.")
