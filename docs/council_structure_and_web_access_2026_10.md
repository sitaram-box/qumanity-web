# Quantum Punch Council structure & website access logic — SPEC ONLY, NOT YET BUILT (2026-10-05)

The Founder shared this specification at the end of a session already deep in other work
(Founder's Message translation, go-live hardening). It is captured here verbatim-in-substance so
it isn't lost, and is **explicitly deferred** — nothing below has been implemented. Before
building any of this, reconcile it against what already exists (see "Known conflicts with the
current codebase" below) — several of its assumptions don't match the live system as of this date.

## The spec, as given

**1. Quantum Punch Council — 5 seats, every group page from Village to Earth:**

| Position | Role | How filled | Who can fill |
|---|---|---|---|
| 1 | Mentor | Founder/Admin | Founder only |
| 2 | Member (elected, zodiac male) | Elections | Elected by members |
| 3 | Member (elected, zodiac female) | Elections | Elected by members |
| 4 | Member — Team Manager | Founder only | Hired/added by Founder |
| 5 | Member — Agent | Founder only | Hired/added by Founder |

**2. Key rules**: the Founder is Mentor of every location from Village to Earth, permanently. The
Founder cannot select positions 2/3 (those are elected via zodiac-based elections). The Founder can
only select positions 4/5 (Team Managers and Agents) — hired/internal roles at every scale (local,
district, state, national, global).

**3. Website access (qumanity.in)**: only the Founder plus users added as Manager (4) or Agent (5)
can log in to the *website*. The *phone app* stays open to the general public (register/login) and
every council member. General public = app-only, no website registration/login.

**4. What each role can do on the website**: Founder (Mentor) = full access (add managers/agents,
view all data/tracking/reports). Manager (4) = council dashboard, tracking, reports for their
location. Agent (5) = limited dashboard, assigned tasks, escalation handling. Elected members (2/3)
= no website access at all, app only.

**5. Proposed schema** (as given, Postgres-flavored — `SERIAL`, `REFERENCES`): three new tables —
`council_members` (user_id, council_level, location_id, position 1-5, role, added_by, term dates,
is_active), `web_access` (user_id, can_login, access_level, added_by, is_active), and
`council_permissions` (council_level, position, a set of boolean capability flags — can_add_members,
can_track_users, can_broadcast, can_escalate, can_view_reports, can_manage_agents).

**6. Flow**: Founder logs in → searches a user by Account ID/User ID → assigns them as Manager(4)
or Agent(5) for a location → that user gets a phone notification → they can now log in to the
*website* with Private ID + PIN → they see a Council Dashboard scoped to their role.

## Known conflicts with the current codebase — resolve before building

- **This app runs on SQLite, not Postgres** (per the Founder's own 2026-10-04 go-live decision —
  see `docs/go_live_hardening_2026_10.md` — "stay on SQLite for this launch"). The proposed schema
  above is written in Postgres syntax (`SERIAL`, `REFERENCES`); it needs translating to this app's
  existing SQLite table style (see `election_core.py`'s `village_council`/`election_candidates`
  tables for the established pattern) before it can be built here.
- **A council already exists and doesn't match this 5-seat shape.** `election_core.py`'s real,
  working Zodiac Council Voting system (the pilot village, `election_core.PILOT_VILLAGE_ID`) has
  a *male head* and a *female head* per zodiac-sign cycle (elected), not a fixed 5-seat structure
  with a permanent Founder "Mentor" seat or Founder-appointed Manager/Agent seats. The new spec's
  positions 2/3 ("elected, zodiac male/female") sound like they're describing the SAME election
  mechanism already built (`election_core.nomination_eligible`/`voting_eligible`,
  `current_cycle_for_village`) — but positions 1/4/5 (Mentor/Manager/Agent) are entirely new
  concepts with no equivalent today. Any build here needs to decide: is this describing the
  *existing* council with 3 new appointed seats added on top, or a replacement 5-seat model for
  every location level? The spec as given doesn't say.
- **"Every group page from Village to Earth has 5 seats" is a big scope jump.** The real election
  system today is piloted at exactly ONE village (`election_core.PILOT_VILLAGE_ID`) — it has never
  been generalized to run at every level up to Earth. Building Mentor/Manager/Agent seats "from
  Village to Earth" means deciding whether to generalize the whole election system first, or build
  the appointed seats (1/4/5) independently of whether elections (2/3) exist at that level yet.
- **This directly supersedes the earlier identity-privacy work for the Founder's own account**
  (see `docs/founders_message_2026_10.md` / memory `project_founder_identity_and_message.md`):
  the Founder's account currently has `hide_identity=1` specifically so strangers can't find their
  real name when searching or sending a friend request — but this spec has the Founder logging in
  to a public-facing website role ("Mentor," full admin access) and personally searching other
  users by Account ID/User ID to assign them as Manager/Agent. These aren't necessarily in tension
  (the Founder's PERSONAL social identity staying masked is a different surface than an ADMIN
  action of assigning roles), but it's worth the Founder confirming that distinction explicitly
  before building, since "the Founder's name should never surface" was a hard requirement just one
  day earlier in this same project.
- **"Website login restricted to Founder + Managers + Agents only; general public is app-only" is
  a major, currently-unstated scope change.** Right now `/register` and `/login` on the website are
  open to the general public — this is literally how every test/demo user in this project (and
  presumably real users before the app ships) has ever gotten an account. If this restriction is
  real and intended for launch, it needs explicit confirmation: does the WEBSITE stop accepting new
  public registrations entirely once the phone app exists, or does this restriction only apply
  going forward once the app is live? The spec's own flow ("Founder searches user by Account ID" to
  grant them web access) presumes the user already has an account — meaning app registration must
  already be live and the primary registration path before this makes sense.

## Recommended before building

Walk through the conflicts above with the Founder directly — in particular (a) SQLite vs. the
given Postgres schema, (b) whether this replaces or extends the existing pilot-village election
system, (c) the scope jump from one pilot village to every level up to Earth, and (d) whether
"website is Founder+Manager+Agent only" is meant to take effect now or only once the phone app is
the public's primary registration path. None of this needs re-deriving from scratch next time —
this document is the starting point.
