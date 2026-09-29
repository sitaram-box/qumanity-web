# Private ID, PIN and sign-in

*Website and phone app use the same scheme.*

| Item | Rule |
|---|---|
| **Private ID** | **9 random digits**, unique for every user (no two users can share one), fixed for life, kept **secret** by its owner |
| **PIN** | **5 digits** chosen at registration; replaces the password |
| **Sign-in** | 9-digit Private ID + 5-digit PIN |
| **Lock-out** | 5 wrong PINs lock that ID for 15 minutes |
| **Readable ID** | the older form built from name, gender, age, zodiac and birth place (e.g. `FIM-RM-GMA2-ZFL-CS.DL.1.A.12`). It stays in the database as a reference and is **never shown to the user**; only group admins may reveal it |
| **Account ID** | public, changes with the present location (see the app plan §4) |

## Registration
Step 1 asks for a PIN (twice) instead of a password. At the end the system generates the 9-digit code and shows it once, big and copyable, with a warning to save it; Qumanity cannot recover it. The button reads "I have saved my Private ID → Dashboard".

## Privacy in the profile
The Private ID is **masked** (`•••••••••`). "Show" asks for the PIN again, reveals it for 30 seconds, then hides it.

## Founder / admin
The Founder's readable ID `FIM-RM-GMA2-ZFL-CS.DL.1.A.12` maps to the code `014918240`; the PIN is known only to the Founder (stored hashed). Admin rights are given by the setting `QM_ADMIN_PRIVATE_IDS` (the 9-digit code), currently `014918240`. Demo users are ordinary users.

## Existing users
`scripts/migrate_private_codes.py` gives every existing user a code and the development PIN `12345` (see `DEMO_ACCOUNTS.md`).

Code: `id_generator.generate_private_code`, `/login`, `/api/auth/register`, `/api/user/private-code`.
