# Q-Punch council: the 5 seats

Every group from Village to Earth has 5 seats. The council popup on each Collective Board shows them.

| Seat | Who | How |
|---|---|---|
| **1 · Founder / Admin** | the Founder | on every group; **name is never shown**, only the title "Founder / Admin" |
| **2 · Male Leader** | the man elected for the current sun sign (village) or element (above) | elected once a year; **serves only that sign's month**, then is released |
| **3 · Female Leader** | the woman elected for the same sign/element | same |
| **4 · Managers** | a **team** hired by the council members | run every service of the group, Village → Earth; many people can sit in this one seat |
| **5 · Agents & Volunteers** | see below | volunteers register themselves; agents are hired |

## Seats 2 and 3 rotate monthly
- **Village:** each month belongs to a sun sign. In the **Aries** month the elected **Aries male** and **Aries female** hold seats 2 and 3; in the **Taurus** month a different pair; and so on. Each leader **serves only the one month** of their sign (around their birthday) and is then **released**; the next month different leaders serve, and next year that month can have a different pair.
- **Tehsil → Earth:** the leaders are the four **elements** (Fire, Earth, Air, Water), one man and one woman each — 8 a year. Water leaders lead the Cancer, Scorpio and Pisces months, Fire leaders Aries, Leo and Sagittarius, and so on.
- **After serving** a leader may: stand again for the village council next year; stand in the **Tehsil** (element) election, where the village leaders of the whole tehsil are the electors; and so on up the levels if they win.
- **Voting is informed:** every candidate publishes their overall performance, behaviour and promises, and voters read them before voting.
- Third-gender members vote by their present gender identity, matched to their birth sign/element, but cannot stand — see [voting_logic.md](voting_logic.md). Until elections start (minimum residents) the seats show as open.

## Seat 5
- **Volunteers** (village only): anyone can register — vegetable sellers, skilled workers, unemployed people. They can be hired by managers or citizens and can earn by serving; those chosen by the council also hold **referral codes** ([referral_system.md](referral_system.md)).
- **Agents** (every level, Village → Earth): hired for **specific professional services**. They act on the website/app: approve permissions, answer citizens' queries and resolve matters by **direct communication** with members of their group and the pages above.

Code: `/api/qpunch/<level>` and `static/js/board.js` (`openQp`); volunteers register from the popup (`volunteers` table). Agent hiring, manager teams and the leader rotation data are still to build.
