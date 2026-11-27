"""Q-Cards (2026-11-15): the server-side resolution of a physical card's QR token to a real
account, the issuance primitive, and (Stage 3) the Admin-facing management actions and the
free-eligibility derivation. See migrations/039_q_cards.py for the full schema rationale and
docs/qcard_phase1_2026_11_15.md for the design this implements.

Stage 3 adds: the six admin actions (mark_paid, mark_free, mark_delivered, revoke, replace,
list_pending), each enforcing the four status values and legal transitions in Python -- there is
no SQL CHECK constraint on `status` (see migrations/039_q_cards.py's own docstring), so this is
the ONLY enforcement point, and every writer below goes through it. Also adds free_eligibility(),
which derives WHY a user may get a free card (never an admin-supplied string) from three existing
sources: _is_admin_user() (this module's own Flask-independent mirror of app.py's _is_admin(), see
its own docstring for why it isn't a shared import), family_core.recursive_member_node_ids() (the
Family Tree cascade -- reused, not reimplemented, see that function's own docstring), and
announcements_core.is_council_member() against election_core.PILOT_VILLAGE_ID (the one existing
village-council-membership check, already used by the Announcements feature). The batch
PDF/QR-rendering flow remains Stage 4's.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import os
import secrets
from pathlib import Path

import qrcode
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas

import announcements_core
import election_core
import family_core

ACTIONABLE_STATUS = "active"
_STATUSES = {"pending_payment", "active", "revoked", "replaced"}
_PAYMENT_METHODS = {"cash", "upi_static"}

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "static" / "images" / "qumanity-logo-dpga.png"
CARD_LOGIN_URL = "https://qumanity.in/card/"

# Standard CR80 card size (credit-card / ID-card format, landscape) -- 2026-11-28 redesign from
# the original A4-page Platypus layout, which rendered as a plain letter-sized document with a
# giant QR code rather than anything resembling a physical card.
_CARD_W = 3.370 * inch
_CARD_H = 2.125 * inch
_GOLD = HexColor("#B8860B")
_NAVY = HexColor("#0A1929")
_CREAM = HexColor("#FAF7F1")
_TEXT = HexColor("#1D2733")
_TEXT_DIM = HexColor("#5B6B7A")
_PHOTO_BG = HexColor("#E0DCCF")
_SILHOUETTE = HexColor("#A8A398")
_SILHOUETTE_HAIR = HexColor("#8A8578")


def ensure_tables(conn) -> None:
    """Defensive mirror of migrations/039_q_cards.py, same convention every other *_core.py
    module in this codebase already follows -- a throwaway test DB (or a database a migration
    hasn't reached yet) self-heals instead of crashing on a missing table."""
    conn.execute("""CREATE TABLE IF NOT EXISTS q_cards (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, token_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending_payment', issued_at TEXT NOT NULL, revoked_at TEXT,
        replaced_by_card_id INTEGER, payment_status TEXT NOT NULL DEFAULT 'unpaid',
        payment_method TEXT, payment_reference TEXT, free_reason TEXT, delivered_at TEXT,
        card_display_id TEXT)""")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_q_cards_token_hash ON q_cards(token_hash)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_q_cards_display_id ON q_cards(card_display_id)")
    conn.commit()


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _new_token() -> tuple[str, str]:
    """(raw, hash) -- same shape as family_recovery_core.py's own _new_token(): the raw value is
    returned to the caller exactly once (here: to be encoded into the printed QR and shown to the
    Admin at issuance) and never stored; only the hash is persisted."""
    raw = secrets.token_urlsafe(24)
    return raw, _hash(raw)


def issue_card(conn, user_id: int, free_reason: str | None = None) -> dict:
    """Creates one q_cards row for user_id. free_reason ('admin'|'family'|'council'), when given,
    means the FREE-ELIGIBILITY DECISION has already been made by the caller (Stage 3's own
    derivation from existing tables -- this function never makes that decision itself, it only
    records the outcome) -- the card starts 'active'/'free' immediately, no payment gate. Without
    free_reason, the card starts 'pending_payment'/'unpaid' -- Phase 1's explicit decision that an
    unpaid, non-free card does not activate until an Admin marks it paid (Stage 3).

    Returns {"card_display_id", "raw_token"} -- raw_token is shown/encoded exactly once, here;
    only its hash is ever stored (see module docstring)."""
    raw_token, token_hash = _new_token()
    now = _now_iso()
    is_free = free_reason is not None
    cur = conn.execute(
        """INSERT INTO q_cards (user_id, token_hash, status, issued_at, payment_status, payment_method, free_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, token_hash, "active" if is_free else "pending_payment", now,
         "free" if is_free else "unpaid", "free" if is_free else None, free_reason),
    )
    card_display_id = f"QC-{cur.lastrowid:06d}"
    conn.execute("UPDATE q_cards SET card_display_id = ? WHERE id = ?", (card_display_id, cur.lastrowid))
    conn.commit()
    return {"card_display_id": card_display_id, "raw_token": raw_token}


def resolve_token(conn, raw_token: str) -> dict | None:
    """The enumeration-safe scan: None for EVERY non-actionable case alike -- unknown token,
    malformed/empty input, and a card that exists but isn't 'active' (pending_payment, revoked,
    or replaced) -- never distinguishing which. A 'replaced' token is refused outright, never
    forwarded to replaced_by_card_id (Phase 2's explicit decision: forwarding a found lost card's
    token to its own replacement would let whoever found it keep logging in until the
    replacement itself gets reported lost too -- refusing outright is the safer default).

    Returns {"card_id", "user_id", "name"} only for a genuinely active card. Callers needing the
    scanning person's own first name (the card-resolve route's own "confirm this is your card"
    display) derive it from `name` themselves -- this function doesn't assume what a caller wants
    to show."""
    if not raw_token:
        return None
    row = conn.execute(
        """SELECT q.id AS card_id, q.user_id, u.name FROM q_cards q
           JOIN users u ON u.id = q.user_id
           WHERE q.token_hash = ? AND q.status = ? AND u.is_removed = 0""",
        (_hash(raw_token), ACTIONABLE_STATUS),
    ).fetchone()
    if not row:
        return None
    return {"card_id": row["card_id"], "user_id": row["user_id"], "name": row["name"]}


# ---- Stage 3: free-eligibility derivation ----

# Deliberately duplicates app.py's _is_admin() by design -- see that function's own definition
# in app.py for the source of truth this mirrors. Not a stale copy: if app.py's _is_admin() ever
# changes its env var or column, this one must change to match.
def _is_admin_user(conn, user_id) -> bool:
    """Flask-independent mirror of app.py's own _is_admin() -- SAME env var
    (QM_ADMIN_PRIVATE_IDS), SAME users.private_id_9digit comparison -- but parameterized by a
    user_id rather than reading session["user_id"], since free_eligibility() below must be able to
    ask "is this card's owner the Admin" for ANY user_id, not only the currently logged-in one.

    A duplicate of app.py's own five lines, not a shared import, because app.py's version is
    irreducibly Flask-session-coupled (it has no user_id parameter at all) and q_card_core.py, like
    every other *_core.py module in this codebase, imports no Flask machinery. This is the Admin
    *identity* check (one person, one env var) -- not a second family-membership rule, which is
    the thing Phase 2 was told not to reinvent; that one is recursive_member_node_ids() below."""
    allowed = {pid.strip() for pid in os.environ.get("QM_ADMIN_PRIVATE_IDS", "").split(",") if pid.strip()}
    if not allowed:
        return False
    row = conn.execute("SELECT private_id_9digit FROM users WHERE id = ?", (user_id,)).fetchone()
    return bool(row and row["private_id_9digit"] in allowed)


def _admin_root_group_ids(conn) -> set[int]:
    """The family_groups.id of every unit where an Admin account is a FOUNDER (husband_node_id or
    wife_node_id) -- the root(s) family-eligibility cascades down from. Reading: 'root' means the
    group the Admin themself FOUNDED (married into), matching the worked example (Pardeep+Neelam,
    where Pardeep is husband_node_id) -- not any group where the Admin is merely a plain child
    node under their OWN parents. If the Admin's own node is also a child in some ascendant group
    (a living grandparent unit), this does not ascend to it; eligibility cascades only DOWNWARD
    from the Admin's own founder group(s), per Rule 1's own wording ("a son's household cascades
    into his FATHER's unit" -- the Admin is being treated as the father, the top, here)."""
    allowed = {pid.strip() for pid in os.environ.get("QM_ADMIN_PRIVATE_IDS", "").split(",") if pid.strip()}
    if not allowed:
        return set()
    admin_user_ids = [r["id"] for r in conn.execute(
        f"SELECT id FROM users WHERE private_id_9digit IN ({','.join('?' * len(allowed))})", tuple(allowed),
    ).fetchall()]
    group_ids = set()
    for admin_user_id in admin_user_ids:
        node_row = conn.execute("SELECT id FROM family_nodes WHERE claimed_user_id = ?", (admin_user_id,)).fetchone()
        if not node_row:
            continue
        for g in conn.execute(
            "SELECT id FROM family_groups WHERE husband_node_id = ? OR wife_node_id = ?",
            (node_row["id"], node_row["id"]),
        ).fetchall():
            group_ids.add(g["id"])
    return group_ids


def family_eligible_user_ids(conn) -> set[int]:
    """Every user_id inside the Admin's cascade, per family_core.recursive_member_node_ids() --
    reusing the Family Tree cascade rules (the Cascade, the Daughter Rule, the Death Rule) exactly
    as they are, never a second, independent membership rule written here. Resolves each node_id
    the cascade returns to a user_id via family_nodes.claimed_user_id (an unclaimed placeholder
    node contributes nothing -- only a real account can be free-eligible)."""
    node_ids = set()
    for group_id in _admin_root_group_ids(conn):
        node_ids |= family_core.recursive_member_node_ids(conn, group_id)
    if not node_ids:
        return set()
    rows = conn.execute(
        f"SELECT claimed_user_id FROM family_nodes WHERE id IN ({','.join('?' * len(node_ids))}) AND claimed_user_id IS NOT NULL",
        tuple(node_ids),
    ).fetchall()
    return {r["claimed_user_id"] for r in rows}


def _council_eligible(conn, user_id) -> bool:
    """Reuses announcements_core.is_council_member() -- the one existing village-council-
    membership check in this codebase (already powering the Announcements feature) -- scoped to
    election_core.PILOT_VILLAGE_ID, the one village this whole platform currently pilots on."""
    return announcements_core.is_council_member(conn, user_id, election_core.PILOT_VILLAGE_ID, "village")


def free_eligibility(conn, user_id) -> str | None:
    """The single source of truth for WHY (if at all) user_id may get a free Q-Card -- 'admin',
    'family', or 'council' -- or None. mark_free() below MUST derive free_reason from this
    function's own return value, never from an admin-supplied string, so this is the only place
    the three category strings are decided."""
    if _is_admin_user(conn, user_id):
        return "admin"
    if user_id in family_eligible_user_ids(conn):
        return "family"
    if _council_eligible(conn, user_id):
        return "council"
    return None


# ---- Stage 3: admin actions. Every writer enforces the four status values and legal
# transitions in Python -- the only enforcement that exists, since migrations/039_q_cards.py
# deliberately has no SQL CHECK constraint (matching this codebase's existing convention). ----

def _get_card(conn, card_id) -> dict:
    row = conn.execute("SELECT * FROM q_cards WHERE id = ?", (card_id,)).fetchone()
    if not row:
        raise ValueError("Card not found")
    return row


def _set_status(conn, card_id: int, new_status: str, **extra_cols) -> None:
    """The one place every writer below funnels its status change through -- since there is no
    SQL CHECK constraint on q_cards.status (migrations/039_q_cards.py), this is the only
    enforcement of the four legal values that exists anywhere. Any caller (present or future)
    passing a fifth value is refused here, not at the database."""
    if new_status not in _STATUSES:
        raise ValueError(f"Illegal status '{new_status}' -- must be one of {sorted(_STATUSES)}")
    cols = ", ".join(f"{k} = ?" for k in extra_cols)
    sql = f"UPDATE q_cards SET status = ?{', ' + cols if cols else ''} WHERE id = ?"
    conn.execute(sql, (new_status, *extra_cols.values(), card_id))


def mark_paid(conn, card_id: int, method: str, reference: str | None = None) -> None:
    """unpaid -> paid, pending_payment -> active. Refuses any card not currently
    'pending_payment' -- including an already-active or already-free card (there is no
    paid-on-top-of-paid), and both terminal states (revoked/replaced, per 'no transition out of
    revoked or replaced')."""
    if method not in _PAYMENT_METHODS:
        raise ValueError(f"Unknown payment method '{method}' -- must be one of {sorted(_PAYMENT_METHODS)}")
    card = _get_card(conn, card_id)
    if card["status"] != "pending_payment":
        raise ValueError(f"Cannot mark paid: card is '{card['status']}', not 'pending_payment'")
    _set_status(conn, card_id, "active", payment_status="paid", payment_method=method, payment_reference=reference)
    conn.commit()


def mark_free(conn, card_id: int) -> str:
    """unpaid -> free, pending_payment -> active. free_reason is ALWAYS derived from
    free_eligibility(), never accepted as a parameter -- an admin cannot mark a non-eligible
    user's card free; this function refuses the call outright and says why. No override path
    exists; if one is ever needed, it must be proposed explicitly (a reason string like
    'override:manual' plus an audit log entry), not built silently here. Returns the free_reason
    that was recorded."""
    card = _get_card(conn, card_id)
    if card["status"] != "pending_payment":
        raise ValueError(f"Cannot mark free: card is '{card['status']}', not 'pending_payment'")
    reason = free_eligibility(conn, card["user_id"])
    if reason is None:
        raise ValueError("This card's owner is not eligible for a free card (not Admin, not in the Admin's family cascade, not on the pilot village council)")
    _set_status(conn, card_id, "active", payment_status="free", payment_method="free", free_reason=reason)
    conn.commit()
    return reason


def mark_delivered(conn, card_id: int) -> None:
    """Writes delivered_at. Idempotent -- a card already marked delivered is a pure no-op, never a
    second write (same convention as revoke() below, and as qmail_core.auto_activate()'s own
    repeat-call no-op)."""
    card = _get_card(conn, card_id)
    if card["delivered_at"]:
        return
    conn.execute("UPDATE q_cards SET delivered_at = ? WHERE id = ?", (_now_iso(), card_id))
    conn.commit()


def revoke(conn, card_id: int) -> None:
    """pending_payment|active -> revoked, writes revoked_at. Revoking an already-revoked card is a
    no-op (idempotent, no second write to revoked_at) -- not an error, so a caller doesn't need to
    check status first. Revoking a 'replaced' card directly is refused: that card's own replacement
    already carries the current revoked_at/replaced_by_card_id story; act on the replacement
    instead (same 'no transition out of replaced' rule as every other writer)."""
    card = _get_card(conn, card_id)
    if card["status"] == "revoked":
        return
    if card["status"] == "replaced":
        raise ValueError("Cannot revoke a replaced card directly -- act on its replacement (replaced_by_card_id) instead")
    _set_status(conn, card_id, "revoked", revoked_at=_now_iso())
    conn.commit()


def replace(conn, card_id: int) -> dict:
    """The old row: status -> replaced, writes revoked_at, sets replaced_by_card_id. A new row is
    issued with a fresh token, status 'pending_payment' -- even if the old card was free, the
    replacement is NOT automatically re-granted free; mark_free() must be called again on it,
    so a fresh eligibility check always runs rather than silently trusting a prior grant that may
    no longer hold. Refuses a card that is already 'revoked' or 'replaced' (no transition out of
    either terminal state). Returns issue_card()'s own {"card_display_id", "raw_token"} dict for
    the new card."""
    card = _get_card(conn, card_id)
    if card["status"] in ("revoked", "replaced"):
        raise ValueError(f"Cannot replace a '{card['status']}' card")
    new = issue_card(conn, card["user_id"])
    new_id = conn.execute("SELECT id FROM q_cards WHERE card_display_id = ?", (new["card_display_id"],)).fetchone()["id"]
    _set_status(conn, card_id, "replaced", revoked_at=_now_iso(), replaced_by_card_id=new_id)
    conn.commit()
    return new


def list_pending(conn) -> list[dict]:
    """Read-only listing of every card still awaiting a payment/free decision."""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM q_cards WHERE status = 'pending_payment' ORDER BY issued_at"
    ).fetchall()]


