# Qoin transaction history

## Private account
A **Transaction history** section lists credits and debits with their Qoins and currency value, grouped **by week**.
- The weekly view refreshes at **00:00 when Sunday ends and Monday begins**, showing the week that just finished (in the user's country time zone).
- The user sees the **last 3 months** only. Older weeks are kept in the backend and can be opened by **council members** only.
- Each week shows its rows (`+2 Qoins · Post reward at Tehsil · 25 Sep 14:32`) and a **weekly change**.

## Group wallets (Village → Earth)
Every group wallet has the same history. The group's **Q-Punch council** can read it: how many Qoins, with their values, came in or went out last week and before.

## Storage
`…/wallet/transactions/2026-W39.json` (one file per ISO week) **and** the `wallet_transactions` table with `week_number`, `year`. Rows are written when the transaction happens; the weekly file is closed at the Monday-00:00 boundary. On the website the week is computed when the page is read (no scheduler needed on the free plan); the app uses `tools/ops` until Cloud Functions are available.

## Status
`wallet_core.wallet_transactions` already lists a user's rows. To build: week grouping, the 3-month cut-off, council access to older data, the group-wallet view, the Private-account section.
