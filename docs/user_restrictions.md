# Who can do what: Sub-continent residents and everyone else

Anyone on Earth can register. **Where you presently live** decides the accounts you get.

| | Lives in one of the 10 Sub-continent countries (India, Nepal, Bhutan, Bangladesh, Myanmar, Sri Lanka, Pakistan, Balochistan, Afghanistan, Maldives) | Lives elsewhere |
|---|---|---|
| Private account | ✅ | ✅ |
| Personal account (family, friends) | ✅ | ✅ |
| **Public account** (Village → Zone pages) | ✅ | ✗ |
| Global account (Country, Continent, Earth pages) | ✅ | ✅ |
| Post in the Village chat | ✅ (present village) | ✗ |
| Paid posts Tehsil → Zone | ✅ | ✗ |
| Vote on posts | ✅ their present groups | ✅ only on the Global pages where they are members |
| Read council broadcasts and elevated posts | ✅ | ✅ |
| Vote in council elections | ✅ village and above where eligible | ✗ |
| Currency shown | their country's | not decided — a Global-only member outside the 10 countries has no Qoins currency mapping yet; they don't currently earn or spend Qoins |

- Birth location may be **anywhere** (default Asia); **present** location decides everything above (`register.js` + `/api/auth/register` enforce the Sub-continent rule for a Public account).
- People elsewhere read broadcast messages of the Global pages, and read and vote on elevated user posts there. They cannot write in chats.
- Moving house creates a **new Account ID** (a new present-location group set); the User ID stays for life.
