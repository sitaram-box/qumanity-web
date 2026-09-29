# Qoins and wallets

*Spec of 2026-09-27. Code: `Qumanity_DPG/qoin_core.py` (denominations, currencies, top-up, rewards, prices) and `wallet_core.py` (balances and transactions). Same file lives in `Qumanity_App/docs/` and `Qumanity_DPG/docs/`.*

## 1. Two kinds of wallet
| Wallet | Owner | Lives in | Purpose |
|---|---|---|---|
| **Private wallet** | one person | their Private account | personal Qoins: rewards, top-ups, paying for posts |
| **Group wallet** | a location group, Village → Earth (8 wallets) | the location's folder in `0_Earth` | community Qoins, visible to that group's Q-Punch council |

Nested-folder storage (source of truth for the files, mirrored into SQLite/Firestore for speed):
```
0_Earth/…/<Village>/group_wallet/{balance.json, qoin_breakdown.json, transactions/2026-W39.json}
0_Earth/…/<Village>/BORN_HERE/<element>/<Private ID>/private_account/wallet/{balance.json, qoin_breakdown.json, transactions/2026-W39.json}
                                                                       /election_history.json
```
Only the folders that already exist under `0_Earth` are used; no new top-level folders.

## 2. Currency
Every Qoin carries one of the **currency-range values `1, 2, 5, 10, 20, 50, 100, 200, 500`** — the same numbers in every country. The symbol and name follow the country the user **presently lives in**, and change automatically when their present location changes.

| Country | Currency | Symbol |
|---|---|---|
| India | INR | ₹ |
| Nepal | NPR | Rs |
| Bangladesh | BDT | ৳ |
| Sri Lanka | LKR | Rs |
| Pakistan and Balochistan | PKR | Rs |
| Bhutan | BTN | Nu. |
| Maldives | MVR | Rf |
| Afghanistan | AFN | ؋ |
| Myanmar | MMK | K |

A Qoin of value 100 in Nepal is worth "100 Nepalese Rupees"; there is **no exchange rate** between countries. (The brief also listed Mauritius; it is not one of the 10 Sub-continent countries — Balochistan is — so it is not included. ❓ confirm.)

## 3. Turning an amount into Qoins
A wallet stores an **amount**. It is shown as the **fewest Qoins, highest value first** (`qoin_core.to_qoins`):

| Amount | Qoins |
|---|---|
| 289 | 7 Qoins: 200 + 50 + 20 + 10 + 5 + 2 + 2 |
| 500 | 1 Qoin: 500 |
| 47 | 4 Qoins: 20 + 20 + 5 + 2 |
| 123 | 4 Qoins: 100 + 20 + 2 + 1 |

*The brief wrote 289 as `…+ 5 + 3 + 1`, but 3 is not a permitted value; the greedy result above also gives 7 Qoins.*

**Paying (debit):** the wallet total drops by exactly the price and the rest is shown again as the fewest Qoins (`qoin_core.debit_plan`). "1 minute audio costs 1 Qoin of value 2" therefore means "₹2 from the wallet".

## 4. Where Qoins come from
1. **Registration** — free (1 Qoin minted) or donated: [donation_distribution.md](donation_distribution.md).
2. **Independent top-up** (no referrer) — the table in that file.
3. **Post rewards** — [post_rewards.md](post_rewards.md).
4. Later: other Karma types.

The **new user's own share stays locked** until they cast their first election vote in their village; the new village council then approves the credit (`wallet_core.unlock_user_share`). Referrer and location shares are credited **immediately** and shown live to everyone.

## 5. Where Qoins go
Posting with media and paid posts on higher pages: [post_types_pricing.md](post_types_pricing.md).

## 6. SQLite mirror (website) / Firestore (app)
`wallets(owner_type, owner_id, balance_qoins)`, `wallet_transactions(wallet_id, amount_qoins, reason, locked, related_user_id, created_at)` exist today. Planned additions: `currency`, `week_number`, `year`, `pending_qoin_credits`, `referrals`, `election_history` (see the other docs). The nested JSON files are written from the same transaction so the two never disagree.

## 7. Conflicts found in the brief and how they were resolved
| # | Brief says | Used | Status |
|---|---|---|---|
| 1 | Free account: "10% to user, 10% to each group wallet" **and** "90 paise to referrer, 10 to user" (adds up to 180 paise) | **Decided 2026-09-27:** 10 paise to each of the 10 shares (8 location tiers + referrer + new user) = ₹1 exactly. With no referrer, their 10p folds into the new user's share (20p). Sub-rupee amounts are kept in a `wallets.paisa_balance` ledger and only become a real Qoin once a wallet reaches 100 paise. | ✅ built |
| 2 | First rule "10% to each of 8 groups + 10% to user" vs the later bracket table | the **bracket table** (per-location ₹1/2/5/10) replaces the 10% wording for donations ≥ ₹1; the flat 10%-each rule now applies only to the ₹0 free case (item 1) | used |
| 3 | ₹15 → referrer 4.20, user 2.80 in one place, 4 and 3 in another | **whole numbers**: referrer = round(60% of the rest), user = the remainder | used |
| 4 | Earth participant reward "100 + 50 = 200" | **Decided 2026-09-27: 100 + 100 = 200.** The winner is whoever has the highest score among the posts freezing at Earth in the same settle pass; every other positive-score post gets the participant reward. | ✅ built |
| 5 | Top-up table in the code sample gave ₹5 → village 1 Qoin | the **worded rules** (₹5 → own 3, village 2 …) | used |
| 6 | No-referrer registration donation | the **top-up table** below, not the earlier 80/20 in `wallet_core` (to change when the registration donation UI is built) | to do |
| 7 | "Post on Tehsil → Earth" then "Tehsil → Zone only" | paid posting **Tehsil → Zone only** | used |
| 8 | Earth "winner" (highest score) | **Decided:** highest score among Earth posts freezing together; ties all count as winners | ✅ built |
