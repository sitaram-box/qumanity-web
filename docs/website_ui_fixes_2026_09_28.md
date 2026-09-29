# Website fixes and features — 2026-09-28

*This whole round was built and verified on the website (Qumanity_DPG, Flask). The screenshots that prompted it were the website viewed on a phone browser, not the separate React Native Qumanity_App — the same UI decisions apply to both, but no React Native code was written this round.*

## 1. India location fix
See [india_location_fix.md](india_location_fix.md).

## 2. Village/group wallet: no currency, just members + Qoins
Every Collective Board header (Village → Earth, and every sub-group chat) now shows `👥 N members` and `🔷 N Qoins` — never a rupee amount. `board_core.board_view()` / `chat_messages()` return `members` and `qoins`; the rupee value stays inside the Private wallet and the (currently admin-gated) council wallet-history view only.

## 3. Chat text box vs. the on-screen keyboard
`static/js/mobile_keyboard.js`: focusing any compose textarea hides the poems marquee (reclaiming its space) and scrolls the field into view; `visualViewport`'s resize event re-scrolls as the keyboard animates in. Compose bars are also `position: sticky; bottom: 0` inside their chat panel as a CSS-only baseline.

## 4/5. Reactions (Agree / Disagree / Read), sender + Account ID, admin label
New `reactions_core.py`, table `message_reactions`, shared by village sub-group chat (`board_core.py`) and Personal group chat (`social_core.py`). One reaction per person per message, replaceable, no voting. Every message now shows the sender's name **and** Account ID. A village sub-group has an `admin_label` (free text the creator sets, e.g. "RWA Committee" or "Panchayat") shown in its chat header along with the member count.

## 5. Personal timeline restructured
Five top tabs, in this order: **Private Groups** (the existing 1:1 chat list) · **Family Groups** · **Friend Groups** · **Business Groups** · **Create New Group**. `social_core.py`'s `personal_groups` table now has a `category` (family/friends/business/custom) instead of a fixed 5-slots-per-user `kind`, so a user can have *any number* of groups per category:
- Family starts with **Paternal / Maternal / Spouse-Family** (auto-created).
- Friends starts with one **Friends** group.
- Business starts empty, except the Founder/admin gets **Qumanity Team** automatically.
- "Create New Group" files into `category="custom"`; `move_group()` can re-file any group the user owns into a different category later.
No "Custom Group 2/3" wording remains anywhere in the UI.

## 6. Private account
- **Account ID history + switching**: every present-location stay keeps its own Account ID forever (`account_ids` table, already built); the Private profile lists them all, with **Switch to this** on the inactive ones. Switching updates `users.account_id`/`present_location_json` immediately, so Public timeline pages change; Global is unaffected.
- **Requesting a new Account ID**: `social_core.request_new_account` + an admin queue (`/api/admin/account-ids`) — manual council review only. The founder's spec also wants this triggered automatically by a local shop's payment approval; that needs a commerce/shop module that doesn't exist yet, so it's deferred.
- **Foundational-info change requests**: `/api/dashboard/edit-request` now also accepts `dob`, `tob`, `birth_location`, `present_location` (previously name/email/phone only), queued in a new `profile_change_requests` table and still written to the user's real folder as before. `/api/admin/profile-changes` + `/decide` let a council member approve or reject. **Known gap:** approving a DOB/birth-location change updates the stored value but does **not** recompute the zodiac/Kundali — that duplicates a lot of registration logic and is deferred.

## 7. Home page / login gate + "Register a member"
`/login` is now a gate: logo, tagline, **▶️ GO** (reveals the Private ID + PIN form) and **➕ Register New Member** (goes to `/register`), with a "remember my Private ID on this device" checkbox (stored in `localStorage`, never the PIN). A logged-in user can click **🧑‍🤝‍🧑 Register a member** on their dashboard to open `/register?assist=1`; the registration API accepts `assisted: true` and, when the requester has an active session, uses that session's own account as the referrer directly (no code or PIN needed — being logged in already proves who they are), and **keeps them logged in as themself** afterward rather than switching to the new account.

## 8. Election history redesign
- Real `<select>` dropdowns (year × party), not a button grid.
- **Country-specific party lists** (`election_core.PARTIES_BY_COUNTRY`) for all 10 Sub-continent countries — India's own wording is exact ("BJP / NDA Alliance", "INC / INDIA Alliance", "OTH / Independent / Regional / NOTA"); the other 9 are researched best-effort (Afghanistan has only "OTH — no elections currently held").
- **Aggregate sentiment** — a % breakdown, never per-person — shown only on a **Country** page (Lok Sabha, from everyone's `loksabha_2029` answer) and a **State** page (Vidhan Sabha, from `vidhansabha_next`). Nowhere else. `/api/election-sentiment/<level>/<location_id>`.

## A note on this round's editing
Several `.replace()`-based edits to already-large files (`board_core.py`, `social_core.py`) silently no-op'd when their target text had drifted from an earlier edit in the same session, and one multi-function slice-replace in `social_core.py` accidentally dropped `group_by_id`/`_is_member`/`group_messages`/`send_group_message` entirely. All of these were caught by **round-tripping every new endpoint through real HTTP calls** (not just `python3 -c "import ..."` or grep) and fixed before this was called done — a reminder that a clean import is necessary but not sufficient evidence a change actually landed.

## Not built this round
- The full "Master.json v2" / Cloudflare D1 rebuild (deferred, own session — see [india_location_fix.md](india_location_fix.md)).
- Shop-transaction-triggered automatic Account ID approval.
- Zodiac/Kundali recompute on an approved DOB/birth-location change.
- Any React Native code for Qumanity_App (this round only touched the website).