# ---- Stage 4 (2026-11-19): the single-card PDF/QR renderer this module's own docstring long said
# was still outstanding ("The batch PDF/QR-rendering flow remains Stage 4's") -- built now as a
# per-card primitive, specifically so the batch exporter proposed in
# docs/qcard_phase1_2026_11_15.md §4 can loop THIS SAME layout across many pages later, rather than
# needing a second implementation. ----

def _draw_photo_cover(c, photo_bytes: bytes, x: float, y: float, size: float) -> None:
    """Draws photo_bytes scaled to COVER the x/y/size square (crops overflow, never
    letterboxes/stretches) -- reportlab's own preserveAspectRatio="contain"-only sizing left
    visible empty strips down both sides of any non-square (e.g. portrait 3:4) uploaded photo,
    which looked broken rather than like a cropped ID photo."""
    img = ImageReader(io.BytesIO(photo_bytes))
    iw, ih = img.getSize()
    scale = max(size / iw, size / ih)
    draw_w, draw_h = iw * scale, ih * scale
    offset_x = x + (size - draw_w) / 2
    offset_y = y + (size - draw_h) / 2
    c.saveState()
    clip = c.beginPath()
    clip.roundRect(x, y, size, size, 4)
    c.clipPath(clip, stroke=0, fill=0)
    c.drawImage(img, offset_x, offset_y, width=draw_w, height=draw_h, mask="auto")
    c.restoreState()


