-- Phase 2: adds a cycle_id column (+ index) to every table classified as "ongoing activity" --
-- see docs/phase_2_report.md for the full table-by-table include/exclude rationale (23 tables
-- from the Founder's own named examples + exclusions, plus the group/container cluster the
-- Founder asked to include on review: subgroups, personal_groups, private_chats,
-- subgroup_members, personal_group_members -- 28 tables total).
--
-- Additive only: no column is dropped, no row is touched here (migration 003 backfills values).
-- tools/run_migrations.py applies this statement-by-statement and treats "duplicate column name"
-- as success, so this file is safe to re-run.

ALTER TABLE wallet_transactions ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_cycle ON wallet_transactions(cycle_id);

ALTER TABLE election_candidates ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_election_candidates_cycle ON election_candidates(cycle_id);

ALTER TABLE election_votes ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_election_votes_cycle ON election_votes(cycle_id);

ALTER TABLE karma_entries ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_karma_entries_cycle ON karma_entries(cycle_id);

ALTER TABLE collective_karma_log ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_collective_karma_log_cycle ON collective_karma_log(cycle_id);

ALTER TABLE business_ratings ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_business_ratings_cycle ON business_ratings(cycle_id);

ALTER TABLE board_posts ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_board_posts_cycle ON board_posts(cycle_id);

ALTER TABLE board_votes ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_board_votes_cycle ON board_votes(cycle_id);

ALTER TABLE board_comments ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_board_comments_cycle ON board_comments(cycle_id);

ALTER TABLE board_messages ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_board_messages_cycle ON board_messages(cycle_id);

ALTER TABLE personal_messages ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_personal_messages_cycle ON personal_messages(cycle_id);

ALTER TABLE private_messages ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_private_messages_cycle ON private_messages(cycle_id);

ALTER TABLE account_ids ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_account_ids_cycle ON account_ids(cycle_id);

ALTER TABLE people_requests ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_people_requests_cycle ON people_requests(cycle_id);

ALTER TABLE account_id_requests ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_account_id_requests_cycle ON account_id_requests(cycle_id);

ALTER TABLE country_sentiment ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_country_sentiment_cycle ON country_sentiment(cycle_id);

ALTER TABLE zone_sentiment ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_zone_sentiment_cycle ON zone_sentiment(cycle_id);

ALTER TABLE app_reviews ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_app_reviews_cycle ON app_reviews(cycle_id);

ALTER TABLE profile_change_requests ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_profile_change_requests_cycle ON profile_change_requests(cycle_id);

ALTER TABLE volunteers ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_volunteers_cycle ON volunteers(cycle_id);

ALTER TABLE message_reactions ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_message_reactions_cycle ON message_reactions(cycle_id);

ALTER TABLE referrer_applications ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_referrer_applications_cycle ON referrer_applications(cycle_id);

ALTER TABLE subgroups ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_subgroups_cycle ON subgroups(cycle_id);

ALTER TABLE personal_groups ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_personal_groups_cycle ON personal_groups(cycle_id);

ALTER TABLE private_chats ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_private_chats_cycle ON private_chats(cycle_id);

ALTER TABLE subgroup_members ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_subgroup_members_cycle ON subgroup_members(cycle_id);

ALTER TABLE personal_group_members ADD COLUMN cycle_id VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_personal_group_members_cycle ON personal_group_members(cycle_id);
