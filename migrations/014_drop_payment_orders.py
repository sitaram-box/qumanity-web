"""Razorpay removal (2026-10): Qumanity no longer has any payment or donation path -- Qoins are
earned, never purchased (see docs/qoins_earn_reference.md). Nothing in the code reads or writes
`payment_orders` any more.

Drops the table only when it is empty. If a deployment still holds rows, they are kept as
historical data, untouched; no new rows will ever be written because the integration is gone.

Run via tools/run_migrations.py (calls run(conn)).
"""
from __future__ import annotations


def run(conn) -> None:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'payment_orders'"
    ).fetchone()
    if not exists:
        print("    payment_orders: not present, nothing to do")
        return
    rows = conn.execute("SELECT COUNT(*) FROM payment_orders").fetchone()[0]
    if rows == 0:
        conn.execute("DROP TABLE payment_orders")
        conn.commit()
        print("    payment_orders: empty, dropped")
    else:
        print(f"    payment_orders: kept {rows} historical row(s); the Razorpay integration was "
              "removed, so no new rows will be written")
