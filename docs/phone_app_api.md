# Phone app ↔ website API

*Added 2026-09-28. Identical copies live in `Qumanity_App/docs/` and `Qumanity_DPG/docs/`.*

The website (`Qumanity_DPG`, Flask) is the **single backend** for the website and the phone app. Both platforms therefore share:
- accounts (9-digit Private ID + 5-digit PIN), 12-digit search codes and wallets
- the Collective Board, Q-Punch council, village sub-groups and personal groups
- private chats
- the 0_Earth folder writes

The app is a client of the same `/api/...` routes the website's pages use. There is no separate app backend and no copy of the data.

## Sign-in for the app
| Step | Call | Notes |
|---|---|---|
| Sign in | `POST /login` `{private_id, pin, client: "app"}` | returns `{token}` in addition to the website's normal reply; 5 wrong PINs lock the ID for 15 minutes |
| Register | `POST /api/auth/register` `{…, client: "app"}` | same body as the website wizard; returns `{private_code, token}` |
| Every call | header `Authorization: Bearer <token>` | valid for 30 days; the website then treats the request exactly like a signed-in browser session |
| Change PIN | `POST /api/user/pin` `{current_pin, new_pin, client: "app"}` | old tokens stop working; a fresh token is returned |

**How the tokens are built:**
- Tokens are signed with the website's secret key (`QM_SECRET_KEY`).
- They carry a fingerprint of the PIN hash, so changing the PIN cancels them.
- A bad or expired token gets `401 {"error": "Please sign in again"}`.
- Browser logins are unchanged: the website only returns a token when the request says `client: "app"`.

## Added to the website for the app
- `GET /api/me`: the dashboard's Private-profile data as JSON. The readable IDs and the 9-digit code are left out; the code is revealed only through `POST /api/user/private-code` with the PIN.
- `POST /api/user/pin`: change PIN. The website had no change-PIN route yet, only "forgot PIN".
- `QM_HOST=0.0.0.0` makes the site reachable from phones on the same Wi-Fi. The debugger is then off unless `QM_DEBUG=1`.
- **Fix:** registration now creates the new account's 12-digit search code at once. Before this, it only appeared after a server restart (start-up backfill), so new users could not be found.

## App tour and the one-time rating (added 2026-09-29, `review_core.py`)
- `GET /api/onboarding` returns `{tour: null|"done"|"skipped", review_done}`.
- `POST /api/onboarding/tour` takes `{status: "done"|"skipped"}`.
- `POST /api/reviews` takes `{rating: 1–5, text: ≤100 characters, allow_public}`.
  - It works **once per member**: a second attempt returns 409.
  - `{decline: true}` ("No thanks") also uses that chance.
- `GET /api/reviews/public` needs no sign-in. It returns the average over all ratings and the reviews that are **both** allowed public by the member **and** approved by an admin, showing first name and village only.
- `GET /api/admin/reviews` and `POST /api/admin/reviews/<id>/approve` `{approved}` are for admins only.

The app shows the tour once after the first sign-in (skippable, and it can be replayed from Settings). Then comes the rating, whether the tour was finished or skipped.

## Registering someone else, Account IDs, election labels (2026-09-29)
- **Register a new member:** `POST /api/auth/register` with `assisted: true`.
  - On the website, the signed-in member is the helper and stays signed in as themself.
  - In the app, the helper has signed out and sends `helper_private_id` + `helper_pin`. These are checked **before** the account is created, with the same 5-tries lock as sign-in; a wrong PIN returns 403.
  - The helper is the referrer and is stored in `users.referred_by_user_id`. A cash donation is split between the 8 location wallets, the helper and the new member.
  - Nobody is signed in afterwards: the reply carries `assisted: true` and no token.
- **Account IDs:**
  - `GET /api/people/me` returns `account_history` (with row `id`) and `account_requests`.
  - `POST /api/people/account-ids/switch` takes `{row_id}`. The member's Public and Global pages follow the active one.
  - `POST /api/people/account-ids/request` takes `{present_location}`, one pending request at a time.
  - The council approves with `/api/admin/account-ids…`. Automatic approval through a local shop's payment is not built; it needs a shop/payments module.
