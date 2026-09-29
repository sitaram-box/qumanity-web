# What a post is and what it costs

## Village (every present resident)
| Type | How | Cost |
|---|---|---|
| **Text** (default, free) | up to **1000 characters** | **free** |
| **Image** | dot icon in the text box → Image | ₹1 |
| **Audio** | dot icon → Audio → **1, 3 or 5 minutes**; record in the app or upload a clip | ₹2 / ₹5 / ₹10 |
| **Video** | dot icon → Video → **1, 3 or 5 minutes** | ₹20 / ₹50 / ₹100 |

The price is shown **before** posting at every step and is taken from the poster's Qoins only after they confirm. Text stays free so nobody is shut out. Voting starts at once (7 days).

## Tehsil → Zone: paid posting for common users
A **Post** button exists on Tehsil, District, State and Zone pages. It is a paid service:

| Level | Text | Image | Audio 1 / 3 / 5 min | Video 1 / 3 / 5 min |
|---|---|---|---|---|
| Tehsil | 100 | 200 | 500 / 700 / 1000 | 700 / 1000 / 2000 |
| District | 200 | 500 | 700 / 1000 / 1500 | 1000 / 1500 / 2000 |
| State | 500 | 700 | 1000 / 1500 / 2000 | 5000 / 7000 / 10000 |
| Zone | 1000 | 2000 | 5000 / 7000 / 10000 | 20000 / 50000 / 100000 |

## Country, Continent, Earth
**No paid posting.** These pages only show council **broadcasts** and **elevated posts** open for voting, plus the Frozen tab.

## Tabs on Tehsil → Earth
1. **Broadcast** — notices from council members.
2. **Voting** — elevated posts open for votes.
3. **Frozen** — the group's post history; **recent winners on top**, each with its score, dates and comments.

Code: prices in `qoin_core.py` (`VILLAGE_PRICES`, `PAID_PRICES`, `post_price`); `/api/qoins/config` returns them for the currency of the user. **Built (2026-09-27):** text posting on Village (free) and Tehsil→Zone (paid, debited from the poster's wallet, blocked if the balance is too low). **Not built:** image/audio/video — they need file storage, which needs the paid Firebase plan on the app side.

**Display rule (updated 2026-09-28):** the table above is in the *local currency* of the poster's country, not a raw Qoin count — a price is shown as `<currency symbol><amount> | <n> Qoin(s)` (e.g. "₹1000 | 2 Qoins" — ₹1000 is two 500-value Qoins), never a bare "1000 Qoins" and never a full sentence. This applies to every place the system asks the user to pay for a feature or service, not posting alone. `board_core.board_view()` returns `post_price` (currency amount), `post_price_qoins` (`qoin_core.to_qoins(post_price)`, the actual Qoins debited — its *length* is `n` above) and `currency`/`currency_symbol`/`currency_name` (via `qoin_core.currency_for`, keyed off the poster's own `present_location.country.code` — so a Nepal-based poster sees NPR, not INR); `static/js/board.js`'s `priceLine()` and the app's `Board.tsx` `Composer` build this from those fields for both the compose placeholder/button and the pay-confirm dialog. (This format went through several iterations the same day — sentence-with-currency → symbol-only → this — the field names on the API never changed, only how the client formats them.)
