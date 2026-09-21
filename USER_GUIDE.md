# Opulent user guide

Version 1.1.0 — local/hosted pilot. Project folder: `C:\opulent condo system`.

## What you have

A working staff-only web application with property and tenant records, rent and condominium charges, monthly fee plans, payments, balances, reminder simulations, staff permissions, CSV exports and database backups.

**SMS is simulation only. No message reaches a phone in this version.** No paid provider account, hosted deployment or real customer records have been configured. A server-side worker processes simulated reminders every 15 seconds, independently of the browser while the server is running.

## 1. Start it on your PC

1. Open `C:\opulent condo system` in File Explorer.
2. Double-click **Start Opulent.cmd**. Python 3.13 is already available on the development PC. Another PC needs Python installed and available on PATH.
3. Leave the server window open. When it displays the application address, open **http://localhost:8765** in Microsoft Edge.
4. On your first visit, enter your name, staff email and a password of at least 12 characters to create your administrator account. No email is sent; the email identifies your account.
5. On later visits, sign in with that email and password.

To stop the system, press **Ctrl+C** in the server window. Closing the browser does not stop reminders; stopping the server does. The installed shortcut does not automatically start the server.

If the browser says it cannot connect, first check that the server window is open. If the server reports that port 8765 is already in use, check whether Opulent is already running; do not launch a second copy.

## 2. Install the app shortcut

After opening the address in Edge, use its menu → **Apps** → **Install this site as an app**, or its app-install icon if offered. You can also open Opulent’s **User Guide** screen and click **Install on this PC** when the browser supports the installation prompt. Pin the installed app to Start or your taskbar.

Installation creates a browser-managed app window and shortcut, not a standalone Windows installer. The server must still be running. Browser installation support is described in [Microsoft's PWA documentation](https://learn.microsoft.com/en-us/microsoft-edge/progressive-web-apps/ux); local development installability is described in [MDN's installability guide](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable).

This pilot accepts localhost connections only. Other PCs cannot connect to this PC over the network. An organization-wide release needs one secured hosted server and database, not separate copies of this folder with separate records.

## 3. Set your organization preferences first

Open **Settings → Edit settings** as Administrator.

- Currency: default **UGX**, illustrative until you confirm it.
- Country: default **UG**, illustrative until you confirm it.
- UTC offset: default **180 minutes**, meaning UTC+3. This is a fixed offset and does not automatically change for daylight saving.
- Automatic billing and reminders: disabled initially.
- Days before due date: default 7.
- A reminder also occurs on the due date. Overdue repeats default to every 7 days, measured from the due date.
- Quiet hours: default 18:00–08:00 for automatic reminders.
- Price per SMS segment: 0 means unknown, not free provider service. It is only an estimate; simulations incur no provider fee.

The currency is locked after you create financial records so changing a label cannot silently turn UGX balances into another currency. All amounts use two decimal places internally, including currencies normally displayed as whole amounts.

## 4. Register properties and units

Open **Properties & Units → Add property** and enter its name and address/location. Then choose **Add unit**, select the property, and enter its block and unit label, for example Block A / A01.

The combination of property, block and unit label must be unique. Use **Deactivate** for a unit you no longer bill. Its history remains, and future automated charges/reminders are skipped while inactive.

## 5. Register tenants, owners and phone numbers

Open **Contacts → Register contact**.

1. Select the unit.
2. Choose Tenant or Owner.
3. Enter the name.
4. Enter a full international phone number beginning with `+`, without spaces or punctuation, for example a country code followed by the subscriber number.
5. Choose whether this contact receives reminders.

Enter an optional **alternate phone number** directly on the same contact, using the same international format. Enter **Start of billing period** as an exact calendar date, for example 17 May 2025. It records when billing began and does not generate historical charges or prorate fees. Existing contacts show “Not recorded” for unknown dates; use **Edit** to fill them in rather than inventing them.

Register an owner as a separate contact when needed. A shared phone number does not merge financial accounts. Number validation checks the international format; it does not prove ownership or whether the number is reachable. Primary and alternate numbers must differ.

Use **Mute SMS** to stop reminders for a contact, or **Deactivate** when they leave. Register the replacement against the same unit. Historical balances remain with the unit in this release; separate liability accounts per occupant or owner are not yet supported.

## 6. Declare rent and condominium fees

Open **Charges → Set recurring fee**.

1. Select a unit and choose **Rent** or **Condo Fee**.
2. Enter the monthly amount.
3. Select the due day and first billing period.
4. Optionally enter the final billing period.
5. Save, then click **Generate a billing period** and choose the month to bill.

