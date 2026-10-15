# Qumanity data model

Qumanity stores everything in one SQLite database (path set by `QM_DB_PATH`). The SQL is plain enough to move to PostgreSQL later.

## How the schema is built

There is no manual migration step. On every start, `ensure_database_ready()` in `app.py` does the following, and every step is idempotent (`CREATE TABLE IF NOT EXISTS`, or a migration recorded in the `migrations` table):
1. Applies `db/schema.sql`, the base tables for members, zodiac, locations, wallets and elections.
2. Seeds the zodiac reference data.
3. Creates each `*_core.py` module's own tables.
4. Runs the files in `migrations/` (001–003 and 007–014; numbers 004–006 are unused) through `tools/run_migrations.py`.
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

Most activity tables carry `cycle_id` (the lunar cycle the row was written in) and `pipeline_level` (how far up the Village-to-Earth pipeline it has moved).

## Tables

64 application tables, listed from the local development database on 11 October 2026. PK is the primary key and FK a declared foreign key. Many user references (`user_id`, `author_id` and so on) point to `users.id` by convention without a declared FK.

### Identity and sign-in

| Table | PK | Key references | Holds |
|---|---|---|---|
| `users` | `id` | | Member: name, gender, birth date and time, birth and present location (JSON), languages, Private ID, PIN hash, optional email and phone, profile fields, referrer, `hide_identity` |
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
| `location_elements` | `id` | `location_id` | Element counts per location |

### Location

| Table | PK | Key references | Holds |
|---|---|---|---|
| `india_villages` | `id` | `tehsil_id` | Village names per tehsil. Continents to tehsils come from JSON files and `Qumanity_Master.json` |

### Collective Boards and village groups

| Table | PK | Key references | Holds |
|---|---|---|---|
| `board_posts` | `id` | `author_id`, `origin_post_id`, `elevated_to` | Posts, score, voting window, status (active, elevated, frozen, removed) |
| `board_votes` | `post_id, user_id` | | One vote per member per post |
| `board_comments` | `id` | `post_id`, `user_id` | Comments |
| `subgroups` | `id` | `village_id`, `created_by` | Village societies or RWAs |
| `subgroup_members` | `subgroup_id, user_id` | | Membership and join status |
| `board_messages` | `id` | `subgroup_id`, `user_id` | Sub-group chat |
| `volunteers` | `user_id, level, group_id, kind` | | Q-Punch volunteers and agents |

### Personal social

| Table | PK | Key references | Holds |
|---|---|---|---|
| `personal_groups` | `id` | `owner_user_id` | Family, Friends, Business and Custom groups |
| `personal_group_members` | `group_id, user_id` | | Members and invite status |
| `personal_messages` | `id` | `group_id`, `user_id` | Group messages |
| `private_chats` | `id` | `user_lo`, `user_hi` | One-to-one chats |
| `private_messages` | `id` | `chat_id`, `user_id` | Chat messages |
| `people_requests` | `id` | `from_user_id`, `to_user_id` | Friend, group and message requests |
| `chat_read_state` | `user_id, kind, chat_id` | | Last-read markers |

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
| `election_cycle_config` | `country_code, kind` | | National election years |
| `election_history` | `user_id` | | Member's optional past-vote record (legacy layout) |
| `election_history_entries` | `user_id, kind, slot` | | Same, current layout |

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
