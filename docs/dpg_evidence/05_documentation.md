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

Audited in the qumanity-web repository on 11 October 2026, re-checked on 17 October 2026, and re-checked again on 18 October 2026 at commit f1edd55: 439 tracked files, 72 of them in `docs/`.

**Repository root**

| File | Purpose | Status |
|---|---|---|
| `README.md` | 354 lines, rewritten on 18 October 2026 (065cecc): what the application is, the ownership and licence notice, a section on Qmail, council addresses and the Admin Panel linking `docs/QMAIL.md` and `docs/ADMIN_PANEL.md`, the Earth map, the India map and registration wizard, "Run it" (2 commands, then `docs/INSTALL.md`), the zodiac and kundali design, the code layout, known simplifications, and a pointer to the open work in `docs/dpg_evidence/10_forward_plan.md`. Routes, modules and tables are left to `docs/API.md`, `docs/ARCHITECTURE.md` and `docs/DATA_MODEL.md` | Complete. *Corrected 18 October 2026: this row previously said 362 lines and Complete. That README did not mention Qmail, council addresses or the Admin Panel, and it also said things that were no longer true: a manual `db/init_db.py` step (the app sets up its own database on boot), a 12-route API table (there are 178 routes), a registration flow through a disconnected `identity_core.py`, and two known simplifications that had already been fixed. The rewrite in 065cecc removed those and added what was missing.* |
| `.env.example` | Every environment variable with safe placeholder values | Complete |
| `requirements.txt` | 7 Python dependencies, minimum versions only | Complete |
| `.python-version` | Python 3.12 | Complete |
| `Procfile` | Production start command (`gunicorn app:app`) | Complete |
| `migrations/` (001–003 and 007–024) and `tools/run_migrations.py` | Schema changes. `app.py` applies the full schema and runs the migrations on every boot (`ensure_database_ready`), so no manual step is needed. Explained in `docs/DATA_MODEL.md` | Complete |
| `db/schema.sql`, `db/init_db.py` | Base schema and first-run setup | Complete (see `docs/DATA_MODEL.md`) |
| `tools/verify_*.py`, `tests/` | Verification scripts for the lunar-cycle and archive systems (listed in `docs/INSTALL.md`), and 11 test scripts in `tests/` (the eleventh, added in c09b91f, brings the repository to 440 tracked files at 065cecc): council updates, post kinds, Account ID sync, Qmail, Qmail attachments, Qmail drafts, the `/qmail` page, the shared text renderer's wiring, Q-Punch council addresses, the Admin Panel's council scope, and reading replies to a member's own council message or Admin query (`tests/test_reply_read.py`, added with the fix in c09b91f, Document 10 row 44). Each is a standalone script with no test framework: it builds a throwaway database through the real app and prints PASS or FAIL. All 11 passed on 18 October 2026 at c09b91f. `tests/test_qmail_attachments.py` section 6 covers the attachment fix in f1edd55 (Document 09, 9.6 row 8), which made three decisions a reader should see: `qmail_core.AttachmentTypeError` subclasses `ValueError`, so any existing caller that catches `ValueError` still works, while the compose route catches the subclass first and returns 400 for a disallowed type instead of the size limit's 413; a valid file whose browser declares a blank or unrecognised content type is rejected, which is deliberate strictness and a known limitation members may notice (for example, a .docx from a machine with no Office type mapping will not attach); and the download-only serving applies to attachments already stored, because it changes the serve route rather than the stored data, so no migration was needed. Each script sets its repository root to the founder's own checkout path, so on another machine it needs `PYTHONPATH=.`, and four of them (council updates, post kinds, the renderer wiring and reply reading) read files through that path and fail unless the repository sits there (5.3 #11). There is no test suite covering the whole application yet. | Partial |
| `LICENSE` | AGPL-3.0 | Complete |

**`docs/` folder, grouped**