- **Election history:** "Lok Sabha" is now **National Election** and "Vidhan Sabha" is **State Election**.
  - `/api/election-sentiment/country|state/<id>` percentages appear on Country and State pages only.
  - Party lists were updated to each country's latest election (see `election_core.PARTIES_BY_COUNTRY`).

## Routes the app uses
- **Locations:** `/api/world-data`, `/api/subcontinent`, `/api/subcontinent/districts`, `/api/india-villages/<tehsil or district id>`
- **Registration helpers:** `/api/zodiac/preview`, `/api/registration/donation-preview`
- **Board:** `/api/board/<level>`, `/api/board/post`, `/api/board/vote`, `/api/board/comment`, `/api/board/removed`
- **Council and sub-groups:** `/api/qpunch/<level>`, `/api/qpunch/volunteer`, `/api/subgroups…`, `/api/chat/<id>`
- **People:**
  - search and profile: `/api/people/search`, `/api/people/me`
  - groups: `/api/people/groups…`
  - requests: `/api/people/invite`, `/api/people/message`, `/api/people/inbox…`
  - private chats: `/api/people/chats…`
- **Wallet:** `/api/wallet/balance[/<tier>/<id>]` (Earth's id is `EARTH`), `/api/wallet/history`, `/api/wallet/donate` (simulated), `/api/qoins/config`, `/api/qoins/preview`
- **Account:** `/api/election-history`, `/api/user/languages`, `/api/user/private-code`, `/api/auth/forgot-pin/*`, `/api/auth/recover-id`
- **Statistics:** `/api/location/stats/<level>/<id>`, `/api/earth/stats`
- **Connection check:** `/api/zodiac/current`

## Checking it
`python3 Qumanity_App/tools/website-check/check_app_api.py` runs 87 checks. It registers two people, then goes through:
- sign-in, posting and voting, all 8 boards and councils
- search by 12-digit code, a message request that is accepted, private and family chats
- wallet, election history, languages, and a PIN change
- bad and missing tokens, and that the website dashboard still works

It works on a **temporary copy** of the database and a temporary 0_Earth folder, so it can be run at any time.

## Monthly sign election (pilot: Rohini Sector 24, `CS.DL.3.4.1A`) — added 2026-09-29

Every month belongs to one sun sign. The election for that sign runs in 4 weeks:

| Week | Dates (Libra 2026) | What happens |
|---|---|---|
| 1 · Candidates come forward | 23–30 Sep (8 days from the sign's start) | Same-sign men and women aged 25–60 living here stand; at most **3 per gender** (chosen at random when more stand) |
| 2–3 · Voting | 1–14 Oct (14 days) | Every same-sign resident aged 5+ votes once — men for a male candidate, women for a female candidate |
| 4 · Results | 15–22 Oct | Most votes wins (tie → earliest nomination). Winners serve **1 year** (15 Oct 2026 – 14 Oct 2027) |

- `GET /api/qpunch/village` → adds `election` (sign, element, status, `week`, `weeks[4]`, `candidates{male,female}`, `turnout`, `eligible_voters`, `winners` + term) and `guide` (`my_sign`, `my_gender`, `role`, `text`, `action` = `stand`/`vote`/null, `can_stand`, `can_vote`, `voted_genders`). Only on the pilot village.
- `GET /api/election/status` → also `guide`, `weeks`, `week`. `GET /api/election/summary` → the `election` object.
- `GET /api/notifications/summary` → `election` = `{sign, week, action, text}` when the member has something to do (counted in `total`).
- `POST /api/election/nominate` `{reason, why_vote, changes, past_work?}` · `POST /api/election/vote` `{candidate_user_id, gender}`.
- Admin automation: `POST /api/admin/election/auto-nominate` (week 1), `POST /api/admin/election/auto-vote` `{turnout?}` (weeks 2–3).

## Dashboard parity calls — added 2026-09-29
`GET /api/timebox`, `GET /api/lunar/phase`, `GET /api/karma/me` (app: Private → Time-box & Kundali) ·
`GET|POST /api/perception/{country|zone}/<id>[/vote]` (Country and Zone pages) ·
`GET /api/referrer/me`, `POST /api/referrer/apply {note}` (Q-Punch) ·
`POST /api/dashboard/edit-request {name?, email?, phone?, dob?, tob?, reason}` (Private → Change my profile).