One unit can have a rent plan and a separate condo-fee plan. **Add category** creates categories such as Water or Parking. Only one charge per unit/category/month is allowed in this release; multiple same-month assessments require separate categories.

A due day of 31 uses the month's last day when it has fewer days. Generating the same month again creates only missing charges. It does not overwrite amounts already billed.

To change a future fee, **Stop plan**, then create the replacement plan with its new amount and start month. Existing charges are preserved. Stop a plan only after you have generated any earlier months you still need from it; inactive plans are excluded from generation even for old periods. This version does not edit or void a billed charge; inspect amounts before saving, and use a test database for initial practice.

## 7. Enter previous periods / opening arrears

Open **Charges → Add charge** and enter the original period, due date, amount, category and a descriptive source.

Choose one import approach per historical balance:

- Enter the original charge and separately enter the payments already received; or
- Enter only the unpaid opening amount and describe its source as opening arrears.

Do not enter both approaches for the same balance. That would count it twice. Dates and amounts are manual entries; review your source statements first.

## 8. Record payments, credit and corrections

Open **Payments → Record payment**. Select the unit, amount, date received and receipt/bank reference. Future payment dates are rejected.

The system allocates money to that unit's oldest outstanding charge by due date, then by charge creation order. It allocates across charge categories. This policy is fixed in the pilot; you cannot select a particular charge or category to allocate to yet.

For a UGX 350,000 charge and a UGX 200,000 payment, the remaining balance becomes UGX 150,000. A payment larger than all outstanding charges leaves **unallocated credit**, automatically applied when new charges are created.

If an entry is wrong, click **Reverse**, enter a reason and save. The original record remains with a Reversed status. Its allocations stop counting; other available unit credit may cover the reopened charges. Record the correct payment separately.

Payment submissions have a request identifier to protect retries of the same form. After a connection error, retry within the existing form or inspect payment history before starting a new one. Receipt references are not globally unique because a receipt may represent several units; the system cannot identify a duplicate manually entered through a completely new form.

This records received money; it does not collect payments, connect to mobile money or issue automated SMS receipts.

## 9. Test phone numbers and manual reminders

Open **Guided Demo** from the sidebar or Dashboard to practise without saving any database records. It shows a fictional tenant whose billing began on 17 May 2025, an overdue 350,000 condo charge, a 200,000 example payment, the remaining 150,000, a manually selected elevator-card notice and a demo simulation. **Reset walkthrough** resets only these browser-session examples. The examples use the configured currency for display.

Using the normal Contacts, Charges or Payments screens does save actual records to the database; keep normal-screen test entries in a separate staging instance. Developer tests use isolated databases.

1. Ensure the selected unit has an active contact with notifications enabled.
2. Create an outstanding charge, including a past period if you want to test arrears.
3. Open **Reminders**. Filter by month, unit, category or overdue status.
4. Select the charge rows, or choose **Select outstanding** for the visible list.
5. Optionally enter a **Penalty notice**. It is added only to selected charges whose due date is before today. Choose **Use elevator-card example** for editable sample wording, or write your own (maximum 300 characters). This communicates staff policy; it neither deactivates a card nor creates a monetary penalty.
6. Optionally check **Also notify the registered alternate numbers**. Primary numbers are used by default; automatic reminders always use primary numbers only. Duplicate numbers within the same selected charge are consolidated.
7. Click **Preview selected**.
8. Review recipient names and numbers, primary/alternate labels, periods, notice wording, balances, estimated segments and cost.
9. Click **Confirm simulation**.
10. Wait up to 15 seconds, then **Refresh status**. Message history should show **simulated** and a `SIM-` reference.

Each opted-in recipient number receives a separate simulated message per selected charge. Fully paid charges and inactive units/contacts are excluded. The reminder describes the selected charge's remaining amount, not an aggregated account total. Manual notice wording is saved with the message snapshot and is never included in automatic reminders.

If a payment or recipient changes after preview, confirmation is rejected and you must preview again. If it changes after queueing but before processing, the queued message is cancelled instead of sending stale information. Retrying confirmation for the same preview does not duplicate messages; a new preview is a new deliberate send and can repeat the message.

**Testing actual phone delivery requires a future provider integration and your explicit authorization to send live test messages.** You will need a provider account, sender approval where required, server-side credentials, verified test recipients, provider pricing and delivery callback configuration. There is no live-send toggle or hidden provider key in this pilot.

## 10. Automatic reminders