| Files | Purpose | Status |
|---|---|---|
| `INSTALL.md` | Clone to running server: quick start, environment variables, becoming an admin, production settings, verify scripts, sample data, and where to get `Qumanity_Master.json` | Complete |
| `ENVIRONMENT.md` | Every environment variable: purpose, default, whether production needs it. Defaults are repo-relative (`QM_EARTH_ROOT=./0_Earth`) | Complete |
| `ARCHITECTURE.md`, `API.md`, `DATA_MODEL.md` | Component diagram and module map; `/api` routes with access level; tables and migrations | Complete. Brought up to date on 18 October 2026 (065cecc) from this pack's own copies, which they now match byte for byte: `API.md` covers all 178 `/api` routes and `DATA_MODEL.md` covers the 74 tables created on boot, the 2 created on first use, and migrations 001–003 and 007–024 (5.3 #10). *Corrected 18 October 2026, twice: first from Complete to Partial, because `API.md` then documented 170 of 178 routes and `DATA_MODEL.md` listed 67 tables and migrations up to 018; then back to Complete once 065cecc brought both up to date.* |
| `QMAIL.md`, `ADMIN_PANEL.md`, `EMAIL.md` | Qmail, Q-Punch council addresses, attachments, drafts and the `/qmail` page; the Admin Panel, its scope rules and the council queue; the optional registration email | Complete |
| `HANDOVER.md` | A map of the whole project for whoever takes it over next, refreshed 18 October 2026. It says of itself that it will go stale and is not a source of truth for current state | Complete (snapshot) |
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

**Overall:** the design of each feature is well documented, `docs/INSTALL.md` takes a newcomer from `git clone` to a running server, and the README, `API.md`, `ARCHITECTURE.md` and `DATA_MODEL.md` cover the 18 October 2026 features (065cecc). The demo login list (`DEMO_ACCOUNTS.md`) was removed from the repository, added to `.gitignore` and scrubbed from git history. The one remaining gap is the village dataset (5.3 #3). `dpg_evidence/` holds this evidence pack.

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
| 10 | Found 18 October 2026: the repository's `docs/API.md` and `docs/DATA_MODEL.md` do not cover the routes and tables added on 18 October 2026 (5.2) | Bring both up to date from this evidence pack's own `API.md` and `DATA_MODEL.md` once those are revised in this pass | Done, 18 October 2026 (065cecc): `API.md`, `ARCHITECTURE.md` and `DATA_MODEL.md` in the repository match this pack's copies byte for byte |
| 11 | Found 18 October 2026: the test scripts hard-code the founder's checkout path | Resolve the repository root from each script's own location, which fixes the import for all 11. The four path-dependent scripts (council updates, post kinds, the renderer wiring and reply reading) also read files such as `db/schema.sql` and `templates/dashboard.html` through that hard-coded path, so their file reads must be changed too, or they will still fail after the import is fixed. Document how to run the tests in `docs/INSTALL.md` | Pending (code) |
| 12 | Found 18 October 2026: `README.md`'s feature tour does not yet mention Qmail, council addresses or the Admin Panel | Add them to the feature tour, linking `docs/QMAIL.md` and `docs/ADMIN_PANEL.md` | Done, 18 October 2026 (065cecc): a new README section covers all three and links both files. The README was also corrected where it had gone out of date (5.2) |

## 5.4 Additions now in place

`docs/INSTALL.md`, `docs/ENVIRONMENT.md`, `.env.example`, `docs/ARCHITECTURE.md`, `docs/API.md` and `docs/DATA_MODEL.md` are all in the qumanity-web repository (checked 17 October 2026). `docs/QMAIL.md`, `docs/ADMIN_PANEL.md`, `docs/EMAIL.md` and `docs/HANDOVER.md` were added on 18 October 2026. The README, `API.md`, `ARCHITECTURE.md` and `DATA_MODEL.md` were brought up to date on 18 October 2026 (065cecc). The open documentation items are publishing `Qumanity_Master.json` (5.3 #3) and the test scripts' hard-coded path (5.3 #11).
*Correction, 18 October 2026: this section previously said publishing `Qumanity_Master.json` was the only open documentation item. The features added on 18 October 2026 left `API.md`, `DATA_MODEL.md`, the README and the test scripts behind (5.3 #10 to #12); #10 and #12 were closed the same day by 065cecc.*

## 5.5 Evidence for the application form

| Form field | Proposed answer |
|---|---|
| Documentation URL | https://github.com/sitaram-box/qumanity-web/tree/main/docs |
| Setup guide | `docs/INSTALL.md`, with `docs/ENVIRONMENT.md` and `.env.example` |
| API documentation | `docs/API.md` (every route), `docs/ARCHITECTURE.md` and `docs/DATA_MODEL.md` |
