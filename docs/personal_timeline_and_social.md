# Personal timeline, search, and account recovery

*Built 2026-09-27.* Code: `social_core.py` (groups, requests, chats, search, Account-ID history), `recovery_core.py` (PIN reset, Private-ID recovery), routes in `app.py`, UI in `static/js/social.js` + `static/css/dashboard.css`.

## The 12-digit public search ID
Every **Account ID** a user has ever held (see below) gets its own random 12-digit search code, generated once and never reused. The **current** one is shown on the Public profile as "safe to share"; it is never the same value as the 9-digit Private ID, and it can also be looked up by typing the readable Account ID string directly.

## Account ID history
A person's present location can change over their life, and every distinct stay keeps its own Account ID **forever** (`account_ids` table): moving away and later moving back generates a **new** Account ID each time, never a reused one. The Private profile has a "Past Account IDs" list showing every one, its place, and whether it is current. Only the current one is searchable; older ones are history only.

## Personal timeline: categories, not a fixed 5 groups
*Rewritten 2026-09-28.* `personal_groups.category` is one of `family` / `friends` / `business` / `custom` — a user can own **any number** of groups in each category (not a fixed slot each). Defaults, auto-created on first use: Family gets **Paternal**, **Maternal**, **Spouse-Family**; Friends gets one **Friends** group; Business starts empty (the Founder's own account additionally gets a **Qumanity Team** business group). A `business`-category group also carries a business name, sector and services, editable by its owner.

The owner invites anyone (someone in another of their groups, or a stranger found by search) into any group they own; the invitee must accept. Once accepted, the group is a shared chat both people see — the owner's copy, not a duplicate. `social_core.my_groups()` returns every category's `{owned, joined}` lists; a user's Personal-tab UI shows every group **they own** plus every group **someone else** has approved them into.

**App UI (2026-09-28):** the phone app simplifies this to 3 buttons — **Private** (business + custom groups combined), **Family**, **Friends** — plus a **Create New Group** action, each opening its own list screen (`groups/[category].tsx`); tapping a group opens its own chat screen. Nothing is ever shown inline on the Personal tab itself (`lib/groupBuckets.ts` holds the bucket↔category mapping). The website keeps all 4 categories visible as their own tabs.

## Requests: one-time message, or a group invitation
- **Message request**: a first message to someone found by search, sent once. They can **Accept** (opens a private one-to-one chat, delivering that first message), **Decline**, or leave it **Waiting**.
- **Group invitation**: only the group's owner can send it. Accepting adds the invitee as an approved member of that specific group.
- Both land in the recipient's **Requests** inbox on the Personal tab.

## Private one-to-one chats
Opened only by an accepted message request. `private_chats` is keyed by the pair of user ids (order-independent), so there is at most one chat per pair.

## Wallet weekly history
`wallet_core.weekly_history()` groups every unlocked transaction into ISO weeks (Monday–Sunday, matching "updates when Sunday ends and Monday begins"). A user sees the last 3 months on their own Private wallet; a group wallet's older weeks (and the full history) are for **council members only** — currently gated by `_is_admin()` as a placeholder, since elected council seats are not fully built above the pilot village yet.

## Election history (Private account, optional)
See `docs/election_history.md` for the full picture — per-country party lists (4 choices, including an explicit "Not Voted"), rolling Lok Sabha years (`election_core.loksabha_years()`, council-editable), and Vidhan Sabha's last/next. `election_core.save_party_history` / `get_party_history`.
- **Q-Punch**: not editable — it is read straight from the ballots the user actually cast (`election_votes` joined with `village_council`), so it always matches reality, including whether that candidate won.

## Recovering access
- **Forgotten PIN**: self-service, by a one-time code sent to the phone or email already on the account (`/forgot-pin`). No SMS/email provider is connected yet, so delivery is **simulated** — the code is generated and hashed exactly as a real one would be, but only appears in the server console (`QM_DEV_SHOW_OTP=1` also returns it in the API response, for testing only — never enable this in a real deployment). Five wrong attempts void the code.
- **Forgotten Private ID**: never self-service, and never emailed or texted — it is a login credential. `/recover-id` collects name, DOB, birth country, contact details and a home address. The system tries to auto-match a single account by name + DOB + birth country; if it finds exactly one, the request is marked "matched". The Founder's team reviews the queue, and the ID is only ever handed over by **physical letter**, prepared after an admin explicitly reveals it (`/api/admin/recover-id/<id>/reveal`) — every reveal is logged (`id_recovery_reveals`).

## Not built
- No admin-facing page for the ID-recovery queue yet (API only — `/api/admin/recover-id`, `/decide`, `/reveal`).
- No real SMS/email provider (needs Twilio/SendGrid or similar, plus the paid Firebase plan on the app side).
- Real elected council seats above the pilot village, which the wallet-history and reveal permissions should eventually check instead of the blanket `_is_admin()` flag.