Administrators can enable automatic billing/reminders in Settings. Every 15 seconds, the server:

1. Generates missing current-month charges from active plans.
2. Finds outstanding charges whose reminder date is today.
3. Skips automatic reminders during quiet hours.
4. Queues one message per eligible contact and charge for that date.
5. Rechecks eligibility and processes the simulation.

Default schedule: due 30 September, lead 7 days, overdue interval 7 days → reminder dates 23 September, 30 September, 7 October, 14 October, continuing while unpaid. The due-date reminder always occurs, even when staff choose a different pre-due lead time. Duplicate prevention stops the same automatic charge/contact/date combination from repeating.

The local server must be running during a permitted hour on the send date. Missed reminder dates are not caught up automatically. Recurring generation creates only the current month automatically, not all missed months; use manual generation for missed periods. Manual confirmations are deliberate staff actions and are not restricted by automatic quiet hours.

## 11. Staff roles and security

Administrators add accounts in **Settings → Add staff**:

- Administrator: all billing functions, organization settings, staff creation, backups and audit history.
- Billing officer: properties, contacts, charges, payments and reminders.
- Read-only viewer: records and CSV exports, without mutations or audit/staff administration.

All staff may change their own password in Settings; this invalidates their sessions. Sessions expire after eight hours. There is no password-reset email or staff removal screen yet. Keep administrator credentials safely; forgotten-password recovery needs an authorized maintenance change. The local pilot uses an HttpOnly, same-site cookie and backend permission checks. Its plain HTTP listener is restricted to the same PC; it must not be exposed publicly as-is.

Anyone with filesystem access to the database or backups can read them. Use Windows account and folder permissions and encrypted storage appropriate to your organization. Do not commit `data` or `backups` to source control.

## 12. Reports and backups

**Reports → Export balances** downloads a CSV with billed, paid and remaining amounts for all charges. Open it in Excel if desired. In-app unit reports show total balances and unallocated credit.

**Settings → Create backup** writes a timestamped `.sqlite3` file to `C:\opulent condo system\backups` and checks its integrity. Copy backups to private separate storage. In-app backup creation is manual; scheduled backups are a production task.

### Restore a backup

Restoring replaces the active financial records with the chosen backup. Later entries will no longer be present in the active database, but a safety backup of the existing database is made first.

1. Stop Opulent with Ctrl+C in its server window.
2. Open PowerShell in `C:\opulent condo system`.
3. Run the following, substituting the actual backup filename:

```powershell
python maintenance.py restore "C:\opulent condo system\backups\opulent-YOUR-BACKUP.sqlite3"
```

4. The tool rejects incompatible or damaged backups, preserves a safety backup, restores the data, clears staff sessions and pending previews, cancels queued messages, and disables automatic scheduling.
5. Start Opulent again and sign in with credentials present in that backup. Review balances, contacts and settings before re-enabling automatic scheduling.

The restore command refuses to proceed while the default server port is occupied. Financial unit tests have verified restoration against an isolated database. This is not a substitute for your organization's scheduled recovery exercises.

## 13. Updates

Stop the server, make a backup, then replace only application source/public assets with a verified compatible release. Preserve `data` and `backups`. Start the server and refresh the app. A changed service worker offers an update prompt; save and close forms before applying it. No financial data is cached for offline editing.

Version 1.1 applies an additive migration for alternate phone numbers, billing-start dates and message notices. It preserves financial records, leaves legacy unknown dates empty, and expires old previews so they must be reviewed again. Future schema changes still require verified migrations and a rollback/forward-repair plan; do not install an incompatible source update over financial records.

## 14. Moving to organization-wide operation

The hosted launch files now provide an actionable Railway pilot path. Follow **RAILWAY_GUIDE.md** for the exact source upload, persistent volume, service variables, private setup code, HTTPS domain, staff installation, backups and updates. The Flask/Gunicorn adapter was tested locally; no Railway deployment is claimed. The local launcher continues to work as before.

Before full organizational production use, implement and verify:

- A maintained production server with HTTPS and organization access controls.
- A central production database, with PostgreSQL as the recommended migration target.
- A supervised always-running worker, restart/recovery monitoring and scheduled verified backups.
- SMS transport, bounded retries, reconciliation of uncertain responses, authenticated delivery callbacks, and accepted/delivered/failed/unknown states.
- Local messaging/privacy requirements, recipient preferences and approved sender identity.
- Staff deactivation/recovery, financial charge corrections, deployment migrations and operational load testing.

Do not start entering live customer data or sending SMS until those operating choices and authorization are settled.
