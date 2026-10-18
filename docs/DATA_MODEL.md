# Qumanity data model

Qumanity stores everything in one SQLite database (path set by `QM_DB_PATH`). The SQL is plain enough to move to PostgreSQL later.

## How the schema is built

There is no manual migration step. On every start, `ensure_database_ready()` in `app.py` does the following, and every step is idempotent (`CREATE TABLE IF NOT EXISTS`, or a migration recorded in the `migrations` table):
1. Applies `db/schema.sql`, the base tables for members, zodiac, locations, wallets and elections.
2. Seeds the zodiac reference data.
3. Creates each `*_core.py` module's own tables.
4. Runs the files in `migrations/` (001–003, 007–024; numbers 004–006 are unused) through `tools/run_migrations.py`.
5. Adds late columns to `users` (`_ensure_user_columns`).

| Migration | Change |
|---|---|
| 001 | `cycle_state` |
| 002, 003 | `cycle_id` column on activity tables, and backfill |
| 007 | `pipeline_level` column |
| 008–011 | `level_holdings`, `transfer_log`, `pipeline_state`, `pipeline_bootstrap` |
| 012 | Announcements |
| 013 | Citizen Reports |
| 014 | Drops `payment_orders` if empty (Razorpay removed) |
| 015 | `qoins` (physical denominated Qoins), `recognition_stars` |
| 016 | `users.is_demo`, `users.is_removed` |
| 017 | `board_posts.post_kind`/`is_test`/`is_demo_post`/`test_reward_inr`, `board_votes.voted_at`, `testing_windows` |
| 018 | `location_elements.birth_users` |
| 019 | `admin_export_log` |
| 020 | `admin_queries`, `admin_query_replies` |
| 021 | `users.qmail_username`, `qmail_addresses`, `qmail_messages` |
| 022 | `qpunch_addresses`, `qpunch_queue_messages`, `qpunch_queue_actions` |
| 023 | `qmail_attachments` |
| 024 | `qmail_drafts` |

Most activity tables carry `cycle_id` (the lunar cycle the row was written in) and `pipeline_level` (how far up the Village-to-Earth pipeline it has moved).

## Tables

76 application tables in a running database: 74 created on boot, and 2 that their module creates the first time it is used (`chat_read_state` and `election_cycle_config`). SQLite's internal `sqlite_sequence` is not counted. The list was first taken from the local development database on 11 October 2026, updated 17 October 2026, and checked on 18 October 2026 against a fresh database built from commit f1edd55. PK is the primary key and FK a declared foreign key. Many user references (`user_id`, `author_id` and so on) point to `users.id` by convention without a declared FK.

*Corrected 18 October 2026: this line previously said 67 application tables. A fresh database built from commit c641f2c has 64 tables on boot. The 67 also counted the 2 tables created on first use and a legacy `election_history` table that no current code creates; that table is now removed from the list (see Elections and councils). Migrations 019–024 (18 October 2026) added the 10 tables in the Qmail, Council addresses and queue, and Admin Panel and export sections, which gives 74 on boot and 76 in a running database.*

The entries in the three sections added on 18 October 2026 also say who can read each table, because Document 07 (7.3) describes their access rules and this file must agree with it. The older entries do not have that column; their access rules are in Document 07.

### Identity and sign-in

| Table | PK | Key references | Holds |
|---|---|---|---|
| `users` | `id` | | Member: name, gender, birth date and time, birth and present location (JSON), languages, Private ID, PIN hash, optional email and phone, profile fields, referrer, `hide_identity`, `is_demo`, `is_removed`, `qmail_username` (optional, unique, 8–15 characters, chosen once when the member activates Qmail) |
| `account_ids` | `id` | `user_id` | Account IDs and search codes per location |
| `user_onboarding` | `user_id` | | App tour and review prompt status |
| `otp_requests` | `id` | `user_id` | One-time codes for PIN reset (hashed) |
| `id_recovery_requests` | `id` | `candidate_user_id` | Forgotten-ID requests for admin review |
| `id_recovery_reveals` | (none) | `request_id` | Audit of when an ID was revealed |
| `profile_change_requests` | `id` | `user_id` | Requested changes to locked profile fields |

### Astrology

| Table | PK | Key references | Holds |
|---|---|---|---|
| `zodiac_signs` | `id` | | Reference: the 12 signs |
| `nakshatras` | `id` | FK `zodiac_id` → `zodiac_signs` | Reference: the 27 nakshatras |
| `user_zodiac` | `id` | FK `user_id` → `users` | Member's sun and moon sign, nakshatra, ascendant, birth chart |
| `user_elemental_profile` | `id` | FK `user_id` → `users` | Member's elemental balance |
| `location_elements` | `id` | `location_id` | Element counts per location. `total_users` is PRESENT-location real members only (`is_demo=0, is_removed=0`) — this is the membership count. `birth_users` is separate, metadata-only: real users born here, never counted toward `total_users`, never driving membership or voting (see `docs/member_count_design.md`). |

