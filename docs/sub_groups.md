# Village sub-groups and the location explorer

## Village: Groups button (built on the website)
On the village Collective Board a **☰ Groups** button on the left opens a drawer with **Village groups only** (sub-groups for societies, RWAs or parts of a large village). They appear **only on the Village page**.
- **Council members only can create** a group. Everyone else sees the list and can **ask to join ONE group** (one group per member); a council member approves or declines.
- Members open the group chat; **← Village board** returns. There is **no member list or member search** in this drawer.

## Tehsil → Earth: the same button lists the level below
The drawer heading is the **next lower level**: Earth → **Continents**, Continent → **Countries**, Country → **Zones**, Zone → **States**, State → **Districts**, District → **Tehsils**, Tehsil → **Villages**. Picking one shows that place's **statistics only** (never a chat). Village groups never appear on these pages.

## Board layout
The board fills the space between the left edge and the statistics column. The **message box stays at the bottom, above the poems marquee**. The board opens on **Live voting**, full height; a **❄️ Frozen posts** button at the bottom-right switches the whole board to frozen and elevated posts (best score first, with scores, dates and comments) and **← Back to live voting** returns.

Code: `board_core.py`, `/api/subgroups`, `/api/chat/<id>`, `static/js/board.js`.

## Who can do what
| Person's relation to a place | Chat, posts, votes | Statistics |
|---|---|---|
| Presently lives there | ✅ | ✅ |
| Born there, lives elsewhere | read only | ✅ |
| Neither | ✗ | ✅ |

Example: living in Village B, a user chats and votes in B; for Village A they can only pick it from the list and read its statistics.

Status: village groups built; the places popup exists as the location tree with statistics in the right column — the dedicated popup and "children list" icon for Tehsil → Earth are to do.
