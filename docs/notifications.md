# Notifications (2026-09-28)

A small, honest badge count of what a user hasn't looked at yet — never a separate feed of
synthetic "activity" events. Code: `notify_core.py`, `GET /api/notifications/summary`,
`POST /api/notifications/mark-read`.

## What's counted
- **Unread Personal-timeline chats** — private one-to-one chats and group chats (see
  `docs/personal_timeline_and_social.md`). A chat is unread when it has a message newer than the
  user's own read mark for it (or no mark at all yet).
- **Pending people-requests** — rows in `people_requests` with `status IN ('pending', 'waiting')`
  addressed to the user.

**Not counted**: village/sub-group board chat or Collective Board posts — those are public,
location-scoped feeds rather than something addressed to one person, so a per-user unread count
for them doesn't map cleanly onto "you have a notification."

## Read state
`chat_read_state (user_id, kind, chat_id, last_read_at)` — a simple per-(user, chat) high-water
mark, `kind` is `'private'` (→ `private_chats.id`) or `'group'` (→ `personal_groups.id`).
`last_read_at` is written in the same ISO-with-timezone shape as every message's `created_at`
(`dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")`) — SQLite has no real datetime
type, so comparisons are plain string comparisons, and mixing that format with SQLite's own
`CURRENT_TIMESTAMP` (space-separated, no offset) would silently sort wrong for every timestamp.

Marked read automatically wherever a chat is already loaded or sent to, so nothing extra was
needed on either client: `api_people_chat_messages` and `api_people_group_messages` in `app.py`
call `notify_core.mark_read()` on both GET and POST. The one special case is
`social_core.decide_request()`: accepting a message request inserts the *sender's* first message
into `private_messages` on the recipient's behalf, so that insert also marks the chat read **for
the sender** — otherwise their own words would show up as an unread notification for them.

## UI
- **Website**: a bell icon (`#notif-btn`) in the dashboard header (`templates/dashboard.html`,
  wired in `static/js/dash_extras.js`), polled every 30s; clicking it switches to the Personal tab.
- **App**: a bell with a badge in `DashboardHeader.tsx` (same 30s poll), opening a dedicated
  `notifications.tsx` screen — pending requests are actionable right there (Accept/Decline/Waiting,
  reusing the same inbox as the Personal tab); unread-chat counts are a tap-through to the Private
  or Personal tab.

## Not built
- No push notifications (would need APNs/FCM wiring plus the paid Firebase plan on the app side).
- No per-chat "which ones exactly are unread" endpoint — the app's Notifications screen shows
  counts and links to the right tab, not a merged list of individual unread chats.
