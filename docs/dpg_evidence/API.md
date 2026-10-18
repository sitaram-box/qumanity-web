# Qumanity API reference

Every JSON route in qumanity-web's `app.py`, read from the code on 11 October 2026, updated 14 October 2026, 17 October 2026 and 18 October 2026: 178 routes under `/api`, counted as rules in the Flask URL map at commit c09b91f. Seven of those rules accept two methods (shown as `GET/POST`), so the tables hold 185 method-and-path pairs; on 18 October 2026 the pairs in the tables were compared with the pairs in the URL map, and the two sets are identical. The website and the phone app call the same routes. `docs/phone_app_api.md` describes only the routes the phone app uses; this file covers all of them.

## Conventions

- **Base URL:** `https://qumanity.in` in production, `http://localhost:5000` locally.
- **Format:** requests and responses are JSON (UTF-8). Errors return `{"error": "<message>"}` with a 4xx status.
- **Signing in:** the website signs in through `/login` and keeps a signed session cookie. The phone app sends `Authorization: Bearer <token>`, the token returned by `/api/auth/register` or by `/login` when the app signs in. Tokens are signed with HMAC (`itsdangerous`), expire after 30 days, and stop working when the member changes their PIN. A valid token counts exactly like a session.
- **Path IDs:** `<level>` is one of the location levels (village to earth). `<path:location_id>` is a dotted location ID such as `CS.DL.3.4.1A`. `<scope>` on the reactions route is `subgroup`, `personal`, or `board_post` (the last accepted only when the target post is a council update).

## Access levels