def _draw_silhouette(c, x: float, y: float, size: float, gender: str | None = None) -> None:
    """A generic person-silhouette placeholder when the member has no profile picture -- simple
    vector shapes (no external icon font/image dependency), legible at card scale.

    2026-11-28: differentiated by gender -- same lowercase "male"/"female" match
    id_generator.gender_code() already uses elsewhere in this codebase (anything else, including
    unset, falls back to the original neutral shape, same as that function's own "GB" default)."""
    c.setFillColor(_PHOTO_BG)
    c.roundRect(x, y, size, size, 4, fill=1, stroke=0)
    c.setFillColor(_SILHOUETTE)
    cx, cy = x + size / 2, y + size * 0.60
    head_r = size * 0.17
    head_cy = cy + head_r * 0.9
    if (gender or "").strip().lower() == "female":
        # A single flat silhouette color can't show hair AND a face as separate shapes if both
        # are drawn the SAME color (the first two attempts did exactly that and just produced one
        # bigger blob, since overlapping same-color shapes have no visible boundary between them).
        # Fixed with the standard two-tone technique instead: draw a wider, slightly darker hair
        # shape BEHIND the head first, then draw the normal face circle ON TOP in the lighter
        # silhouette color -- the darker tone only remains visible as a fringe where the face
        # circle doesn't cover it, which reads cleanly as hair framing a face.
        c.setFillColor(_SILHOUETTE_HAIR)
        c.ellipse(cx - head_r * 1.25, head_cy - head_r * 1.2, cx + head_r * 1.25, head_cy + head_r * 0.5,
                  fill=1, stroke=0)
        c.setFillColor(_SILHOUETTE)
    c.circle(cx, head_cy, head_r, fill=1, stroke=0)
    p = c.beginPath()
    shoulder_y = y + size * 0.14
    p.moveTo(x + size * 0.18, shoulder_y)
    p.curveTo(x + size * 0.22, y + size * 0.42, x + size * 0.78, y + size * 0.42, x + size * 0.82, shoulder_y)
    p.lineTo(x + size * 0.18, shoulder_y)
    p.close()
    c.drawPath(p, fill=1, stroke=0)


