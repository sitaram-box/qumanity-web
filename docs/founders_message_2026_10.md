# Founder's Message (rewritten) + Founder identity privacy (2026-10-04)

## The message itself

The Founder's Message was rewritten from scratch at the Founder's own explicit request — their
original pasted text is kept only as a reference for tone and structure
(`founder_core.py`'s module docstring says so explicitly), not as the published text. The new
version centers the pain of poor and helpless people, of animals who have no voice in any of this,
and of a damaged Earth, and ends with a real way to actually reach the Founder — not just
sentiment. It keeps the same closing (जय श्री राम / Jai Hind / Jai Humanity) and the same
fifteen-years-alone origin story the Founder's own reference text used, everything else is new
writing.

Section headings in the stored text are marked with a literal `## ` prefix (parsed by
`templates/founders_message.html`), not inferred from capitalization — a real bug on the first
pass (an ALL-CAPS heuristic that never matched Title-Case headings) was fixed this way.

The homepage preview (`templates/home.html`, `data-i18n="founder_preview"`) was rewritten to match,
and retranslated into all 12 supported languages (`scripts/build_ui_locales.py`). The full ~1,500-
word letter itself is still English-only — see `docs/i18n_multilanguage_2026_10.md` for why that
wasn't attempted in this pass.

## Founder identity privacy — a new, general mechanism

The Founder asked for something broader than just "don't show my name": their real name should
only ever be visible to their own Family group and on anything they themselves post to a
Public/Global Collective Board — everywhere else a stranger could discover them (search, a
friend/message request either direction, a village member list), only their Account ID, Gender,
Age-Category and Zodiac Sun-Element show, with their location capped at State (never
District/Tehsil/Village).

**Built as a general per-user flag, not a Founder-specific hack**: `users.hide_identity`
(`app._ensure_user_columns()`), currently set only on the Founder's own account (`id=24`) but
usable for anyone. `social_core.py` gained:

- `is_family_member(conn, owner_user_id, viewer_user_id)` — true if the viewer belongs to one of
  the owner's own "family" category personal groups.
- `display_identity(conn, user_id, viewer_user_id)` — the masking decision itself: real name +
  real village if not hidden or the viewer is Family; otherwise the Account ID as the "name", the
  present location capped to State/Country/Continent, plus Age-Category and Sun-Element.
- `find_person()` (the 12-digit-search-code / Account-ID search `/api/people/search` uses) now
  routes through `display_identity()`.
- `inbox()` (`/api/people/inbox`, incoming friend/message requests) masks `from_name` the same way
  — so a request the Founder SENDS doesn't leak their name to the recipient either.
- `app.api_location_members()` (the village member-list endpoint the dashboard's Public-tab
  explorer uses) masks the same way, scoped per-viewer via `session.get("user_id")`.

**Verified live** (throwaway test account, cleaned up after): searching the Founder's real Account
ID returns `{"name": "<their Account ID>", "place": "Delhi", "age_category": "Yuvak",
"sun_element": "Fire", "gender": "male"}` — no real name, no village. Adding the same test account
to the Founder's own "Paternal" family group and re-checking `display_identity()` correctly
flipped to showing the real name and real village; removing the membership flipped it back.

**Deliberately NOT touched**: Collective Board post rendering (`board_core.py`) — the Founder's own
posts to Public/Global boards should keep showing their real name, exactly as asked, so nothing
there was changed. Private chat headers and business-group listings are NOT yet routed through
`display_identity()` — a known, documented gap if this needs to extend further.
