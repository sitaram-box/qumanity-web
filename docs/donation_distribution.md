# Donation at registration and top-ups

Donation is **optional**. The registration page has a toggle, **off by default**, that explains where the money goes and that a share comes back to the donor as Qoins. Maximum **200** per member for registration. The amount is chosen from `1, 2, 5, 10, 20, 50, 100, 200` or typed freely (whole numbers, ≤ 200), in the user's own currency (see [qoins_wallet_system.md](qoins_wallet_system.md)). The section shows, live, **what each of the 10 recipients gets** and how many Qoins that is.

## The 10 recipients
Earth · Continent · Country · Zone · State · District · Tehsil · Village (the new user's *present* location chain) · **Referrer (User A)** · **New user (User B)**.

## With a referrer
| Donation | Each of the 8 location wallets | Referrer A | New user B |
|---|---|---|---|
| 0 (free) | 0 | 90 paise | 10 paise |
| 1 | 0 | 0.50 | 0.50 |
| 2 | 0 | 1 | 1 |
| 3–10 (5, 10 in the brief) | 0 | 60% (5 → 3, 10 → 6) | rest (5 → 2, 10 → 4) |
| 11–20 | 1 | 60% of the rest | rest |
| 21–50 | 2 | 60% of the rest | rest |
| 51–100 | 5 | 60% of the rest | rest |
| 101–200 | 10 | 60% of the rest | rest |

"Rest" = donation − 8 × per-location amount. Rounding: whole numbers, referrer = round(60%), user = remainder.
- ₹15 → 8 × 1 = 8; rest 7 → **A 4, B 3**
- ₹36 → 8 × 2 = 16; rest 20 → **A 12, B 8**
- ₹100 → 8 × 5 = 40; rest 60 → **A 36, B 24**
- ₹200 → 8 × 10 = 80; rest 120 → **A 72, B 48**

Code: `wallet_core.calculate_donation_distribution`. Free (₹0) and ₹1 paise cases are recorded in paise.

## Without a referrer (independent visitor)
The donor's own wallet and **their own village wallet** share the amount:

| Donation | Own wallet | Qoins | Village wallet | Qoins |
|---|---|---|---|---|
| 1 | 1 | 1 | 0 | – |
| 2 | 1 | 1 | 1 | 1 |
| 5 | 3 | 2+1 | 2 | 2 |
| 10 | 6 | 5+1 | 4 | 4 |
| 20 | 12 | 10+2 | 8 | 5+2+1 |
| 50 | 34 | 20+10+2+2 | 16 | 10+5+1 |
| 100 | 68 | 50+10+5+2+1 | 32 | 20+10+2 |
| 200 | 136 | 100+20+10+5+1 | 64 | 50+10+2+2 |
| 500 | 372 | 200+100+50+20+2 | 128 | 100+20+5+2+1 |

Any other amount: 60% own / 40% village (`qoin_core.topup_split`). The top-up in the Private wallet (after registration) may go up to 500.

## When Qoins arrive
| Recipient | Credited |
|---|---|
| 8 location wallets | immediately, visible to everyone in real time |
| Referrer | immediately |
| New user B | **locked** until B's first vote in the village council election; the new council then approves it |

## Free registration
Nobody is turned away: with no money, **1 Qoin of value 1** is still created (90p to the referrer, 10p to the user — [conflict #1](qoins_wallet_system.md)).
