-- Phase 3 (pipeline engine): adds a pipeline_level column (+ 2 indexes) to the same 28 activity
-- tables Phase 2 added cycle_id to -- see docs/phase_3_report.md. Tracks how far a row's
-- archival position has progressed up the lunar-cycle pipeline; it is NOT the same axis as
-- board_posts.level (Collective Board voting-elevation) or collective_karma_log's own
-- location_level -- a row can independently be "elevated to Tehsil" by voting while its
-- pipeline_level is still 'village' (the lunar pipeline hasn't reached it yet).
--
-- Deviation from the literal spec (documented in docs/phase_3_report.md): country_sentiment and
-- zone_sentiment default to 'country'/'zone' respectively, not 'village' -- per Decision 3, a
-- sentiment vote is cast directly ABOUT a country/zone and was never "at village" in the first
-- place; defaulting it to 'village' would be a silent correctness bug in every later aggregate.
-- SQLite's ALTER TABLE ADD COLUMN ... DEFAULT backfills existing rows with that value at ALTER
-- time, so no separate Python backfill pass is needed for this column (unlike Phase 2's cycle_id).

ALTER TABLE wallet_transactions ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_pipeline_level ON wallet_transactions(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_cycle_pipeline ON wallet_transactions(cycle_id, pipeline_level);

ALTER TABLE election_candidates ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_election_candidates_pipeline_level ON election_candidates(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_election_candidates_cycle_pipeline ON election_candidates(cycle_id, pipeline_level);

ALTER TABLE election_votes ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_election_votes_pipeline_level ON election_votes(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_election_votes_cycle_pipeline ON election_votes(cycle_id, pipeline_level);

ALTER TABLE karma_entries ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_karma_entries_pipeline_level ON karma_entries(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_karma_entries_cycle_pipeline ON karma_entries(cycle_id, pipeline_level);

ALTER TABLE collective_karma_log ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_collective_karma_log_pipeline_level ON collective_karma_log(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_collective_karma_log_cycle_pipeline ON collective_karma_log(cycle_id, pipeline_level);

ALTER TABLE business_ratings ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_business_ratings_pipeline_level ON business_ratings(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_business_ratings_cycle_pipeline ON business_ratings(cycle_id, pipeline_level);

ALTER TABLE board_posts ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_board_posts_pipeline_level ON board_posts(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_board_posts_cycle_pipeline ON board_posts(cycle_id, pipeline_level);

ALTER TABLE board_votes ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_board_votes_pipeline_level ON board_votes(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_board_votes_cycle_pipeline ON board_votes(cycle_id, pipeline_level);

ALTER TABLE board_comments ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_board_comments_pipeline_level ON board_comments(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_board_comments_cycle_pipeline ON board_comments(cycle_id, pipeline_level);

ALTER TABLE board_messages ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_board_messages_pipeline_level ON board_messages(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_board_messages_cycle_pipeline ON board_messages(cycle_id, pipeline_level);

ALTER TABLE personal_messages ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_personal_messages_pipeline_level ON personal_messages(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_personal_messages_cycle_pipeline ON personal_messages(cycle_id, pipeline_level);

ALTER TABLE private_messages ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_private_messages_pipeline_level ON private_messages(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_private_messages_cycle_pipeline ON private_messages(cycle_id, pipeline_level);

ALTER TABLE account_ids ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_account_ids_pipeline_level ON account_ids(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_account_ids_cycle_pipeline ON account_ids(cycle_id, pipeline_level);

ALTER TABLE people_requests ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_people_requests_pipeline_level ON people_requests(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_people_requests_cycle_pipeline ON people_requests(cycle_id, pipeline_level);

ALTER TABLE account_id_requests ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_account_id_requests_pipeline_level ON account_id_requests(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_account_id_requests_cycle_pipeline ON account_id_requests(cycle_id, pipeline_level);

ALTER TABLE country_sentiment ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'country';
CREATE INDEX IF NOT EXISTS idx_country_sentiment_pipeline_level ON country_sentiment(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_country_sentiment_cycle_pipeline ON country_sentiment(cycle_id, pipeline_level);

ALTER TABLE zone_sentiment ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'zone';
CREATE INDEX IF NOT EXISTS idx_zone_sentiment_pipeline_level ON zone_sentiment(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_zone_sentiment_cycle_pipeline ON zone_sentiment(cycle_id, pipeline_level);

ALTER TABLE app_reviews ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_app_reviews_pipeline_level ON app_reviews(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_app_reviews_cycle_pipeline ON app_reviews(cycle_id, pipeline_level);

ALTER TABLE profile_change_requests ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_profile_change_requests_pipeline_level ON profile_change_requests(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_profile_change_requests_cycle_pipeline ON profile_change_requests(cycle_id, pipeline_level);

ALTER TABLE volunteers ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_volunteers_pipeline_level ON volunteers(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_volunteers_cycle_pipeline ON volunteers(cycle_id, pipeline_level);

ALTER TABLE message_reactions ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_message_reactions_pipeline_level ON message_reactions(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_message_reactions_cycle_pipeline ON message_reactions(cycle_id, pipeline_level);

ALTER TABLE referrer_applications ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_referrer_applications_pipeline_level ON referrer_applications(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_referrer_applications_cycle_pipeline ON referrer_applications(cycle_id, pipeline_level);

ALTER TABLE subgroups ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_subgroups_pipeline_level ON subgroups(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_subgroups_cycle_pipeline ON subgroups(cycle_id, pipeline_level);

ALTER TABLE personal_groups ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_personal_groups_pipeline_level ON personal_groups(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_personal_groups_cycle_pipeline ON personal_groups(cycle_id, pipeline_level);

ALTER TABLE private_chats ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_private_chats_pipeline_level ON private_chats(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_private_chats_cycle_pipeline ON private_chats(cycle_id, pipeline_level);

ALTER TABLE subgroup_members ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_subgroup_members_pipeline_level ON subgroup_members(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_subgroup_members_cycle_pipeline ON subgroup_members(cycle_id, pipeline_level);

ALTER TABLE personal_group_members ADD COLUMN pipeline_level VARCHAR(20) NOT NULL DEFAULT 'village';
CREATE INDEX IF NOT EXISTS idx_personal_group_members_pipeline_level ON personal_group_members(pipeline_level);
CREATE INDEX IF NOT EXISTS idx_personal_group_members_cycle_pipeline ON personal_group_members(cycle_id, pipeline_level);
