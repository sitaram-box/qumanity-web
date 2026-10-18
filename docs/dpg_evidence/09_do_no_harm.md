# Qumanity: Do No Harm by Design

**DPG Standard Indicator 9: Do No Harm by Design**
Current owner: Rohit Mudgal (individual). Legal entity Qumanity Lok LLP is in registration. The IP will be assigned to Qumanity Lok LLP once it is registered.

## Contents

- [9.1 What the DPG Standard requires](#91-what-the-dpg-standard-requires)
- [9.2 Data privacy and security (9A)](#92-data-privacy-and-security-9a)
- [9.3 Financial harm](#93-financial-harm)
- [9.4 Inappropriate and illegal content (9B)](#94-inappropriate-and-illegal-content-9b)
- [9.5 Protection from harassment (9C)](#95-protection-from-harassment-9c)
- [9.6 Gaps and actions](#96-gaps-and-actions)
- [9.7 Evidence for the application form](#97-evidence-for-the-application-form)

## 9.1 What the DPG Standard requires

The project must anticipate, prevent and do no harm by design. The Standard asks about three areas:
- 9A: how personal data is collected, stored and shared securely;
- 9B: how inappropriate and illegal content is handled where users can create content;
- 9C: how users are protected from harassment where they can interact.

## 9.2 Data privacy and security (9A)

Document 07 lists the personal data Qumanity collects and how it is protected. In summary:
- PINs are stored as salted scrypt hashes, with lockout after repeated failures.
- There is no advertising, tracking or sale of data.
- Public statistics are aggregates only, with counts from 1 to 4 shown as `"<5"`.
- A member's birth chart is shown only to that member, after sign-in.
- Database files stay out of the public repositories.
- Every view, reply and close on a message sent to a council address is logged with the council member who did it (`qpunch_queue_actions`), and the Admin member export is logged (`admin_export_log`) (Document 07, 7.3).

## 9.3 Financial harm

Qumanity does not store, transmit, or process financial data. There is no payment processor integrated. This eliminates an entire category of harm (payment fraud, card theft, financial PII exposure). The Qoin system is strictly internal to the platform and cannot be used to send or receive money.

## 9.4 Inappropriate and illegal content (9B)

Members create content in Collective Board posts and comments, Citizen Reports, private messages and sub-group chats, Qmail messages with optional attachments, and messages to their village council's address, and can react to messages and council updates. Councils also publish council updates.

- **Collective Boards:** posts start at the village level and rise only if residents vote them up. When a post's voting window closes with a negative score, it is marked removed and hidden from the board, and its author loses karma (`board_core.settle`). The author can still see it in their removed posts. A post that closes at exactly zero is frozen and stays visible, with no reward. This is community moderation by vote, but it acts only when the window closes, so a harmful post stays visible until then. Posts and messages are limited to 1,000 characters, and comments (allowed only once voting has closed) to 500.
- **Council updates:** posted only by a location's council (or the administrator) and never voted on, so community-vote moderation does not apply to them. Members can react to them. Reporting tools (9.6 #1) will cover them too.
- **Test content:** during the Post Testing cycle, demo accounts post labelled test messages. They are hidden from real members while voting is open, carry a "Demo · Test" badge afterwards, and never earn real Qoins or karma. No scheduler runs the 500 election-pilot demo accounts. The voting logic exists (`election_core.auto_vote`) and can be triggered manually by an admin via `POST /api/admin/election/auto-vote`. Nothing schedules it automatically. The automated election testing cycle is planned, not built.
- **Citizen Reports:** these go only to the responsible council and have no public view. A council must respond within 10 days or the report escalates to the next level.
- **Private messages:** these are seen only by the people in the chat.
- **Qmail messages:** seen only by the sender and the recipient. Unlike posts and chat messages, a Qmail message has no character limit of its own; only the 3 MB request cap applies.
- **Messages to a council address:** these go to a shared queue for the village's serving council heads (or the Admin while the seat is empty), and every view, reply and close is logged with the name of the council member who did it (`qpunch_queue_actions`). A head can close a message but cannot delete it.
- **The Admin Panel:** the Admin reviews four sources in one list: Citizen Reports, ID-recovery requests, member queries and the council queue. A serving village council head sees only their own village's council queue (Document 07, 7.5). Member queries can be read and answered from the panel, but the member-facing route to submit a query is not wired yet, so no member can file one today.
- **Message text is never rendered as HTML.** Qmail stores plain text with three marks only (`**bold**`, `_italic_`, `[text](url)`). The browser builds the bold, italic and link elements one by one with `createElement` and `textContent` (`static/js/qmail_format.js`), so no HTML string is ever built from what a member typed. A link becomes clickable only if it starts with `http://` or `https://`; anything else, including a `javascript:` link, is shown as plain text.
- **Images only as attachments:** a message cannot load an image from an outside URL. Images travel only as attachments, stored in Qumanity's database and served through a signed-in, access-checked route, so opening a message tells no outside party who read it or when. An attachment is always downloaded rather than opened in the page, and only a fixed list of non-executable file types can be attached (9.6, row 8).
- **No automated test of the renderer's safety.** There is no automated regression test showing that a `<script>` tag stays inert text, or that a `javascript:` link stays unclickable. Both were checked by hand, once, in a live browser on 18 October 2026. Because nothing re-checks them, a future change to the renderer, such as building elements with `innerHTML`, adding `|safe` to a template, or loosening the `http(s)://` link check, could reintroduce a cross-site scripting path without any test failing (`docs/QMAIL.md` section 12; 9.6, action 9).

Qumanity acts as an intermediary under the Information Technology Act, 2000 and the Intermediary Guidelines, 2021. That carries duties the platform does not yet meet in full: published rules for users, a grievance officer, and removal of unlawful content on notice. These are actions 1 to 3 in 9.6.

## 9.5 Protection from harassment (9C)

- **Messaging by consent (chats):** a member cannot open a private chat with someone directly. They send a message request with one first message, and the other member accepts or declines it (`social_core.send_message_request`, `decide_request`). Repeat requests while one is pending are refused.
- **Qmail has no request-and-accept step.** Any signed-in member who has activated Qmail can send a message to any member who has activated Qmail, if they have that member's address or 12-digit Public ID (`/api/qmail/compose`, `/api/qmail/resolve-public-id`). The only opt-in is the recipient's own activation of Qmail. A member who has not activated Qmail has no address and cannot be sent a Qmail at all; this is the actual protection. Username suggestions in the To field are limited to members the sender is already connected to, but entering a Public ID reaches anyone who has activated.
  *Correction, 18 October 2026: this section previously said only that messaging requires the recipient's consent. That remains true for chats. Qmail, added in commit fc937b1 (18 October 2026), has no consent step.*
- **Anonymous reports:** a member can report a problem to their council without the council seeing their name.
- **Hidden identity:** the data model can show a member by Account ID instead of name and hide their exact location from strangers. There is no member-facing switch yet.

## 9.6 Gaps and actions

| # | Gap | Action | Status |
|---|---|---|---|
| 1 | No way for a member to report a post, message or member as abusive | Add "Report" on posts, messages, Qmail messages and profiles, with a review queue for the administrator (the Admin Panel can carry it as a further source) | Pending (code) |
| 2 | No way to block a member | Add "Block": a blocked member cannot send requests, messages or Qmail | Pending (code) |
| 3 | No published community rules or grievance contact (IT Rules, 2021) | Publish community rules and name a grievance officer (founder@qumanity.in) with a response time | Pending |
| 4 | Village member names are listed without sign-in (Document 07, action 3) | Require sign-in | Pending (code) |
| 5 | Small-count statistics can single out individuals (Document 07, action 4) | Suppress counts below 5 | Done, 14 October 2026, for the location stats (JSON and CSV); the country and continent routes remain (Document 06, 6.5 #5) |
| 6 | No minimum age or parental consent (Document 07, action 5) | Set a minimum age or add parental consent | Pending |
| 7 | Hidden identity has no member-facing switch | Let any member turn it on in Private account settings | Pending (code) |
| 8 | Found during the pack review on 18 October 2026: a Qmail attachment was served inline with the content type its sender's browser declared, and there was no file-type allowlist. An attachment declared as HTML or SVG could therefore have run script on qumanity.in when its recipient opened it | Attachments are now always served as downloads (`Content-Disposition: attachment`) with `X-Content-Type-Options: nosniff`. On upload, `qmail_core.save_attachment` accepts only png, jpg, jpeg, gif, webp, pdf, txt, csv, doc, docx, xls, xlsx, ppt, pptx and zip, and rejects a file whose extension and declared type disagree, so a rejected file never enters the database. SVG, HTML, JS and XML are excluded. Tested in `tests/test_qmail_attachments.py` section 6 | Done, 18 October 2026 (f1edd55), before submission |
| 9 | No automated regression test for the safety of the Qmail text renderer (9.4) | Add a browser-level test that a `<script>` tag renders as text and a `javascript:` link is not clickable | Pending (code) |

## 9.7 Evidence for the application form

| Form field | Proposed answer |
|---|---|
| 9A: Does the project collect, store or distribute PII? | Yes. See Document 07 for what is collected and how it is protected. |
| 9B: Does the project collect, store or distribute content? | Yes: board posts, Citizen Reports and messages. Moderation is by community vote today; reporting tools and published rules are planned (9.6). |
| 9C: Does the project facilitate interactions between users? | Yes. Chats require the recipient to accept a request first. Qmail has no request step: a member can be sent a Qmail only after activating Qmail themselves, and then by anyone who has their address or Public ID. Block and report tools are planned (9.6). *Corrected 18 October 2026: previously "Messaging requires the recipient's consent", which no longer holds for Qmail.* |
