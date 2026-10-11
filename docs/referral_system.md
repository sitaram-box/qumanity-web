# Referrals and volunteers

**Referral ID** is optional for everyone (Sub-continent users and foreigners).

## Who gets one (built 2026-09-27)
- Anyone signed in can **apply** from the Q-Punch popup's 5th seat, with a short note on why. Council members (admins today) see pending applications there and **approve or decline**.
- Approval mints a unique code like `REF-7K2QDX` (`board_core.py`: `referrer_applications`, `referrers`). One application at a time; a user cannot apply twice or hold two codes.
- A volunteer registers **bank account details** (needed to pay out) and their own **9-digit Private ID** (used to confirm cash).
- Format `REF-<VOLUNTEER>-<CHECK>`, e.g. `REF-VOL0042-X7K` (checksum stops typing mistakes).

## Sharing
The volunteer publishes the code/link on WhatsApp or social media. When someone opens the website/app through it, the code is **recorded automatically** on the registration form.

## Registration flow (donation ON)
1. New user B fills the registration form, switches the donation toggle on, picks an amount and types A's code.
2. The live split shows on screen ([qoins_earn_reference.md](qoins_earn_reference.md)).
3. B pays A **cash**, in person.
4. **Cash verification (built):** A types **their own 5-digit PIN** into the registration form to confirm the cash was received. The account is created either way, but the donation is only applied if the PIN matches; if it does not, B is registered as if no referral code was given (donation lost, not blocked).
   - Online payment (UPI/QR/webhook) is **not built** — no payment provider is connected yet.
5. Credits: the 8 location wallets and A are credited **immediately**; B's own share is **locked** until B's first council vote.
6. No donation: B is registered free; the ₹1 Qoin is still split 10 ways ([qoins_earn_reference.md](qoins_earn_reference.md)).

## Rules
- One code use per new account; a volunteer cannot refer themselves.
- Every code use is logged (`referrals`: code, owner, used_by, amount, currency, status, times).
- Volunteers are **village-level** helpers; **agents** (professional, hired) are described in [qpunch_council.md](qpunch_council.md).
- **Not built:** online payment (needs a payment provider and, for the app, the paid Firebase plan for webhooks); volunteer bank-account storage (deliberately not collected yet — a referrer is only asked for their PIN, never bank details, until a secure payments flow exists).