def render_card_pdf(
    card_display_id: str, public_id: str, name: str,
    private_id: str | None = None, gender: str | None = None, sun_sign: str | None = None,
    photo_bytes: bytes | None = None,
) -> bytes:
    """Renders ONE Q-Card as a single CR80-sized card (3.370in x 2.125in, the standard
    credit-card/ID-card format, landscape) -- redesigned 2026-11-28 from the original A4-page
    layout, which rendered as a plain letter-sized document dominated by one giant QR code and
    looked nothing like a physical card. private_id/gender/sun_sign/photo_bytes are all optional
    so existing callers that don't have them yet (or a user with no profile picture) still render
    a complete, correctly-laid-out card -- just with a "—" placeholder or a generic silhouette.

    Fields shown: Name, Gender, Zodiac Sign, Private ID, Public ID, QR -- Location was deliberately
    removed (2026-11-28, Admin's own instruction: "does NOT belong on the card").

    public_id is users.public_id_12 (migrations/050) -- the PERMANENT, location-independent
    12-digit identifier, generated exactly once at registration and never rotated. This replaced
    an earlier design (the QR encoding a one-off opaque bearer token from issue_card(), revocable
    via q_card_core.replace()) per the Admin's own explicit architecture decision: "a user must
    have ONE permanent identity the whole world can search, regardless of how many times they
    travel." The tradeoff is real and was flagged before this change, not glossed over: a
    permanent public identifier can never be revoked the way the old opaque token could if a card
    were lost -- but this is exactly how a physical ID card is supposed to work (the printed ID
    NUMBER is the point), and the actual login credential (private_id_9digit) still never appears
    on a QR or anywhere scannable, which is the boundary that actually matters.

    The QR encodes qumanity.in/card/<public_id_12> -- kept SMALL and in a corner here (42pt
    square) -- the original design let it dominate 60% of the page, which both looked
    unprofessional and is unnecessary: a corner-sized QR scans exactly as reliably."""
    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=(_CARD_W, _CARD_H))

    # Background + border
    c.setFillColor(_CREAM)
    c.rect(0, 0, _CARD_W, _CARD_H, fill=1, stroke=0)
    c.setStrokeColor(_GOLD)
    c.setLineWidth(1.5)
    c.rect(1.5, 1.5, _CARD_W - 3, _CARD_H - 3, fill=0, stroke=1)

    # Header band
    header_h = 26
    header_y = _CARD_H - 2 - header_h
    c.setFillColor(_NAVY)
    c.rect(2, header_y, _CARD_W - 4, header_h, fill=1, stroke=0)
    logo_size = header_h - 8
    text_left = 8
    if LOGO_PATH.exists():
        c.drawImage(str(LOGO_PATH), 6, header_y + 4, width=logo_size, height=logo_size,
                    mask="auto", preserveAspectRatio=True)
        text_left = 6 + logo_size + 4
    c.setFillColor(HexColor("#FFD700"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(text_left, header_y + header_h / 2 - 2, "QUMANITY")
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica", 7)
    c.drawRightString(_CARD_W - 8, header_y + header_h / 2 - 2, "Q-CARD")

    # Photo (or silhouette placeholder), left column
    photo_size = 58
    photo_x, photo_y = 8, 10
    if photo_bytes:
        _draw_photo_cover(c, photo_bytes, photo_x, photo_y, photo_size)
    else:
        _draw_silhouette(c, photo_x, photo_y, photo_size, gender)
    c.setStrokeColor(_GOLD)
    c.setLineWidth(1)
    c.roundRect(photo_x, photo_y, photo_size, photo_size, 4, fill=0, stroke=1)

    # Name / Gender + Zodiac Sign / Private ID, middle column
    text_x = photo_x + photo_size + 10
    text_top = header_y - 12
    c.setFillColor(_TEXT)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(text_x, text_top, (name or "")[:26])

    # Gender and Zodiac Sign share one row (two mini-columns) -- both are short single words, so
    # stacking them separately would waste vertical space this small card doesn't have to spare.
    col2_x = text_x + 62
    c.setFillColor(_TEXT_DIM)
    c.setFont("Helvetica", 6)
    c.drawString(text_x, text_top - 15, "GENDER")
    c.drawString(col2_x, text_top - 15, "ZODIAC SIGN")
    c.setFillColor(_TEXT)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(text_x, text_top - 25, gender or "—")
    c.drawString(col2_x, text_top - 25, sun_sign or "—")

    c.setFillColor(_TEXT_DIM)
    c.setFont("Helvetica", 6)
    c.drawString(text_x, text_top - 40, "PRIVATE ID")
    c.setFillColor(_TEXT)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(text_x, text_top - 50, private_id or "—")

    c.setFillColor(_TEXT_DIM)
    c.setFont("Helvetica", 6)
    c.drawString(text_x, text_top - 65, "PUBLIC ID")
    c.setFillColor(_TEXT)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(text_x, text_top - 75, public_id or "—")

    # QR code, small, bottom-right corner (never the page-dominating size the old layout used)
    card_url = f"{CARD_LOGIN_URL}{public_id}"
    qr_buf = io.BytesIO()
    qrcode.make(card_url).save(qr_buf, format="PNG")
    qr_buf.seek(0)
    qr_size = 42
    qr_x = _CARD_W - qr_size - 8
    qr_y = 10
    c.drawImage(ImageReader(qr_buf), qr_x, qr_y, width=qr_size, height=qr_size)
    c.setStrokeColor(_GOLD)
    c.setLineWidth(1)
    c.rect(qr_x, qr_y, qr_size, qr_size, fill=0, stroke=1)
    c.setFillColor(_TEXT_DIM)
    c.setFont("Helvetica", 5)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 7, card_display_id)

    c.showPage()
    c.save()
    return buf.getvalue()


def save_card_pdf(born_here_dir, pdf_bytes: bytes) -> Path:
    """private_account/q_card.pdf under a BORN_HERE user folder -- folder_connector.py's own
    file-under-an-existing-folder convention (save_user_profile()/save_account_ids()), kept here
    instead since q_card_core.py is where the PDF bytes themselves are produced and this is the
    only caller. Writes into "private_account", one of create_user_folder()'s own already-created
    SUB_ACCOUNTS -- never a new folder. Overwrites any previous file at this path: a card is
    replaced, not versioned (same as replace()'s own 'the old token simply stops working'
    semantics) -- there is only ever one CURRENT card's PDF to keep per person."""
    pdf_path = Path(born_here_dir) / "private_account" / "q_card.pdf"
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    return pdf_path
