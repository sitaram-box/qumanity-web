# Qoins ↔ real payment: Razorpay integration, test mode (2026-10-04)

Second go-live step (after [[docs/karma_finalization_2026_10.md]]). The whole Qoins system was
always a micro-donation model (₹1–₹200 per transaction, `qoin_core.MAX_DONATION`/the Donate
form's own `min=1 max=200`) — never a wallet "top-up store." The gap: both places money was
supposedly changing hands were **entirely simulated**. `api_wallet_donate`'s own docstring said so
outright: *"Simulated donation — no real payment processor."* The registration-time donation was
the same — a client-reported `donation_amount` credited straight into `apply_registration_donation`
with nothing checking real money had moved.

## What was built

New `payment_core.py` (table `payment_orders`) sits in front of both donation paths:

1. `POST /api/payment/order` — creates a `payment_orders` row (status `created`) and, if
   `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` are set, a real Razorpay order via their Orders API
   (plain `urllib`, no new dependency). Returns what the frontend needs to open Razorpay's
   Checkout widget.
2. The frontend (`static/js/payments.js`, shared by `dashboard.js`'s Donate form and
   `register.js`'s registration-time donation) opens Razorpay Checkout with that order.
3. `POST /api/payment/verify` — takes Razorpay's `payment_id`/`order_id`/`signature`, verifies the
   HMAC-SHA256 signature against `RAZORPAY_KEY_SECRET` (`hmac.compare_digest`, timing-safe), marks
   the order `paid`, and ONLY THEN calls `wallet_core.apply_donation`/`apply_registration_donation`
   — using the amount/purpose/referrer/location **stored on the order row**, never anything the
   client sends at this step. A double-verify on an already-paid order is rejected.

**Dev-mode fallback**: with no Razorpay keys set (true today, in local dev), `create_order`
returns `{"mode": "simulated", ...}` and `verify_payment` just marks the order paid without
checking a signature — the exact same "credit immediately" behavior the old simulated route had,
so nothing breaks locally before the Founder sets real keys. This mirrors the existing
`QM_DEV_SHOW_OTP` convention (`api_forgot_pin_request`) rather than inventing a new one.

## Registration-time donation: the harder fix

The donation step inside `/api/auth/register` used to credit inline from whatever
`donation_amount` the client sent — a real free-Qoins hole once this goes live with actual money.
Fixed by splitting it: the account is created and session set exactly as before, but if the
donation amount is real money (self-registration, amount > 0), **nothing is credited yet** —
the response carries `donation_pending_amount` instead, and `register.js` immediately runs the
same order→Checkout→verify sequence against the now-logged-in new account, via
`purpose: "registration"`.

**Assisted registrations** (`helper_user_id` set — someone else is registering a new member) are
forced to the free path regardless of the amount they entered: the new member has no live session
in that response to pay from, and a real-money credit must never run off a client-reported number.
A paid registration donation for an assisted signup isn't wired — the new member can Donate for
real from their own dashboard once they have an account. Documented as a known gap, not silently
dropped.

## Verified (test-mode logic, without live Razorpay credentials)

No Razorpay account credentials exist in this environment yet, so full live-sandbox verification
needs the Founder's own test keys (see "Going live" below). What was verified directly:

- **Full registration → payment → credit path**, via a real throwaway test account (created,
  verified, fully deleted after — DB rows across every referencing table, wallet balances reversed
  by exact transaction amount, `location_elements` decremented, the physical `0_Earth` leaf folder
  removed): registering with a ₹50 donation correctly left it uncredited (`donation_pending_amount:
  50`) until `/api/payment/order` + `/api/payment/verify` ran, which then credited exactly
  `topup_split(50)` = 34 self / 16 village, locked self-share.
- **Double-verification is rejected** ("This order has already been credited.").
- **Amount bounds enforced** (₹1–₹200; a ₹999 request is rejected before any Razorpay call).
- **The standalone Donate flow** (`purpose: "donation"`) end-to-end, including the no-referrer
  tier-based split across every location level from Earth down to village.
- **The HMAC signature check itself**, in isolation with a fake test key/secret (since no real
  Razorpay order can be created without a real account): a correctly-signed payment is accepted; an
  incorrect signature is rejected; a payment claiming a different `razorpay_order_id` than the one
  actually created is rejected ("Order mismatch"). This test caught and fixed a real bug:
  `verify_payment` was returning the pre-update row, so its `status` field read `"created"` even
  after the database row was already `"paid"` — fixed by re-reading the row after the update.

## Going live (when the Founder is ready)

1. Sign in to the already-registered Razorpay account ("SITA Foundation"), switch to **Test Mode**,
   and generate a test Key ID/Secret (Settings → API Keys) — no KYC needed for test mode.
2. Set `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` in the server's environment (never commit them to a
   file in this repo). The moment they're set, every donation (registration or standalone) requires
   a real Razorpay test payment — pay with Razorpay's own published test card numbers.
3. Once that's proven end-to-end with real test-mode traffic, switching `RAZORPAY_KEY_ID`/`SECRET`
   to the account's live keys is the only change needed to go live — same code path either way.

## Scope, per the Founder's own 2026-10-04 answer

Real-money Qoins flows are **India only** — this entire integration is India-specific (the Donate
form, the registration donation step). The other 9 Sub-continent countries keep Qoins as a pure
internal point system; nothing here touches them.
