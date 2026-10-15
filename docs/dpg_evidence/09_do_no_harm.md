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

## 9.3 Financial harm

Qumanity does not store, transmit, or process financial data. There is no payment processor integrated. This eliminates an entire category of harm (payment fraud, card theft, financial PII exposure). The Qoin system is strictly internal to the platform and cannot be used to send or receive money.

## 9.4 Inappropriate and illegal content (9B)

Members create content in three places: Collective Board posts, Citizen Reports and private messages.

- **Collective Boards:** posts start at the village level and rise only if residents vote them up. When a post's voting window closes with a score of zero or less, it is marked removed and hidden from the board (`board_core.py`). Its author can still see it in their removed posts. This is community moderation by vote, but it acts only when the window closes, so a harmful post stays visible until then. Posts and messages are limited to 1,000 characters.
- **Citizen Reports:** these go only to the responsible council and have no public view. A council must respond within 10 days or the report escalates to the next level.
- **Private messages:** these are seen only by the people in the chat.

Qumanity acts as an intermediary under the Information Technology Act, 2000 and the Intermediary Guidelines, 2021. That carries duties the platform does not yet meet in full: published rules for users, a grievance officer, and removal of unlawful content on notice. These are actions 1 to 3 in 9.6.

## 9.5 Protection from harassment (9C)

- **Messaging by consent:** a member cannot open a private chat with someone directly. They send a message request with one first message, and the other member accepts or declines it (`social_core.send_message_request`, `decide_request`). Repeat requests while one is pending are refused.
- **Anonymous reports:** a member can report a problem to their council without the council seeing their name.
- **Hidden identity:** the data model can show a member by Account ID instead of name and hide their exact location from strangers. There is no member-facing switch yet.

## 9.6 Gaps and actions

| # | Gap | Action | Status |
|---|---|---|---|
| 1 | No way for a member to report a post, message or member as abusive | Add "Report" on posts, messages and profiles, with a review queue for the administrator | Pending (code) |
| 2 | No way to block a member | Add "Block": a blocked member cannot send requests or messages | Pending (code) |
| 3 | No published community rules or grievance contact (IT Rules, 2021) | Publish community rules and name a grievance officer (founder@qumanity.in) with a response time | Pending |
| 4 | Village member names are listed without sign-in (Document 07, action 3) | Require sign-in | Pending (code) |
| 5 | Small-count statistics can single out individuals (Document 07, action 4) | Suppress counts below 5 | Done, 14 October 2026, for the location stats (JSON and CSV); the Earth, country and continent routes remain (Document 06, 6.5 #5) |
| 6 | No minimum age or parental consent (Document 07, action 5) | Set a minimum age or add parental consent | Pending |
| 7 | Hidden identity has no member-facing switch | Let any member turn it on in Private account settings | Pending (code) |

## 9.7 Evidence for the application form

| Form field | Proposed answer |
|---|---|
| 9A: Does the project collect, store or distribute PII? | Yes. See Document 07 for what is collected and how it is protected. |
| 9B: Does the project collect, store or distribute content? | Yes: board posts, Citizen Reports and messages. Moderation is by community vote today; reporting tools and published rules are planned (9.6). |
| 9C: Does the project facilitate interactions between users? | Yes. Messaging requires the recipient's consent; block and report tools are planned (9.6). |