| Access | Meaning | Routes |
|---|---|---|
| Public | No sign-in needed | 37 |
| Member | Signed-in member (`login_required`) | 85 |
| Council or admin | Signed in, and an elected council member of the location (or the administrator) | 6 |
| Admin Panel scope | Signed in, and either the administrator (every location) or a village council head during their current term (their own village's council messages only), as decided by `_is_admin_panel_user()`. A message from another village returns 404, not 403. Four routes, under `/api/admin/panel/` | 4 |
| Admin | Signed in, and the member's Private ID is listed in `QM_ADMIN_PRIVATE_IDS`; anyone else gets 403 | 46 |

Parameters list the query-string keys and JSON body keys the route reads. Response fields list the top-level keys of the JSON the route returns directly; "(built by a helper)" means the response object is assembled in a `*_core.py` module.

## Access problems

One route still exposes member data without sign-in. It is marked ⚠ below and recorded in Document 07 (action 3) and Document 10 (10.2 row 3).

| Route | Problem |
|---|---|
| `GET /api/location/members/village/<path:village_id>` | Public. Lists names, gender and age category of a village's members. |

Closed on 14 October 2026:

| Route | Fix |
|---|---|
| `POST /api/admin/sync-folders` | Now requires sign-in and an admin check |
| `GET /api/user/zodiac/<int:user_id>` | Now requires sign-in; returns 403 unless the ID is the signed-in member's own |
| `GET /api/user/kundali/summary/<int:user_id>` | Same |
| `GET /kundali/<int:user_id>` (page) | Same |

## Routes

### Sign-in, account and profile

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| POST | `/api/user/private-code` | Member |  | `private_code` |
| POST | `/api/auth/forgot-pin/request` | Public | body: `channel`, `private_id` | (built by a helper) |
| POST | `/api/auth/forgot-pin/verify` | Public | body: `new_pin`, `otp`, `private_id` | `status` |
| POST | `/api/auth/recover-id` | Public |  | `status`, `reference` |
| GET/POST | `/api/user/languages` | Member | body: `daily`, `preferred` | `languages`, `preferred` |
| GET | `/api/me` | Member |  | (built by a helper) |
| POST | `/api/user/pin` | Member | body: `client`, `current_pin`, `new_pin` | (built by a helper) |
| GET | `/api/onboarding` | Member |  | (built by a helper) |
| POST | `/api/onboarding/tour` | Member |  | (built by a helper) |
| GET/POST | `/api/profile/personal-details` | Member | body: `daughters_count`, `has_children`, `relationship_status`, `sons_count`, `work_profile`, `work_profile_other` | `status`, `relationship_status`, `has_children` |
| POST | `/api/dashboard/edit-request` | Member | body: `reason` | `status` |
| POST | `/api/auth/register` | Public | body: `assisted`, `birth_location`, `client`, `dob`, `email`, `gender`, `helper_pin`, `helper_private_id`, `language`, `name`, `phone`, `pin`, `present_location`, `tob` | `user_id`, `private_code`, `token`, `assisted` |

### Location data and statistics

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| GET | `/api/global-data` | Public |  | (built by a helper) |
| GET | `/api/world-data` | Public |  | (built by a helper) |
| GET | `/api/india-states` | Public |  | (built by a helper) |
| GET | `/api/india-districts` | Public |  | (built by a helper) |
| GET | `/api/subcontinent` | Public |  | (built by a helper) |
| GET | `/api/subcontinent/districts` | Public |  | (built by a helper) |
| GET | `/api/subcontinent/stats` | Public | query: `basis` | (built by a helper) |
| GET | `/api/scoreboard/india` | Public |  | (built by a helper) |
| GET | `/api/india/state-districts/<path:state_id>` | Public | body: `zones` | `type`, `features` |
| GET | `/api/india-villages/<path:tehsil_id>` | Public |  | `tehsil_id`, `villages` |
| GET | `/api/country/stats/<path:country_id>` | Public |  | (built by a helper) |
| GET | `/api/continent/stats/<path:continent_id>` | Public |  | (built by a helper) |
| GET | `/api/location/stats/<level>/<path:location_id>` | Public | query: `basis` | `level`, `location_id`, `basis`, `total_humans`, `gender`, `age_bands`, `elements`, `signs`, `karma_total`, `qoins_wallet_balance` (counts from 1 to 4 shown as `"<5"`) |
| GET | `/api/location/stats/<level>/<path:location_id>.csv` | Public | query: `basis` | CSV with `metric,value` rows: the same fields and suppression |
| GET | `/api/location/members/village/<path:village_id>` | Public ⚠ |  | `members` |
| GET | `/api/earth/stats` | Public |  | (built by a helper) |
| GET | `/api/location/elements/<path:location_id>` | Public | query: `type` | `location_id`, `location_type`, `total_users`, `birth_users`, `<element>_count`, `<element>_percentage` (counts from 1 to 4 shown as `"<5"`, with the matching percentage `null`) |
| GET | `/api/global/elements` | Public |  | `earth`, `all_locations` |

### Astrology, lunar calendar and time

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| GET | `/api/timebox` | Member |  | (built by a helper) |
| GET | `/api/user/zodiac/<int:user_id>` | Member (own ID only) |  | (built by a helper) |
| GET | `/api/me/kundali` | Member |  | (built by a helper) |
| GET | `/api/user/kundali/summary/<int:user_id>` | Member (own ID only) |  | (built by a helper) |
| GET | `/api/zodiac/signs` | Public |  | (built by a helper) |
| GET | `/api/zodiac/current` | Public |  | `date`, `sign`, `element` |
| GET | `/api/zodiac/preview` | Public | query: `dob` | `sign`, `element`, `age_code`, `age_name` |
| GET | `/api/lunar/phase` | Public |  | `current`, `upcoming` |

### Karma

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| GET | `/api/karma/me` | Member |  | `score`, `history` |
| GET | `/api/karma/user/<int:user_id>` | Member |  | `score` |
| GET | `/api/karma/collective/<level>/<path:location_id>` | Public |  | `location_id`, `level`, `points` |

### Qoins and wallets

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| GET | `/api/wallet/history` | Member |  | (built by a helper) |
| GET | `/api/wallet/history/<location_type>/<path:location_id>` | Member |  | (built by a helper) |
| GET | `/api/qoins/config` | Member |  | `currency`, `symbol`, `currency_name`, `denominations`, `village_prices`, `paid_prices` |
| GET | `/api/qoins/preview` | Public | query: `amount` | `amount`, `qoins` |
| GET | `/api/wallet/balance` | Member |  | `balance_qoins`, `qoin_count`, `has_locked_share`, `transactions` |
| GET | `/api/wallet/balance/<location_type>/<path:location_id>` | Public |  | `location_type`, `location_id`, `qoin_count`; also `balance_qoins` for that location's council or the administrator |

### Collective Boards, sub-groups and reactions

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| GET | `/api/board/<level>` | Member |  | (built by a helper) |
| POST | `/api/board/post` | Member | body: `content`, `level` | `id` |
| POST | `/api/board/vote` | Member | body: `post_id`, `value` | `score` |
| POST | `/api/board/comment` | Member | body: `post_id`, `text` | `status` |
| POST | `/api/board/council-update` | Council or admin | body: `content`, `level` | `id` |
| GET | `/api/board/removed` | Member |  | `posts` |
| GET | `/api/subgroups` | Member |  | `village` |
| POST | `/api/subgroups` | Admin | body: `admin_label`, `description`, `name` | `id` |
| POST | `/api/subgroups/<int:sg_id>/join` | Member |  | `status` |
| POST | `/api/subgroups/<int:sg_id>/decide` | Admin | body: `approve`, `user_id` | `status` |
| GET/POST | `/api/chat/<int:sg_id>` | Member |  | `status` |
| POST | `/api/reactions/<scope>/<int:message_id>` | Member | body: `reaction` | `status` |

### People, personal groups, chats and referrals

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| POST | `/api/referrer/apply` | Member |  | `status` |
| GET | `/api/referrer/me` | Member |  | `code`, `pending` |
| GET | `/api/referrer/applications` | Admin |  | `applications` |
| POST | `/api/referrer/applications/<int:app_id>/decide` | Admin |  | `status`, `code` |
| GET | `/api/people/search` | Member | query: `q` | (built by a helper) |
| POST | `/api/people/account-ids/switch` | Member |  | `status` |
| POST | `/api/people/account-ids/request` | Member |  | `status` |
| GET | `/api/people/me` | Member |  | `search_code`, `account_history`, `account_requests` |
| GET | `/api/people/groups` | Member |  | (built by a helper) |
| POST | `/api/people/groups/create` | Member | body: `category`, `name` | `id` |
| POST | `/api/people/groups/<int:group_id>/move` | Member | body: `category` | `status` |
| POST | `/api/people/groups/<int:group_id>/business` | Member | body: `name`, `sector`, `services` | `status` |
| GET/POST | `/api/people/groups/<int:group_id>/rate` | Member | body: `comment`, `stars` | `ratings` |
| POST | `/api/people/groups/<int:group_id>/rename` | Member |  | `status` |
| GET/POST | `/api/people/groups/<int:group_id>/messages` | Member |  | `status` |
| POST | `/api/people/invite` | Member | body: `group_id`, `user_id` | `status` |
| POST | `/api/people/message` | Member | body: `text`, `user_id` | `status` |
| GET | `/api/people/inbox` | Member |  | `requests` |
| POST | `/api/people/inbox/<int:request_id>/decide` | Member |  | (built by a helper) |
| GET | `/api/people/chats` | Member |  | `chats` |
| GET/POST | `/api/people/chats/<int:chat_id>` | Member |  | `status` |
| POST | `/api/people/chats/<int:chat_id>/rename` | Member |  | `status` |
| POST | `/api/people/chats/<int:chat_id>/leave` | Member |  | `status` |
| POST | `/api/people/chats/<int:chat_id>/request-rejoin` | Member |  | `status` |

### Qmail

Added 18 October 2026. Internal messaging between members only: `@qumanity.in` is an addressing convention, and no route sends or receives internet email. A member address is `<username>-<account_id>@qumanity.in`; a council address is `<level>-<location_id>@qumanity.in`, and only village council addresses can receive messages. Full design: `docs/QMAIL.md`.

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| POST | `/api/qmail/activate` | Member | body: `username` (8–15 characters: letters, numbers, `.`, `_`, `-`) | `address` |
| GET | `/api/qmail/status` | Member |  | `activated`, `address`, `changed` |
| POST | `/api/qmail/compose` | Member who has activated Qmail | body: `to`, `subject`, `body`, optional `draft_id`. As multipart form data, also an optional `attachment` file: at most 2 MB, and only png, jpg, jpeg, gif, webp, pdf, txt, csv, doc, docx, xls, xlsx, ppt, pptx or zip, with a declared type that matches the extension (400 otherwise, 413 if too large). `to` is resolved on the server; an unknown address, or a council address that cannot yet receive, returns 404 | `status` |
| GET | `/api/qmail/inbox` | Member |  | `messages` (each with an `attachments` list of metadata) |
| GET | `/api/qmail/sent` | Member |  | `messages` (to members, plus this member's own messages to council addresses); each has `kind`, `member` or `council`, because the two kinds' ids come from different tables |
| GET | `/api/qmail/sent/council/<int:message_id>` | Member (the message's sender only; anyone else, a council head or the Admin included, gets 404) |  | `id`, `subject`, `body`, `created_at`, `to_name`, `to_address`, `attachments`, `replies` (each only `message` and `created_at`). Never the action log or who replied. Marks the reply notification read. Added in c09b91f |
| POST | `/api/qmail/messages/<int:message_id>/read` | Member (the recipient only) |  | `status` |
| GET | `/api/qmail/attachments/<int:attachment_id>` | Member: the sender or recipient, or for a council message its sender or Admin Panel scope for that village. Anyone else gets 404 |  | The file, always as a download (`Content-Disposition: attachment`) with `X-Content-Type-Options: nosniff` |
| GET | `/api/qmail/resolve-username` | Member | query: `q` | `matches` (only members the caller is connected to through groups or chats) |
| GET | `/api/qmail/resolve-public-id` | Member | query: `code` (a 12-digit Public ID) | `activated`, `name`, `address` |
| GET | `/api/qmail/drafts` | Member |  | `drafts` (the caller's own) |
| POST | `/api/qmail/drafts` | Member | body: `to`, `subject`, `body` (at least one) | `id` |
| POST | `/api/qmail/drafts/<int:draft_id>` | Member (the draft's owner; anyone else gets 404) | body: `to`, `subject`, `body` | `id` |
| POST | `/api/qmail/drafts/<int:draft_id>/delete` | Member (the draft's owner; anyone else gets 404) |  | `status` |

### Elections, Q-Punch and perception

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| POST | `/api/qpunch/volunteer` | Member |  | `status` |
| GET | `/api/qpunch/<level>` | Member |  | `level`, `label`, `group`, `group_id`, `residents`, `election_min`, `qpunch_address` (the council address with `address`, `reachable` and `seat_filled`, or null if the location has none yet) |
| GET/POST | `/api/election-history` | Member |  | `status`, `party`, `qpunch` |
| GET | `/api/election-sentiment/<level>/<path:location_id>` | Public |  | `visible`, `level`, `reason` |
| GET | `/api/election/status` | Member |  | `cycle`, `zodiac_sign`, `element`, `year`, `status` |
| GET | `/api/election/candidates` | Member |  | `restricted`, `your_sign`, `cycle_sign`, `male`, `female` |
| POST | `/api/election/nominate` | Member | body: `changes`, `past_work`, `reason`, `why_vote` | `status` |
| POST | `/api/election/vote` | Member | body: `candidate_user_id`, `gender` | `status` |
| GET | `/api/election/summary` | Member |  | (built by a helper) |
| GET | `/api/election/council` | Public |  | `village_id`, `council` |
| GET | `/api/perception/country/<country_id>` | Public |  | (built by a helper) |
| POST | `/api/perception/country/<country_id>/vote` | Member | body: `vote` | (built by a helper) |
| GET | `/api/perception/zone/<path:zone_id>` | Public |  | (built by a helper) |
| POST | `/api/perception/zone/<path:zone_id>/vote` | Member | body: `vote` | (built by a helper) |

### Citizen Reports, announcements and notifications

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| POST | `/api/announcements` | Council or admin | body: `body`, `image_url`, `location_id`, `location_level`, `title` | `id`, `created_at` |
| GET | `/api/announcements/<level>/<path:location_id>` | Member | query: `limit` | `announcements` |
| POST | `/api/announcements/<int:ann_id>/read` | Member |  | `ok` |
| GET | `/api/announcements/unread-count` | Member |  | `total` |
| GET | `/api/announcements/unread-recent` | Member | query: `limit` | `announcements` |
| POST | `/api/reports` | Member | body: `anonymous`, `body` | (built by a helper) |
| GET | `/api/reports/mine` | Member |  | `reports` |
| GET | `/api/reports/inbox` | Council or admin | query: `location_id`, `location_level` | `reports` |
| GET | `/api/reports/<int:report_id>` | Council or admin |  | (built by a helper) |
| POST | `/api/reports/<int:report_id>/update` | Council or admin | body: `message`, `new_deadline`, `update_type` | `ok` |
| POST | `/api/reports/<int:report_id>/escalate` | Council or admin |  | `current_holder_level`, `current_holder_id` |
| GET | `/api/notifications/summary` | Member |  | (built by a helper) |
| POST | `/api/notifications/mark-read` | Member | body: `id`, `kind` | `status` |
| GET | `/api/queries/mine/<int:query_id>` | Member (the member who asked only; anyone else gets 404) |  | `id`, `category`, `subject`, `body`, `created_at`, `replies` (each only `message` and `created_at`). Never who replied. Marks the reply notification read. Added in c09b91f |

### Homepage content and reviews

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| GET | `/api/founder-message` | Public | query: `lang` | (built by a helper) |
| GET | `/api/user/review-status` | Member |  | `cycle_id`, `reviewed` |
| POST | `/api/user/review` | Member | body: `rating`, `review` | `status`, `cycle_id` |
| POST | `/api/reviews` | Member | body: `allow_public`, `client`, `decline`, `rating`, `text` | `status` |
| GET | `/api/reviews/public` | Public |  | (built by a helper) |
| GET | `/api/poems/meta` | Public |  | (built by a helper) |
| GET | `/api/poems/<lang>/<int:index>` | Public |  | `index`, `id`, `marker`, `text` |

### Administration

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| GET | `/api/admin/logout-reviews` | Admin | query: `cycle_id` | (built by a helper) |
| GET | `/api/admin/account-ids` | Admin |  | `requests` |
| POST | `/api/admin/account-ids/<int:request_id>/decide` | Admin |  | `status` |
| GET | `/api/admin/recover-id` | Admin | query: `status` | `requests` |
| POST | `/api/admin/recover-id/<int:request_id>/decide` | Admin | body: `admin_note`, `status` | `status` |
| POST | `/api/admin/recover-id/<int:request_id>/reveal` | Admin |  | `private_code` |
| GET | `/api/admin/reviews` | Admin |  | `reviews` |
| POST | `/api/admin/reviews/<int:review_id>/approve` | Admin |  | `status` |
| GET | `/api/admin/profile-changes` | Admin |  | `requests` |
| POST | `/api/admin/profile-changes/<int:request_id>/decide` | Admin |  | `status` |
| POST | `/api/admin/election/auto-nominate` | Admin |  | `picked` |
| POST | `/api/admin/election/auto-vote` | Admin |  | `cast` |
| POST | `/api/admin/election/nominate/<int:candidate_id>/approve` | Admin |  | `status` |
| POST | `/api/admin/election/nominate/<int:candidate_id>/reject` | Admin |  | `status` |
| GET | `/api/admin/visibility` | Admin |  | (built by a helper) |
| POST | `/api/admin/visibility/<key>` | Admin | body: `display_until`, `enabled` | (built by a helper) |
| GET | `/api/admin/election-cycle` | Admin |  | `countries` |
| POST | `/api/admin/election-cycle/<country_code>` | Admin | body: `interval_years`, `last_election_year` | `status`, `years` |

Admin member export (added 18 October 2026). The one export that contains personal data; every successful call writes a row to `admin_export_log` (Document 07, 7.3).

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| GET | `/api/admin/users/export` | Admin | query: `level`, `location_id` (required unless `level` is `earth`), `period` (`24h`, `7d`, `30d`, `ytd` or `all`) | `members` (each with `id`, `private_id`, `account_id`, `name`, `location`, `created_at`), `count` |
| GET | `/api/admin/users/export.csv` | Admin | as above | CSV download with the same columns |

Admin Panel (added 18 October 2026). One review list over Citizen Reports, ID-recovery requests, member queries and the council queue. The administrator sees all four for every location; a serving village council head sees only their own village's council queue. Full design: `docs/ADMIN_PANEL.md`.

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| GET | `/api/admin/panel/feed` | Admin Panel scope |  | `items` |
| GET | `/api/admin/panel/council/<int:message_id>` | Admin Panel scope (that message's village only) |  | the message, with `actions` and `attachments`. Reading a message writes a 'viewed' row to `qpunch_queue_actions` before the response is returned, so a council head cannot read a resident's message without the read being recorded |
| POST | `/api/admin/panel/council/<int:message_id>/reply` | Admin Panel scope (that message's village only) | body: `message` | `status` |
| POST | `/api/admin/panel/council/<int:message_id>/close` | Admin Panel scope (that message's village only) |  | `status` |
| GET | `/api/admin/queries/<int:query_id>` | Admin |  | `id`, `category`, `subject`, `body`, `status`, `replies` |
| POST | `/api/admin/queries/<int:query_id>/reply` | Admin | body: `message` | `status` |
| POST | `/api/admin/queries/<int:query_id>/close` | Admin |  | `status` |

No route lets a member submit a query yet (Document 10, row 36).

### Administration: lunar cycle, pipeline and archive

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| GET | `/api/admin/lunar/cycle-state` | Admin |  | (built by a helper) |
| POST | `/api/admin/lunar/cycle-state/transition` | Admin | body: `cycle_id` | (built by a helper) |
| GET | `/api/admin/lunar/cycle-state/status` | Admin |  | `active`, `live_calendar_cycle_id`, `in_sync` |
| POST | `/api/admin/pipeline/transfer` | Admin | body: `cycle_id`, `from_level` | (built by a helper) |
| POST | `/api/admin/pipeline/run-all` | Admin | body: `cycle_id` | `cycle_id`, `transfers` |
| GET | `/api/admin/pipeline/status` | Admin |  | `pipeline_state`, `recent_transfers` |
| GET | `/api/admin/pipeline/holdings/<level>/<path:level_id>` | Admin |  | `level`, `level_id`, `holdings` |
| GET | `/api/admin/pipeline/eligible-cycles` | Admin |  | `eligible_cycles` |
| POST | `/api/admin/pipeline/archive` | Admin | body: `cycle_id`, `dry_run` | (built by a helper) |
| GET | `/api/admin/pipeline/archive-status/<cycle_id>` | Admin |  | (built by a helper) |
| POST | `/api/admin/pipeline/bootstrap/activate` | Admin |  | (built by a helper) |
| POST | `/api/admin/pipeline/bootstrap/reset` | Admin | body: `confirm` | `confirm` |
| POST | `/api/admin/pipeline/tick` | Admin | body: `simulate_date` | (built by a helper) |
| GET | `/api/admin/pipeline/health` | Admin |  | (built by a helper) |
| POST | `/api/admin/sync-folders` | Admin |  | (built by a helper) |

### Administration: Post Testing cycle

| Method | Path | Access | Parameters | Response fields |
|---|---|---|---|---|
| GET | `/api/admin/test-cycle/panel` | Admin |  | `window`, `posts_this_month`, `votes_this_month` |
| POST | `/api/admin/test-cycle/start` | Admin | body: `demo_user_count`, `vote_distribution` | (the new window row) |
| POST | `/api/admin/test-cycle/renew` | Admin |  | (the updated window row) |
| POST | `/api/admin/test-cycle/stop` | Admin |  | (the updated window row) |
