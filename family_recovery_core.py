"""Family Tree-based account recovery (2026-11-13): a verified family member helps a requester
recover their Private ID or reset their PIN, delivered as a system-generated, non-forgeable
message in the requester's existing Qmail inbox (see qmail_core.py, docs/QMAIL.md).

Additive to the two existing recovery paths (recovery_core.py), never a replacement for either:
- request_pin_reset()/verify_pin_reset() -- OTP-based self-service, for a member who still knows
  their Private ID and has a reachable phone/email.
- submit_id_recovery()/decide_request()/reveal_private_code() -- the Admin-ticket path, for a
  forgotten Private ID or no OTP channel, every reveal logged.
This module is for a member who has neither: no working OTP channel, and possibly not even their
own Private ID, but a relative willing to vouch for them.

The requester is never supplied as an id or a session -- by definition they aren't logged in (an
unresolved "forgot everything" scenario is the whole point of this path). The only inputs are the
family member's own Private ID/name and the requester's claimed name and relationship. The
requester's real account is DISCOVERED by walking the family member's own verified Family Tree
graph for a claimed (real-account-linked) node whose name matches what was typed and whose actual
graph relationship matches what was claimed -- never trusted from the claim alone (Part 5.4).

A `tracking_code` (random, shown once, hashed at rest like recovery_core.py's own OTP codes) is
how the requester -- who has no session and may have no Private ID -- comes back later to see the
outcome and, if approved, complete a PIN reset or receive their revealed Private ID. This one piece
is not in the original spec's own field list; it's a necessary addition to make the feature
deliverable end-to-end, flagged explicitly in the handover report.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets

import family_core

REQUEST_EXPIRY_HOURS = 72
PIN_RESET_APPROVAL_TTL_HOURS = 24  # how long a family member's PIN-reset approval stays
# redeemable, once granted -- shorter than the request's own 72h window (Part 8.1), since this is
# the final, most sensitive step. Not a separate token's TTL: see approve_pin_reset()'s own
# docstring for why the tracking_code remains the sole bearer credential throughout.
ACTIONS = ("private_id", "pin_reset", "both")
STATUSES = ("pending", "approved", "rejected", "expired", "completed", "superseded")

# Normalizes whatever the requester typed in the free-text relationship field to one of the six
# relationship shapes _graph_relation() below can actually derive from the Family Tree graph. Not
# a reuse of any existing enum -- family_core.py has no "what is X's relationship to Y" vocabulary
# of its own (its UI is built around tree-building actions -- add father/add child/add spouse --
# not a standalone relationship-type lookup), so this is new, scoped narrowly to what the graph can
# actually verify.
RELATIONSHIP_SYNONYMS = {
    "father": "parent", "mother": "parent", "dad": "parent", "mom": "parent", "parent": "parent",
    "son": "child", "daughter": "child", "child": "child",
    "brother": "sibling", "sister": "sibling", "sibling": "sibling",
    "husband": "spouse", "wife": "spouse", "spouse": "spouse",
    "grandfather": "grandparent", "grandmother": "grandparent", "grandparent": "grandparent",
    "grandson": "grandchild", "granddaughter": "grandchild", "grandchild": "grandchild",
}


def ensure_tables(conn) -> None:
    """Schema is created by migrations/037_family_recovery.py; this mirrors every other *_core.py
    module's own defensive ensure_tables() so a throwaway test DB (or a database a migration
    hasn't reached yet) never crashes on a missing table.

    2026-11-14 security correction (migration not yet deployed, so corrected directly here and in
    the migration file itself, rather than adding a follow-up migration): dropped
    `family_member_private_id` (redundant plaintext sensitive data -- `family_member_user_id`
    already identifies the same account, and nothing ever read this column back; see this
    module's create_request()) and the unused `auth_token_hash`/`auth_token_used_at` columns
    (replaced by `pin_reset_approved_until` -- see approve_pin_reset()/complete_pin_reset() for
    why the tracking_code is this flow's one and only bearer credential, not a second token)."""
    conn.execute("""CREATE TABLE IF NOT EXISTS family_recovery_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, requester_user_id INTEGER NOT NULL,
        requester_claimed_name TEXT NOT NULL, family_member_user_id INTEGER NOT NULL,
        claimed_relationship TEXT NOT NULL,
        verified_relationship TEXT NOT NULL, action TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', qmail_message_id INTEGER,
        tracking_code_hash TEXT NOT NULL, pin_reset_approved_until TEXT,
        created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
        decided_at TEXT, decided_by_user_id INTEGER)""")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_family_recovery_tracking ON family_recovery_requests(tracking_code_hash)")
    conn.commit()


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _new_token() -> tuple[str, str]:
    """(raw, hash) -- the raw value is returned to the caller exactly once and never stored;
    only the hash is persisted, the same pattern recovery_core.py's OTP codes already use."""
    raw = secrets.token_urlsafe(24)
    return raw, _hash(raw)


def _normalize_relationship(raw: str) -> str | None:
    return RELATIONSHIP_SYNONYMS.get((raw or "").strip().lower())


# ---- Graph traversal (read-only; family_core.py's own tables are never written here) ----

def _node_for_user(conn, user_id: int) -> int | None:
    row = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (user_id,)).fetchone()
    return row["id"] if row else None


def _parents_of(conn, node_id: int) -> list[int]:
    return [r["parent_node_id"] for r in conn.execute(
        "SELECT parent_node_id FROM family_parent_links WHERE child_node_id = ?", (node_id,)
    )]


def _children_of(conn, node_id: int) -> list[int]:
    return [r["child_node_id"] for r in conn.execute(
        "SELECT child_node_id FROM family_parent_links WHERE parent_node_id = ?", (node_id,)
    )]


def _spouse_of(conn, node_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT husband_node_id, wife_node_id FROM family_groups WHERE husband_node_id = ? OR wife_node_id = ?",
        (node_id, node_id),
    ).fetchall()
    out = []
    for r in rows:
        other = r["wife_node_id"] if r["husband_node_id"] == node_id else r["husband_node_id"]
        if other:
            out.append(other)
    return out


def _graph_relation(conn, viewer_node_id: int, other_node_id: int) -> str | None:
    """"other_node_id is viewer_node_id's ____" -- one of parent/child/sibling/spouse/grandparent/
    grandchild, or None if no such relation exists in the graph (including "too distant" -- this
    function deliberately does not walk more than two hops). Checked nearest-relation-first; a
    person can only be exactly one of these to another at a time in a well-formed tree, so order
    doesn't change the result, only which query short-circuits first."""
    if other_node_id in _parents_of(conn, viewer_node_id):
        return "parent"
    if other_node_id in _children_of(conn, viewer_node_id):
        return "child"
    if other_node_id in _spouse_of(conn, viewer_node_id):
        return "spouse"
    viewer_parents = _parents_of(conn, viewer_node_id)
    for p in viewer_parents:
        if other_node_id in _children_of(conn, p) and other_node_id != viewer_node_id:
            return "sibling"
        if other_node_id in _parents_of(conn, p):
            return "grandparent"
    for c in _children_of(conn, viewer_node_id):
        if other_node_id in _children_of(conn, c):
            return "grandchild"
    return None


def _related_claimed_nodes(conn, member_node_id: int) -> list[dict]:
    """Every node within two hops of member_node_id that is BOTH graph-related (per _graph_relation)
    AND claimed by a real, non-retired account -- the full candidate pool create_request() searches
    by name. An unclaimed placeholder node is never a candidate: there is no real account to
    recover if the match turns out to be a name on the tree nobody has ever activated.

    `relation` is deliberately computed as _graph_relation(candidate, member) -- "what member_node_id
    is to this candidate" -- not the other way around, so it means the exact same thing as the
    `claimed_relationship` field does in verify_relationship()'s direct-Private-ID mode: "the family
    member's relationship TO the requester" (e.g. claimed_relationship="father" means the family
    member is the requester's father). Both modes must agree on this direction, since a requester
    fills in the same form field regardless of whether they happen to remember their own Private ID."""
    seen = set()
    candidates = []
    pool = set(_parents_of(conn, member_node_id)) | set(_children_of(conn, member_node_id)) | set(_spouse_of(conn, member_node_id))
    for p in _parents_of(conn, member_node_id):
        pool.update(_children_of(conn, p))
        pool.update(_parents_of(conn, p))
    for c in _children_of(conn, member_node_id):
        pool.update(_children_of(conn, c))
    pool.discard(member_node_id)
    for node_id in pool:
        if node_id in seen:
            continue
        seen.add(node_id)
        relation = _graph_relation(conn, node_id, member_node_id)
        if not relation:
            continue
        row = conn.execute(
            "SELECT claimed_user_id FROM family_nodes WHERE id = ? AND claimed_user_id IS NOT NULL", (node_id,)
        ).fetchone()
        if not row:
            continue
        user = conn.execute(
            "SELECT id, name, is_removed FROM users WHERE id = ?", (row["claimed_user_id"],)
        ).fetchone()
        if not user or user["is_removed"]:
            continue
        candidates.append({"node_id": node_id, "user_id": user["id"], "name": user["name"], "relation": relation})
    return candidates


def _names_match(a: str, b: str) -> bool:
    norm = lambda s: " ".join((s or "").strip().lower().split())
    return norm(a) == norm(b)


_GENERIC_VERIFICATION_ERROR = (
    "We could not verify this Family Tree relationship. Please check the details and try again, "
    "or use the standard account recovery process."
)


#  Family Tree cascade rewrite, Rule 5 (2026-11-15, amended same day): the recovery verifier
# accepts a NUCLEAR family member of the requester only -- parent, child, sibling, or spouse --
# regardless of tree adjacency. Spouse was deliberately ADDED to the original three-category rule:
# without it, a requester whose only nuclear relative on Qumanity is their spouse would have no
# family-based recovery path at all and would fall through to the Admin-ticket flow meant for
# someone with NO family on the platform -- a worse outcome than letting the spouse verify, by
# explicit, recorded product decision, not an oversight.
#
# _graph_relation() can genuinely confirm six categories against the real graph: parent, child,
# spouse, sibling, grandparent, grandchild -- all six were accepted by this function before this
# change. Of those, ONLY grandparent and grandchild are newly refused by this rule; spouse stays
# accepted, unchanged (see tests/test_family_recovery.py's own pre-existing "spouse1 discovered"
# coverage, which does not flip). Cousin/aunt/uncle/niece/nephew were never reachable here at all
# -- _graph_relation() has no branch for them -- so nothing changes for those either.
NUCLEAR_RELATIONSHIPS = ("parent", "child", "sibling", "spouse")


def verify_relationship(conn, family_member_private_id: str, family_member_name: str,
                         requester_name: str, claimed_relationship: str,
                         requester_private_id: str | None = None) -> dict:
    """Returns {"family_member_user_id", "requester_user_id", "verified_relationship"} on success.
    Raises ValueError(_GENERIC_VERIFICATION_ERROR) on ANY failure -- wrong Private ID, name
    mismatch, no matching tree node, relationship mismatch, a non-nuclear relationship (even a
    genuinely correct one -- see NUCLEAR_RELATIONSHIPS above), ambiguous match (more than one
    candidate fits) -- deliberately the same message for every case, so a probing attacker learns
    nothing about which specific check failed, whether either Private ID exists at all, or
    whether a real but non-nuclear relationship actually holds (Part 5.4).

    Two modes, both ending at the same graph check:
    - `requester_private_id` given (the common case -- forgot PIN only, still remembers their own
      Private ID): resolves the requester directly, no name search needed at all -- just confirms
      the graph agrees the claimed relationship actually holds between these two specific people.
    - `requester_private_id` omitted (the harder case -- forgot everything): the requester's
      account is DISCOVERED by searching the family member's own tree for a claimed node whose
      name matches what was typed and whose graph relationship matches what was claimed."""
    normalized_claim = _normalize_relationship(claimed_relationship)
    if not normalized_claim or normalized_claim not in NUCLEAR_RELATIONSHIPS:
        raise ValueError(_GENERIC_VERIFICATION_ERROR)

    code = "".join(ch for ch in (family_member_private_id or "") if ch.isdigit())
    member = conn.execute(
        "SELECT id, name, is_removed FROM users WHERE private_id_9digit = ?", (code,)
    ).fetchone()
    if not member or member["is_removed"] or not _names_match(member["name"], family_member_name):
        raise ValueError(_GENERIC_VERIFICATION_ERROR)

    member_node_id = _node_for_user(conn, member["id"])
    if not member_node_id:
        raise ValueError(_GENERIC_VERIFICATION_ERROR)

    if requester_private_id:
        requester_code = "".join(ch for ch in requester_private_id if ch.isdigit())
        requester = conn.execute(
            "SELECT id, name, is_removed FROM users WHERE private_id_9digit = ?", (requester_code,)
        ).fetchone()
        if not requester or requester["is_removed"] or not _names_match(requester["name"], requester_name):
            raise ValueError(_GENERIC_VERIFICATION_ERROR)
        requester_node_id = _node_for_user(conn, requester["id"])
        if not requester_node_id:
            raise ValueError(_GENERIC_VERIFICATION_ERROR)
        if _graph_relation(conn, requester_node_id, member_node_id) != normalized_claim:
            raise ValueError(_GENERIC_VERIFICATION_ERROR)
        return {
            "family_member_user_id": member["id"], "requester_user_id": requester["id"],
            "verified_relationship": normalized_claim,
        }

    matches = [
        c for c in _related_claimed_nodes(conn, member_node_id)
        if _names_match(c["name"], requester_name) and c["relation"] == normalized_claim
    ]
    if len(matches) != 1:
        # Zero matches (no such relative, or the relationship doesn't match) and more-than-one
        # (an ambiguous name collision within the tree) are both refused identically -- neither is
        # safe to resolve by guessing.
        raise ValueError(_GENERIC_VERIFICATION_ERROR)

    return {
        "family_member_user_id": member["id"],
        "requester_user_id": matches[0]["user_id"],
        "verified_relationship": normalized_claim,
    }


# ---- Request lifecycle ----

def eligible_family_tree(conn, user_id: int) -> bool:
    """Whether `user_id` has ANY verifiable family connection at all; never itself a trust
    decision -- a member with no claimed node, or a node with no related claimed relatives, falls
    back to the existing Admin ticket path. 2026-11-14: deliberately NOT called from
    available_methods_for_private_id() (or any other public, unauthenticated route) any more --
    its result is per-account information, and surfacing it to an unauthenticated caller keyed on
    an arbitrary Private ID is exactly the enumeration oracle that function was corrected to close.
    Kept as an internal helper for a genuinely authenticated context (e.g. the account's own
    settings) should one need this check later; not currently called by any route."""
    node_id = _node_for_user(conn, user_id)
    if not node_id:
        return False
    return len(_related_claimed_nodes(conn, node_id)) > 0


def available_methods_for_private_id(conn, private_id: str) -> dict:
    """The Part 5.1 "which recovery screen to show" check -- 2026-11-14 security correction: this
    used to look up the real account and return `otp_reset`/`family_recovery` computed from ITS
    actual phone/email/Family-Tree state. That is a genuine enumeration oracle even though the key
    NAMES never changed: two different REAL Private IDs could (and would, in the common case)
    produce two DIFFERENT boolean VALUES, so an attacker sweeping Private IDs could tell "this one
    exists and has an eligible channel" apart from "this one is unknown" -- the fact that an
    unknown id and a known-but-ineligible id looked alike was not enough; any id with ANY eligible
    channel stood out from the rest. Returning a FIXED response for every syntactically well-formed
    input removes that signal entirely: this function no longer queries the database or takes
    `private_id` into account at all (the parameter is kept for API/signature stability only). The
    actual eligibility check happens downstream, inside the real action -- recovery_core.
    request_pin_reset() and family_recovery_core.create_request()/verify_relationship() -- which
    already fail with ONE generic, uniform message for every kind of ineligibility (unknown id,
    no channel, no matching relative), exactly the same precedent this function now defers to
    entirely instead of duplicating. The requester's own UI always offers every path; trying one
    that doesn't apply just produces that same generic failure, same as today."""
    return {"otp_reset": True, "family_recovery": True, "admin_ticket": True}


def create_request(conn, family_member_private_id: str, family_member_name: str,
                    requester_name: str, claimed_relationship: str, action: str,
                    requester_private_id: str | None = None) -> dict:
    """Verifies the relationship (raising ValueError with the one generic message on any failure),
    then creates the request row, supersedes any still-pending request from the SAME discovered
    requester, and delivers a system Qmail message to the family member. Returns
    {"tracking_code", "expires_at"} -- the tracking_code is shown to the caller exactly once."""
    ensure_tables(conn)
    if action not in ACTIONS:
        raise ValueError("Unknown recovery action")
    verified = verify_relationship(conn, family_member_private_id, family_member_name, requester_name,
                                    claimed_relationship, requester_private_id)

    # One pending request per requester (Part 8.2): any prior unactioned request from this same
    # discovered account is superseded, not stacked -- preserved as historical audit, not deleted.
    conn.execute(
        "UPDATE family_recovery_requests SET status = 'superseded' WHERE requester_user_id = ? AND status = 'pending'",
        (verified["requester_user_id"],),
    )

    raw_token, token_hash = _new_token()
    now = _now()
    expires = (now + dt.timedelta(hours=REQUEST_EXPIRY_HOURS)).isoformat()
    # family_member_private_id is NOT persisted (2026-11-14 security correction): it was redundant
    # plaintext sensitive data -- family_member_user_id (resolved by verify_relationship() above)
    # already identifies the exact same account for every actual use (inbox_detail, share/approve/
    # reject, the Qmail message itself), and nothing ever read this column back. Only ever needed
    # transiently, to perform the lookup in verify_relationship().
    cur = conn.execute(
        """INSERT INTO family_recovery_requests
           (requester_user_id, requester_claimed_name, family_member_user_id,
            claimed_relationship, verified_relationship, action, status, tracking_code_hash,
            created_at, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
        (verified["requester_user_id"], requester_name.strip(), verified["family_member_user_id"],
         claimed_relationship.strip(), verified["verified_relationship"], action, token_hash,
         now.isoformat(), expires),
    )
    request_id = cur.lastrowid

    message_id = _send_recovery_message(conn, request_id, verified, requester_name.strip(), action, expires)
    conn.execute("UPDATE family_recovery_requests SET qmail_message_id = ? WHERE id = ?", (message_id, request_id))
    conn.commit()
    return {"tracking_code": raw_token, "expires_at": expires}


_ACTION_LABELS = {"private_id": "Private ID recovery", "pin_reset": "PIN reset", "both": "Private ID recovery and PIN reset"}


def _send_recovery_message(conn, request_id: int, verified: dict, requester_name: str, action: str, expires_at: str) -> int:
    """Inserts the system-generated Qmail message directly into qmail_messages -- never through
    qmail_core's normal compose path (no ordinary member can address a message to themselves as
    "the system," and this one is tagged message_type='family_recovery_request' precisely so the
    inbox can refuse to let it be treated like one). Uses qmail_core's own auto-activation so the
    family member is guaranteed to have an address to deliver to, the same guarantee every other
    real member now has from registration/login onward.

    from_user_id is set to the family member's OWN user id, same as to_user_id -- not a "the
    family member sent themselves a message" bug, but the only value this column (NOT NULL,
    unchanged from migrations/021_qmail.py, INNER JOINed to `users` by both /api/qmail/inbox and
    /api/qmail/sent) can legally hold without altering the existing, deployed qmail_messages
    schema. 2026-11-14 security correction: app.py's /api/qmail/inbox now overrides the displayed
    sender for any message_type != 'member' instead of showing the recipient their own name back,
    and /api/qmail/sent now excludes message_type != 'member' rows entirely, so this never
    surfaces as a self-sent message in either folder. See app.py's own comments at those two
    routes for the exact fix."""
    import qmail_core
    qmail_core.auto_activate(conn, verified["family_member_user_id"])
    subject = f"Family Recovery Request — {requester_name}"
    body = (
        f"{requester_name} has requested assistance recovering access to their Qumanity account. "
        f"Our system has verified your existing Family Tree relationship "
        f"({verified['verified_relationship']}).\n\n"
        f"Requested action: {_ACTION_LABELS.get(action, action)}.\n"
        f"This request expires at {expires_at} (UTC).\n\n"
        "Please review the request and choose whether you wish to assist."
    )
    cur = conn.execute(
        """INSERT INTO qmail_messages (from_user_id, to_user_id, subject, body, created_at, message_type, recovery_request_id)
           VALUES (?, ?, ?, ?, ?, 'family_recovery_request', ?)""",
        (verified["family_member_user_id"], verified["family_member_user_id"], subject, body, _now_iso(), request_id),
    )
    return cur.lastrowid


def _get_active(conn, request_id: int) -> dict | None:
    """The request row, only if it's still pending, not past its own 72-hour expiry, AND the
    requester's account is still real (not retired/removed since the request was created) --
    every action (share/approve/reject) goes through this single gate, not a separate check per
    action, so there is exactly one place "is this request still actionable" is decided. A
    retired requester is treated exactly like an expired request: nothing left to act on
    (2026-11-14 security correction -- helping a now-retired account recover access serves no
    purpose and the data this would reveal/change is still sensitive either way)."""
    row = conn.execute("SELECT * FROM family_recovery_requests WHERE id = ?", (request_id,)).fetchone()
    if not row:
        return None
    if row["status"] == "pending" and row["expires_at"] < _now_iso():
        conn.execute("UPDATE family_recovery_requests SET status = 'expired' WHERE id = ?", (request_id,))
        conn.commit()
        return None
    if row["status"] != "pending":
        return None
    requester = conn.execute("SELECT is_removed FROM users WHERE id = ?", (row["requester_user_id"],)).fetchone()
    if not requester or requester["is_removed"]:
        return None
    return dict(row)


def inbox_detail(conn, viewer_user_id: int, request_id: int) -> dict | None:
    """The request detail for the Qmail inbox's own reading pane -- None if this viewer isn't the
    intended family member (same 404-not-403 shape as every other access check in this codebase;
    see qmail_core.py's own docstrings for the precedent) or the request is no longer pending."""
    row = conn.execute("SELECT * FROM family_recovery_requests WHERE id = ?", (request_id,)).fetchone()
    if not row or row["family_member_user_id"] != viewer_user_id:
        return None
    active = row["status"] == "pending" and row["expires_at"] >= _now_iso()
    return {
        "id": row["id"], "requester_claimed_name": row["requester_claimed_name"],
        "verified_relationship": row["verified_relationship"], "action": row["action"],
        "status": row["status"] if active else ("expired" if row["status"] == "pending" else row["status"]),
        "created_at": row["created_at"], "expires_at": row["expires_at"],
        "can_act": active,
    }


def share_private_id(conn, request_id: int, acting_user_id: int) -> str:
    """Returns the requester's real Private ID -- only after confirming the acting user IS the
    intended family member and the request is still pending and unexpired. Marks the request
    completed; this is a one-time action, never repeatable (Part 7.1). The status-flip UPDATE is
    itself the concurrency guard (`WHERE status = 'pending'`, checked via rowcount): if the family
    member double-clicks, or two requests race, only the first commits the transition -- the
    second sees rowcount 0 and fails the same way a stale/already-decided request would, never
    re-reading or re-sharing anything (2026-11-14 security correction)."""
    row = _get_active(conn, request_id)
    if not row or row["family_member_user_id"] != acting_user_id:
        raise ValueError("Request not found")
    if row["action"] not in ("private_id", "both"):
        raise ValueError("This request did not ask for Private ID recovery")
    cur = conn.execute(
        "UPDATE family_recovery_requests SET status = 'completed', decided_at = ?, decided_by_user_id = ? "
        "WHERE id = ? AND status = 'pending'",
        (_now_iso(), acting_user_id, request_id),
    )
    if cur.rowcount != 1:
        conn.rollback()
        raise ValueError("Request not found")
    requester = conn.execute("SELECT private_id_9digit FROM users WHERE id = ?", (row["requester_user_id"],)).fetchone()
    conn.commit()
    print(f"[family_recovery] PRIVATE_ID_SHARED request_id={request_id} by_user_id={acting_user_id}")
    return requester["private_id_9digit"]


def approve_pin_reset(conn, request_id: int, acting_user_id: int) -> None:
    """Approves the request: the family member's consent, nothing more -- the PIN itself is never
    generated, shown, or decided here. No separate authorization token is minted (2026-11-14
    security correction; see complete_pin_reset()'s own docstring for the full reasoning): the
    requester already holds the one secret this whole flow runs on -- their tracking_code, handed
    to them once by create_request() -- and the family member has no channel to deliver a second,
    fresh secret through even if one were minted. Approving only stamps
    `pin_reset_approved_until` (now + PIN_RESET_APPROVAL_TTL_HOURS); complete_pin_reset() checks
    that window directly. Race-safe the same way share_private_id() is -- the status-flip UPDATE's
    own rowcount is the guard against a double-approval race."""
    row = _get_active(conn, request_id)
    if not row or row["family_member_user_id"] != acting_user_id:
        raise ValueError("Request not found")
    if row["action"] not in ("pin_reset", "both"):
        raise ValueError("This request did not ask for a PIN reset")
    approved_until = (_now() + dt.timedelta(hours=PIN_RESET_APPROVAL_TTL_HOURS)).isoformat()
    cur = conn.execute(
        "UPDATE family_recovery_requests SET status = 'approved', decided_at = ?, decided_by_user_id = ?, "
        "pin_reset_approved_until = ? WHERE id = ? AND status = 'pending'",
        (_now_iso(), acting_user_id, approved_until, request_id),
    )
    if cur.rowcount != 1:
        conn.rollback()
        raise ValueError("Request not found")
    conn.commit()
    print(f"[family_recovery] PIN_RESET_APPROVED request_id={request_id} by_user_id={acting_user_id}")


def reject(conn, request_id: int, acting_user_id: int) -> None:
    row = _get_active(conn, request_id)
    if not row or row["family_member_user_id"] != acting_user_id:
        raise ValueError("Request not found")
    cur = conn.execute(
        "UPDATE family_recovery_requests SET status = 'rejected', decided_at = ?, decided_by_user_id = ? "
        "WHERE id = ? AND status = 'pending'",
        (_now_iso(), acting_user_id, request_id),
    )
    if cur.rowcount != 1:
        conn.rollback()
        raise ValueError("Request not found")
    conn.commit()


# ---- The requester's own side: tracking code status + completing an approved PIN reset ----

def status_by_tracking_code(conn, raw_code: str) -> dict:
    """Public, unauthenticated lookup -- the requester's only way back in. Returns a status shape
    that never includes the family member's identity or the Private ID itself (that's
    reveal_private_id_by_tracking_code()'s job, a separate, explicit step) -- just enough for the
    requester's own UI to know what to do next. tracking_code_hash is UNIQUE, so this can never
    return another request's status -- a tracking credential only ever resolves the one request
    it was issued for."""
    row = conn.execute(
        "SELECT * FROM family_recovery_requests WHERE tracking_code_hash = ?", (_hash((raw_code or "").strip()),)
    ).fetchone()
    if not row:
        raise ValueError("No recovery request found for that tracking code")
    status = row["status"]
    if status == "pending" and row["expires_at"] < _now_iso():
        conn.execute("UPDATE family_recovery_requests SET status = 'expired' WHERE id = ?", (row["id"],))
        conn.commit()
        status = "expired"
    # A granted PIN-reset approval has its OWN, shorter expiry (pin_reset_approved_until) on top
    # of the request's own 72h one -- checked here too so a requester who waits past the 24h
    # window sees 'expired' on their very next poll, not a stale 'approved' that complete_pin_
    # reset() would then refuse anyway.
    if status == "approved" and row["pin_reset_approved_until"] and row["pin_reset_approved_until"] < _now_iso():
        conn.execute("UPDATE family_recovery_requests SET status = 'expired' WHERE id = ?", (row["id"],))
        conn.commit()
        status = "expired"
    out = {"status": status, "action": row["action"], "expires_at": row["expires_at"]}
    if status == "completed" and row["action"] in ("private_id", "both"):
        out["private_id_available"] = True
    if status == "approved" and row["action"] in ("pin_reset", "both"):
        out["pin_reset_ready"] = True
    return out


def reveal_private_id_by_tracking_code(conn, raw_code: str) -> str:
    """The requester's own retrieval step, separate from status_by_tracking_code() so a mere status
    poll never carries the Private ID -- only an explicit call to this function can. Only works
    once (the request's status is 'completed' exactly once, set by share_private_id() above, and
    this function itself doesn't change state further -- repeat calls return the same value for as
    long as the request row exists, matching the fact that this IS the requester's own recovered
    credential, not a one-time reveal like the Admin path's reveal_private_code())."""
    row = conn.execute(
        "SELECT requester_user_id, status, action FROM family_recovery_requests WHERE tracking_code_hash = ?",
        (_hash((raw_code or "").strip()),),
    ).fetchone()
    if not row or row["status"] != "completed" or row["action"] not in ("private_id", "both"):
        raise ValueError("No completed Private ID recovery found for that tracking code")
    user = conn.execute(
        "SELECT private_id_9digit, is_removed FROM users WHERE id = ?", (row["requester_user_id"],)
    ).fetchone()
    if not user or user["is_removed"]:
        raise ValueError("No completed Private ID recovery found for that tracking code")
    return user["private_id_9digit"]


def complete_pin_reset(conn, raw_code: str, new_pin: str) -> None:
    """Redeems the PIN-reset approval approve_pin_reset() granted, sets the new PIN hash (the
    exact UPDATE .../api/user/pin already uses -- which, per that route's own existing design,
    changes this account's bearer-token fingerprint and so already invalidates every previously
    issued Phone App token with no extra code needed here; see app.py's _pin_fingerprint()).

    2026-11-14 security correction -- the authorization mechanism, made explicit: the
    tracking_code is this entire flow's ONE bearer credential, start to finish (status checks,
    Private ID reveal, and this completion). There is no second token: approve_pin_reset() does
    not mint or hand the requester anything new -- it can't, since the family member has no
    channel to deliver a fresh secret through, and the requester already holds the one secret
    that matters. "Approved" is pure server-side state (status='approved' plus
    pin_reset_approved_until), and the tracking_code the requester already has is what lets them
    act on that state.

    Single-use and race-safe: the status-flip UPDATE below only succeeds if it can move the row
    itself FROM 'approved' TO 'completed' in one atomic statement (`WHERE status = 'approved'`).
    If two redemption attempts race (Part 7.2 replay prevention, and the "no race condition
    allowing two PIN-reset completions" requirement), at most one UPDATE affects a row; the
    loser's rowcount is 0 and it fails the same generic way a replay attempt does -- never a
    separate used-once flag to keep in sync with the status column."""
    import re
    from werkzeug.security import generate_password_hash
    if not re.fullmatch(r"""^(?=.*[A-Za-z0-9])[A-Za-z0-9!@#$%^&*()_+\-=\[\]{}|;:'",.<>/?]{5}$""", new_pin or ""):
        raise ValueError("PIN must be 5 characters. It can include numbers, letters, or special characters — but not all special characters.")
    row = conn.execute(
        "SELECT * FROM family_recovery_requests WHERE tracking_code_hash = ?", (_hash((raw_code or "").strip()),)
    ).fetchone()
    if not row or row["status"] != "approved" or row["action"] not in ("pin_reset", "both"):
        raise ValueError("No approved PIN reset found for that tracking code")
    if not row["pin_reset_approved_until"] or row["pin_reset_approved_until"] < _now_iso():
        conn.execute(
            "UPDATE family_recovery_requests SET status = 'expired' WHERE id = ? AND status = 'approved'",
            (row["id"],),
        )
        conn.commit()
        raise ValueError("This authorization has expired")
    requester = conn.execute("SELECT is_removed FROM users WHERE id = ?", (row["requester_user_id"],)).fetchone()
    if not requester or requester["is_removed"]:
        raise ValueError("No approved PIN reset found for that tracking code")
    cur = conn.execute(
        "UPDATE family_recovery_requests SET status = 'completed' WHERE id = ? AND status = 'approved'",
        (row["id"],),
    )
    if cur.rowcount != 1:
        conn.rollback()
        raise ValueError("No approved PIN reset found for that tracking code")
    conn.execute(
        "UPDATE users SET pin_hash = ?, pin_fails = 0, pin_locked_until = NULL WHERE id = ?",
        (generate_password_hash(new_pin), row["requester_user_id"]),
    )
    conn.commit()
    print(f"[family_recovery] PIN_RESET_COMPLETED request_id={row['id']}")
