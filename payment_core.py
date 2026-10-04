"""Real-money Qoins donations via Razorpay (India only -- the Founder's own registered, approved
Razorpay account, "SITA Foundation"). Replaces the previous purely-simulated donate flow.

Test mode first (2026-10-04 instruction): until RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET are set in the
environment, `create_order`/`verify_payment` fall back to the exact same "credit immediately, no
real gateway" behaviour the old simulated `/api/wallet/donate` had -- so local dev keeps working
unchanged. Once those two env vars hold real Razorpay keys (test keys first, live keys only when
the Founder is ready), every donation actually requires a verified Razorpay payment before a single
Qoin is credited. Mirrors the "simulated until a provider is connected" pattern already used for
OTP delivery (see `api_forgot_pin_request`'s QM_DEV_SHOW_OTP).

Nothing here ever trusts amount/purpose/referrer supplied at verification time -- those are fixed
on the `payment_orders` row the moment the order is created, and `verify_payment` only reads them
back from that row, never from the client, before any `wallet_core.apply_*` credit runs.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request

RAZORPAY_API_BASE = "https://api.razorpay.com/v1"
MIN_AMOUNT = 1
MAX_AMOUNT = 200  # matches qoin_core.MAX_DONATION -- the whole Qoins system is a micro-donation model, not a wallet top-up store

SCHEMA = """
CREATE TABLE IF NOT EXISTS payment_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    purpose TEXT NOT NULL,                 -- 'donation' | 'registration'
    amount_rupees INTEGER NOT NULL,
    referrer_user_id INTEGER,
    present_location_json TEXT NOT NULL,
    razorpay_order_id TEXT,
    razorpay_payment_id TEXT,
    status TEXT NOT NULL DEFAULT 'created', -- created | paid
    created_at TEXT NOT NULL,
    paid_at TEXT
);
"""


def ensure_tables(conn) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def is_configured() -> bool:
    return bool(os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET"))


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _razorpay_request(method: str, path: str, body: dict | None = None) -> dict:
    key_id = os.environ["RAZORPAY_KEY_ID"]
    key_secret = os.environ["RAZORPAY_KEY_SECRET"]
    auth = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
    req = urllib.request.Request(
        RAZORPAY_API_BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise ValueError(f"Razorpay error: {e.read().decode(errors='replace')}") from e
    except urllib.error.URLError as e:
        raise ValueError(f"Could not reach Razorpay: {e}") from e


def create_order(conn, user_id: int, purpose: str, amount_rupees: int, present_location: dict,
                  referrer_user_id: int | None = None) -> dict:
    if purpose not in ("donation", "registration"):
        raise ValueError("Unknown payment purpose.")
    if not (MIN_AMOUNT <= amount_rupees <= MAX_AMOUNT):
        raise ValueError(f"Amount must be between ₹{MIN_AMOUNT} and ₹{MAX_AMOUNT}.")
    ensure_tables(conn)
    cur = conn.execute(
        """INSERT INTO payment_orders (user_id, purpose, amount_rupees, referrer_user_id,
               present_location_json, status, created_at) VALUES (?, ?, ?, ?, ?, 'created', ?)""",
        (user_id, purpose, amount_rupees, referrer_user_id, json.dumps(present_location), _now()),
    )
    local_order_id = cur.lastrowid
    conn.commit()

    if not is_configured():
        return {"mode": "simulated", "local_order_id": local_order_id, "amount_rupees": amount_rupees}

    razorpay_order = _razorpay_request("POST", "/orders", {
        "amount": amount_rupees * 100,
        "currency": "INR",
        "receipt": f"qm-{local_order_id}",
        "notes": {"local_order_id": str(local_order_id), "purpose": purpose},
    })
    conn.execute("UPDATE payment_orders SET razorpay_order_id = ? WHERE id = ?", (razorpay_order["id"], local_order_id))
    conn.commit()
    return {
        "mode": "razorpay",
        "local_order_id": local_order_id,
        "razorpay_order_id": razorpay_order["id"],
        "amount_rupees": amount_rupees,
        "amount_paise": amount_rupees * 100,
        "currency": "INR",
        "key_id": os.environ["RAZORPAY_KEY_ID"],
    }


def verify_payment(conn, local_order_id: int, user_id: int, razorpay_payment_id: str | None,
                    razorpay_order_id: str | None, razorpay_signature: str | None) -> dict:
    """Marks the order paid and returns the ORDER ROW (its own stored amount/purpose/referrer/
    location, never anything from the caller) -- it never credits Qoins itself; callers run the
    matching wallet_core.apply_* against this row's own fields."""
    ensure_tables(conn)
    order = conn.execute(
        "SELECT * FROM payment_orders WHERE id = ? AND user_id = ?", (local_order_id, user_id)
    ).fetchone()
    if not order:
        raise ValueError("Unknown payment order.")
    if order["status"] == "paid":
        raise ValueError("This order has already been credited.")

    if is_configured():
        if not (razorpay_payment_id and razorpay_order_id and razorpay_signature):
            raise ValueError("Missing Razorpay payment confirmation.")
        if razorpay_order_id != order["razorpay_order_id"]:
            raise ValueError("Order mismatch.")
        key_secret = os.environ["RAZORPAY_KEY_SECRET"]
        expected = hmac.new(
            key_secret.encode(), f"{razorpay_order_id}|{razorpay_payment_id}".encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, razorpay_signature):
            raise ValueError("Payment signature verification failed.")
        conn.execute(
            "UPDATE payment_orders SET status = 'paid', razorpay_payment_id = ?, paid_at = ? WHERE id = ?",
            (razorpay_payment_id, _now(), local_order_id),
        )
    else:
        conn.execute("UPDATE payment_orders SET status = 'paid', paid_at = ? WHERE id = ?", (_now(), local_order_id))
    conn.commit()
    return dict(conn.execute("SELECT * FROM payment_orders WHERE id = ?", (local_order_id,)).fetchone())
