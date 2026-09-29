# Election history (Private account, optional)

Only the user sees this. Nothing here is required and nothing is shared or used for scoring.

| Election | What the user records |
|---|---|
| **Lok Sabha** (national) | party for the **2 most recent elections** — who they voted for; the **next** one — who they lean towards. The years themselves are never hardcoded: `election_core.loksabha_years()` always returns `[previous, most-recent, next]` and rolls forward on its own once the shown "next" year has passed (e.g. 2019/2024/2029 through 2029, then 2024/2029/2034 from 2030). Each country has its own cycle (`election_cycle_config` table: `last_election_year`, `interval_years`), seeded to a 5-year term and correctable per country by an admin/council member via `GET/POST /api/admin/election-cycle[/<country_code>]` — elections aren't always exactly 5 years apart everywhere, and aren't always on a fixed schedule at all, so this is a manual override, not a formula the code tries to guess. |
| **Vidhan Sabha** (state) | two boxes only: **last election** — who they voted for; **next election** — who they lean towards (states vote at different times, so no fixed years here) |
| **Q-Punch** (village council) | **no choices** — Qumanity shows the **names of the council members they voted for**, whether those candidates won or lost |

**Party options** (`election_core.parties_for_country()`): 4 choices, researched per the 10 Sub-continent countries — the ruling-side alliance, the main opposition alliance, `OTH` (independents/regional parties/NOTA), and an explicit **Not Voted** (appended automatically for every country, distinct from simply leaving a year unanswered). India's are `BJP` (BJP / NDA Alliance), `INC` (INC / INDIA Alliance), `OTH`, `NOTVOTED` (Not Voted).

Storage: `election_history_entries` table (`user_id`, `kind` = `loksabha`|`vidhansabha`, `slot` = a year like `"2024"` for Lok Sabha or `"last"`/`"next"` for Vidhan Sabha, `choice`, `updated_at`) — one row per answered slot, so the Lok Sabha years can roll forward without a schema change; a slot with no row is simply unanswered. The Q-Punch list comes straight from the ballots the user really cast (`election_votes`) plus the tallied result (`village_council`), so nothing there is typed by hand.

**Built (2026-09-28):** `GET/POST /api/election-history`, the website's Private-tab card (`static/js/dash_extras.js`), and the app's `election-history.tsx` screen — all three read the live per-country party list and rolling year set from the API rather than a fixed list baked into the client.