### Location

| Table | PK | Key references | Holds |
|---|---|---|---|
| `india_villages` | `id` | `tehsil_id` | Village names per tehsil. Continents to tehsils come from JSON files and `Qumanity_Master.json` |

### Collective Boards and village groups

| Table | PK | Key references | Holds |
|---|---|---|---|
| `board_posts` | `id` | `author_id`, `origin_post_id`, `elevated_to` | Posts, score, voting window, status (active, elevated, frozen, removed), `post_kind` (member, test, council_update), `is_test`, `is_demo_post`, `test_reward_inr` (a test post's computed-but-never-credited reward) |
| `board_votes` | `post_id, user_id` | | One vote per member per post, `voted_at` |
| `board_comments` | `id` | `post_id`, `user_id` | Comments |
| `subgroups` | `id` | `village_id`, `created_by` | Village societies or RWAs |
| `subgroup_members` | `subgroup_id, user_id` | | Membership and join status |
| `board_messages` | `id` | `subgroup_id`, `user_id` | Sub-group chat |
| `volunteers` | `user_id, level, group_id, kind` | | Q-Punch volunteers and agents |
| `testing_windows` | `id` | | Feature-scoped testing windows (`feature`, start/end date, status, demo user count, vote distribution JSON) — `post_testing` is the only feature using this table so far |

### Personal social

| Table | PK | Key references | Holds |
|---|---|---|---|
| `personal_groups` | `id` | `owner_user_id` | Family, Friends, Business and Custom groups |
| `personal_group_members` | `group_id, user_id` | | Members and invite status |
| `personal_messages` | `id` | `group_id`, `user_id` | Group messages |
| `private_chats` | `id` | `user_lo`, `user_hi` | One-to-one chats |
| `private_messages` | `id` | `chat_id`, `user_id` | Chat messages |
| `people_requests` | `id` | `from_user_id`, `to_user_id` | Friend, group and message requests |
| `chat_read_state` | `user_id, kind, chat_id` | | Last-read markers. `kind` is `private`, `group`, `query` (a reply to a member query) or `council` (a reply to a message sent to a council address). Created on first use by `notify_core.py` |

### Qmail

Qmail is internal messaging between members. Nothing in these tables is sent to or received from internet mail. A member must activate Qmail (choose a `users.qmail_username`) before they can send or receive.

| Table | PK | Key references | Holds | Who can read it |
|---|---|---|---|---|
| `qmail_addresses` | `id` | `user_id`; `full_address` is unique | One row per Account ID a Qmail member has had: `account_id`, `full_address` (`<qmail_username>-<account_id>@qumanity.in`), `is_current`, `created_at`, `forward_until`. When the Account ID changes (`social_core.regenerate_account_id`), the current row gets `is_current = 0` and `forward_until` 30 days ahead, and a new current row is added. An old address delivers until `forward_until`, then stops resolving. Rows are never deleted | The owner sees their current address, and an old one while it still forwards (`/api/qmail/status`). Any signed-in member who enters the owner's 12-digit Public ID gets the current address with the owner's name (`/api/qmail/resolve-public-id`). Members connected to the owner (shared groups or chats) get it suggested by username (`/api/qmail/resolve-username`; demo and removed accounts excluded). The other party to a message sees the address in their inbox or sent list. No route shows anyone else a member's past addresses. The address contains the Account ID and so the attributes it encodes (Document 07, 7.3) |
| `qmail_messages` | `id` | `from_user_id`, `to_user_id` | One member-to-member message: `subject`, `body`, `created_at`, `read_at`. The body is plain text with three markup forms (`**bold**`, `_italic_`, `[text](url)`), never HTML. The recipient is resolved on the server from the To address at send time | The sender (`/api/qmail/sent`) and the recipient (`/api/qmail/inbox`). Only the recipient can set `read_at`. No route gives the Admin or a council access. There is no route to delete a message |
| `qmail_attachments` | `id` | `kind` and `message_id` together: `member` → `qmail_messages.id`, `council` → `qpunch_queue_messages.id`. Not a declared FK, because it points at two tables; every query filters on both columns | At most one file per message, added at compose time: `uploader_user_id`, `filename`, `content_type` (the canonical type for the file's extension, from a 15-type allowlist in `qmail_core.ALLOWED_ATTACHMENT_TYPES`), `byte_size`, `data` (the file itself as a BLOB, 2 MB at most), `created_at`. Replies and drafts never carry one | For a member message: its sender and recipient. For a council message: its sender, that village's serving council heads, and the Admin. Anyone else gets the same 404 as for a missing file. The file is only ever served as a download, with `X-Content-Type-Options: nosniff` (`/api/qmail/attachments/<id>`); the message lists show only its id, name, type and size |
| `qmail_drafts` | `id` | `user_id` | An unsent message: `to_address` (whatever the To field held, not validated until send), `subject`, `body`, `updated_at`. No attachment | Only the member who wrote it. Every list, update and delete is filtered by the signed-in member's id, so another member's draft id returns 404. Deleted when the member deletes it or sends it (in the same transaction as the send). There is no automatic cleanup |

### Reactions and ratings

| Table | PK | Key references | Holds |
|---|---|---|---|
| `message_reactions` | `scope, message_id, user_id` | | Agree, Disagree or Read |
| `business_ratings` | `id` | `group_id`, `rater_user_id`, `provider_user_id` | Star ratings of local businesses |
| `app_reviews` | `id` | `user_id` | One-time app rating; public only if approved |
| `user_reviews` | `id` | `user_id`, `cycle_id` | Optional logout rating, once per lunar cycle |

### Karma

| Table | PK | Key references | Holds |
|---|---|---|---|
| `karma_entries` | `id` | `user_id`, `from_user_id` | Individual karma changes with reasons |
| `collective_karma` | `location_id, location_level` | | Current collective score per location |
| `collective_karma_log` | `id` | `location_id` | History of collective changes |

### Qoins

| Table | PK | Key references | Holds |
|---|---|---|---|
| `wallets` | `id` | `owner_type, owner_id` | One wallet per member and per location; Qoin balance |
| `wallet_transactions` | `id` | FK `wallet_id` → `wallets`; FK `related_user_id` → `users` | Every Qoin movement with a reason |
| `qoins` | `id` | FK `wallet_id` → `wallets` | One row per physical Qoin a wallet holds (its denomination) |
| `recognition_stars` | `id` | `post_id`, `author_id` | Permanent record of a positively-recognised board post, independent of the post's own lifecycle |

### Referrals

| Table | PK | Key references | Holds |
|---|---|---|---|
| `referrers` | `user_id` | `approved_by` | Approved referrers and their code |
| `referrer_applications` | `id` | `user_id` | Applications to become a referrer |

### Elections and councils

| Table | PK | Key references | Holds |
|---|---|---|---|
| `election_cycles` | `id` | FK `male_winner_user_id`, `female_winner_user_id` → `users` | One election per village, sign and year |
| `election_candidates` | `id` | FK `election_cycle_id` → `election_cycles`; FK `user_id` → `users` | Nominations and manifestos |
| `election_votes` | `id` | FK to `election_cycles` and `users` (voter, candidate) | Votes |
| `village_council` | `village_id, zodiac_sign, year` | FK to `election_cycles` and `users` (male and female head) | Elected council pairs |
| `election_cycle_config` | `country_code, kind` | | National election years. Created on first use by `election_core.py` |
| `election_history_entries` | `user_id, kind, slot` | | Member's optional past-vote record |

*Corrected 18 October 2026: this table previously also listed `election_history` ("member's optional past-vote record, legacy layout"). No current code creates that table; it existed only in the local development database the list was first taken from. `election_history_entries` is the live table.*

### Council addresses and queue (Q-Punch)

A location gets a permanent council address once its real-member count (`location_elements.total_users`) reaches the threshold for its level: village 5, tehsil 10, district 100, state 1,000, zone 10,000, country 100,000, continent 1,000,000, Earth 10,000,000 (`qmail_core.QPUNCH_THRESHOLDS`). In the prototype only village addresses can receive messages (`qmail_core.QPUNCH_REACHABLE_LEVELS`).

| Table | PK | Key references | Holds | Who can read it |
|---|---|---|---|---|
| `qpunch_addresses` | `id` | `level, location_id` is unique; `full_address` is unique. `qpunch_queue_messages` joins on `level, location_id` | One row per location that has reached its threshold: `level`, `location_id`, `full_address` (`<level>-<location_id>@qumanity.in`), `created_at`. Created by `qmail_core.sync_qpunch_addresses`, which runs inside `elemental_core.recompute_location_elements()`; today only the manual backfill script runs that, so an address appears when the count is next recomputed, not the moment the threshold is crossed. Never deleted, even if the count later falls | Holds no personal data. A signed-in member sees the address of their own location at each level in the Q-Punch view (`/api/qpunch/<level>`). Any member who has activated Qmail and knows a village address can write to it, wherever they live. A row's existence shows that the location has reached its threshold of real members (Document 06) |
| `qpunch_queue_messages` | `id` | `sender_id`; `level, location_id` (the council written to). Access is decided by comparing `location_id` with `village_council.village_id` for the reader's current term | One message to a council address: `subject`, `body`, `status` (`open`, `answered`, `closed`), `created_at`. It belongs to the seat, not to the heads who held it when it arrived | The sender sees their own copy in `/api/qmail/sent`, and opens it with the text and time of each council reply through `/api/qmail/sent/council/<id>`, without who replied or the action log. The village's council heads serving on the day of the request see that village's messages in the Admin Panel (`/api/admin/panel/feed`, `/api/admin/panel/council/<id>`), including messages from before their term. The Admin sees every location's messages. The detail view returns the sender's internal user id. A message from another village returns 404. No route deletes a message; closing changes its status |
| `qpunch_queue_actions` | `id` | FK `message_id` → `qpunch_queue_messages`; `actor_user_id` | One row for every view, reply and close of a council message: `action` (`viewed`, `replied`, `closed`), `detail` (the reply text, for a reply), `created_at`. A view is written before the message is returned. An out-of-scope attempt writes nothing. Append-only: no route updates or deletes a row | The Admin and the serving heads of the message's village, inside the message's detail view, with each actor's name. The sender sees only the `detail` and `created_at` of the `replied` rows, through `/api/qmail/sent/council/<id>`, never the actor or the other actions. A newer `replied` row counts as an unread item for the sender (`notify_core.py`) until they open it |

### Perception

| Table | PK | Key references | Holds |
|---|---|---|---|
| `country_sentiment` | `user_id, country_id, voting_year` | | Pro or Anti vote per country per year |
| `country_sentiment_stats` | `country_id, voting_year` | | Frozen yearly totals |
| `zone_sentiment` | `user_id, zone_id, voting_year` | | Same for zones |
| `zone_sentiment_stats` | `zone_id, voting_year` | | Frozen yearly totals |

### Citizen Reports

| Table | PK | Key references | Holds |
|---|---|---|---|
| `reports` | `id` | `user_id`, `location_id` | The report, anonymity flag, current holder level, deadline |
| `report_updates` | `id` | FK `report_id` → `reports` | Council responses, extensions, escalations |

### Announcements and notices

| Table | PK | Key references | Holds |
|---|---|---|---|
| `announcements` | `id` | `location_id`, `author_user_id` | Council announcements |
| `announcement_reads` | `id` | FK `announcement_id` → `announcements` | Who has read what |
| `admin_notifications` | `id` | | System events for the administrator |
| `founder_messages` | `id` | | The Founder's Message per language |

### Admin Panel and export

| Table | PK | Key references | Holds | Who can read it |
|---|---|---|---|---|
| `admin_queries` | `id` | `user_id` (the member asking) | A member's question to the Admin with no location attached: `category` (`account`, `karma`, `wallet` or `other`), `subject`, `body`, `status` (`open`, `answered`, `closed`), `created_at`. No route creates a row yet: the member-facing route to submit a query is not wired (`admin_queries_core.create` has no caller), so the table stays empty unless rows are added outside the app | The Admin only (`/api/admin/panel/feed`, `/api/admin/queries/<id>`). A serving council head gets 403. The member who asked can open their own query by id with its replies (`/api/queries/mine/<id>`); no route lists a member's queries |
| `admin_query_replies` | `id` | FK `query_id` → `admin_queries`; `author_user_id` | The Admin's replies to a query: `message`, `created_at`. Append-only | The Admin, inside the query's detail view. The member who asked sees the `message` and `created_at` of each reply, but not who wrote it (`/api/queries/mine/<id>`). A newer reply counts as an unread item for them (`notify_core.py`) until they open it |
| `admin_export_log` | `id` | `admin_user_id` | One row for every successful Admin member export (Document 07, 7.3): `exported_at`, the filters used (`level`, `location_id`, `period`), `row_count` and `format` (`json` or `csv`). The exported data itself is not stored | No route reads it. It is visible only with direct access to the database |

### Lunar-cycle pipeline

| Table | PK | Key references | Holds |
|---|---|---|---|
| `cycle_state` | `cycle_id` | | Each lunar cycle's dates and status |
| `lunar_events` | `id` | | Eclipses and other events |
| `pipeline_bootstrap` | `id` | | Year-1 start and the date the pipeline activates |
| `pipeline_state` | `id` | | Last completed transfer |
| `level_holdings` | `id` | `level, level_id, cycle_id` | Aggregated summaries per level and cycle |
| `transfer_log` | `id` | `cycle_id` | Every transfer run |

### System

| Table | PK | Key references | Holds |
|---|---|---|---|
| `migrations` | `filename` | | Applied migrations |
| `system_settings` | `key` | | Key-value settings (for example, visibility gates) |
| `account_id_requests` | `id` | `user_id` | Requests for an additional Account ID |
