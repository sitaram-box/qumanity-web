# Qumanity: Documentation

**DPG Standard Indicator 5: Documentation**
Current owner: Rohit Mudgal (individual). Legal entity Qumanity Lok LLP is in registration. The IP will be assigned to Qumanity Lok LLP once it is registered.

## Contents

- [5.1 What the DPG Standard requires](#51-what-the-dpg-standard-requires)
- [5.2 What exists today](#52-what-exists-today)
- [5.3 What is missing for a new operator](#53-what-is-missing-for-a-new-operator)
- [5.4 Proposed additions](#54-proposed-additions)
- [5.5 Evidence for the application form](#55-evidence-for-the-application-form)

## 5.1 What the DPG Standard requires

The project must have documentation that lets a technically skilled person who is unfamiliar with it launch and run the software. Repository documentation, a setup guide and API documentation are the usual evidence.

## 5.2 What exists today

Audited in the qumanity-web repository on 11 October 2026 and re-checked on 17 October 2026: 414 tracked files, 68 of them in `docs/`.

**Repository root**

| File | Purpose | Status |
|---|---|---|
| `README.md` | 362 lines: feature tour, "Run it" (4 commands), the code layout, known simplifications, and a link to `docs/INSTALL.md` | Complete |
| `.env.example` | Every environment variable with safe placeholder values | Complete |
| `requirements.txt` | 7 Python dependencies, minimum versions only | Complete |
| `.python-version` | Python 3.12 | Complete |
| `Procfile` | Production start command (`gunicorn app:app`) | Complete |
| `migrations/` (001–003 and 007–018) and `tools/run_migrations.py` | Schema changes. `app.py` applies the full schema and runs the migrations on every boot (`ensure_database_ready`), so no manual step is needed. Explained in `docs/DATA_MODEL.md` | Complete |
| `db/schema.sql`, `db/init_db.py` | Base schema and first-run setup | Complete (see `docs/DATA_MODEL.md`) |
| `tools/verify_*.py`, `tests/` | Verification scripts for the lunar-cycle and archive systems (listed in `docs/INSTALL.md`), and unit tests for council updates and post kinds (`tests/test_council_updates.py`, `tests/test_post_kinds.py`). There is no test suite covering the whole application yet. | Partial |
| `LICENSE` | AGPL-3.0 | Complete |

**`docs/` folder, grouped**

| Files | Purpose | Status |
|---|---|---|
| `INSTALL.md` | Clone to running server: quick start, environment variables, becoming an admin, production settings, verify scripts, sample data, and where to get `Qumanity_Master.json` | Complete |
| `ENVIRONMENT.md` | Every environment variable: purpose, default, whether production needs it. Defaults are repo-relative (`QM_EARTH_ROOT=./0_Earth`) | Complete |
| `ARCHITECTURE.md`, `API.md`, `DATA_MODEL.md` | Component diagram and module map; every `/api` route with access level; every table and the migrations | Complete |
| `phone_app_api.md` | The routes the phone app calls, with sign-in and tokens | Complete for the app; `API.md` covers every route |
| `go_live_hardening_2026_10.md`, `phase_6_deployment_report.md`, `phase_2_5_fix_report.md`, `rollback_plan.md` | Railway deployment, production settings and the QM_* variables used in production, rollback steps | Partial (Railway-specific, spread over 4 files) |
| `lunar_cycle_system.md`, `phase_build_plan.md`, `phase_2_report.md` to `phase_5_report.md` | Design and build of the lunar-cycle archival system | Complete for that subsystem |
| `qoins_wallet_system.md`, `qoins_earn_reference.md`, `karma.md`, `karma_finalization_2026_10.md`, `post_rewards.md`, `post_types_pricing.md`, `transaction_history.md` | Qoins, wallets, karma, rewards and recognition stars | Complete |
| `zodiac_council_voting.md`, `ELECTION_PILOT.md`, `election_history.md`, `qpunch_council.md`, `council_structure_and_web_access_2026_10.md`, `voting_logic.md`, `perception_calculator.md` | Elections, councils and voting rules | Complete (one is marked spec only) |
| `reports_design.md`, `announcements_design.md`, `notifications.md`, `sub_groups.md`, `referral_system.md`, `personal_timeline_and_social.md`, `user_restrictions.md`, `visibility_gating_2026_10.md` | Feature design notes | Complete |
| `private_id_and_login.md`, `private_account_fixes_2026_10.md` | Identity and sign-in | Complete |
| `i18n_multilanguage_2026_10.md`, `founders_message*.md` | Languages and translations | Complete |
| `india_location_fix.md`, `location_consolidation_report.md`, `location_dedup_report.md` | Location data history | Complete (historical) |
| `DASHBOARD_REDESIGN_PLAN.md`, `homepage_redesign_plan_2026_10.md`, `scoreboard_and_tutorial_2026_10.md`, `website_ui_fixes_2026_09_28.md` | UI plans and change logs | Historical |
| `member_count_design.md` | How member counts are defined (present residence only, real members only) and refreshed | Complete |
| `test_cycle_design.md` | The Post Testing cycle: demo-account test posts and votes | Complete |
| `marquee_poems_archive/README.md` | Disabled marquee and how to re-enable it | Complete |
| `phase_6_predeploy_verification.txt` | 984 lines of raw command output | Historical; review before publishing |

**Overall:** the design of each feature is well documented, and `docs/INSTALL.md` now takes a newcomer from `git clone` to a running server. The demo login list (`DEMO_ACCOUNTS.md`) was removed from the repository, added to `.gitignore` and scrubbed from git history. The one remaining gap is the village dataset (5.3 #3). `dpg_evidence/` holds this evidence pack.

`docs/ELECTION_PILOT.md` lists 500 demo Private IDs used for local election testing. These accounts are not present in the production database; the seeding script is in the repository, and the accounts are planned for election testing, not live. The shared PIN the script would assign is documented in the script itself. No Private ID of a live account is published in the repository. The 50 board-test accounts share a PIN that is set in `scripts/seed_demo_voters.py`, but their Private IDs are not published. These are demo accounts. They contain no personal data, the testing scheduler casts their votes only on labelled test posts, and they are excluded from every public count. The platform does not otherwise restrict a signed-in demo account, so someone who also knew one of their Private IDs could post and vote as an ordinary member of the pilot village.

Two stray demo accounts (users 25 and 26) from earlier testing were retired on 17 October 2026. They are flagged `is_demo=1` and `is_removed=1`, cannot sign in, and are excluded from every count.

## 5.3 Gaps found on 11 October 2026, and their status

| # | Gap | Resolution | Status |
|---|---|---|---|
| 1 | No step-by-step install guide | `docs/INSTALL.md` | Complete |
| 2 | No environment variable reference; `QM_EARTH_ROOT` defaulted to the founder's Mac | `docs/ENVIRONMENT.md` and `.env.example`; the default is now `./0_Earth` | Complete |
| 3 | The location dataset `Qumanity_Master.json` is not in the repository | `docs/INSTALL.md` documents the file, its source (Government of India administrative and census data) and where to place it. It is to be published as a GitHub Release asset | Pending: no Release exists yet (checked 17 October 2026) |
| 4 | No database schema overview | `docs/DATA_MODEL.md` | Complete |
| 5 | No complete API reference | `docs/API.md` | Complete |
| 6 | No architecture overview | `docs/ARCHITECTURE.md` | Complete |
| 7 | No instructions for running the checks | "Verifying your setup" in `docs/INSTALL.md` | Complete |
| 8 | `docs/DEMO_ACCOUNTS.md` was tracked in git | Removed from the tree, added to `.gitignore` and scrubbed from git history. `docs/ELECTION_PILOT.md` lists 500 demo Private IDs as a plan for local election testing; those accounts are not present in production (see 5.2) | Complete |
| 9 | The founder's Private ID appeared in tracked files | Removed from every tracked file and from git history, and the live ID was rotated as a precaution. The new ID is not published | Complete |

## 5.4 Additions now in place

`docs/INSTALL.md`, `docs/ENVIRONMENT.md`, `.env.example`, `docs/ARCHITECTURE.md`, `docs/API.md` and `docs/DATA_MODEL.md` are all in the qumanity-web repository (checked 17 October 2026). The only open documentation item is publishing `Qumanity_Master.json` (5.3 #3).

## 5.5 Evidence for the application form

| Form field | Proposed answer |
|---|---|
| Documentation URL | https://github.com/sitaram-box/qumanity-web/tree/main/docs |
| Setup guide | `docs/INSTALL.md`, with `docs/ENVIRONMENT.md` and `.env.example` |
| API documentation | `docs/API.md` (every route), `docs/ARCHITECTURE.md` and `docs/DATA_MODEL.md` |
