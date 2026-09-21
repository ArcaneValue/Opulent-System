# Opulent: recommended PC installation and operation

Status: original target architecture. The local app uses SQLite; the prepared hosted path uses PostgreSQL with separate Railway web and reminder-worker services. PostgreSQL was verified locally in Docker but has not yet been deployed to Railway. SMS remains simulation-only.

## Recommendation

Use an online-first progressive web app (PWA) for Opulent staff, with a centrally hosted backend, PostgreSQL database, and durable background reminder worker. This is the recommended design judgment for a shared organization system with quick delivery and centralized maintenance.

A PWA is a web application staff can install through Microsoft Edge on their Windows PCs. It can open from a desktop or Start menu shortcut in its own app window. Staff may also use its secure website. Microsoft documents this installation model in [Use Progressive Web Apps in Microsoft Edge](https://learn.microsoft.com/en-us/microsoft-edge/progressive-web-apps/ux).

This is browser-managed installation, rather than a traditional `.exe` or `.msi` installer. If a downloadable installer is a firm organizational requirement, retain the same backend and database and add a desktop wrapper later. That adds packaging, signing, distribution, and updater maintenance.

## How everyone shares one system

Staff PC app → secure backend → shared database.

Server scheduler → persistent message queue → SMS provider → tenant or owner's phone.

SMS delivery callbacks → backend → reminder history and staff dashboard.

Each authorized staff member signs in with their own account. Suggested roles are Administrator, Billing Officer, and Read-only Viewer. Backend permissions control who can change records and send messages. Tenants have no accounts or portal in version one. Knowing the website address or installing its shell must never grant access to data.

The database stores properties, units, contact relationships, charge types, dated charges, payments, allocations, reminder rules, message attempts, and audit events. Contacts can move between units, and multiple contacts can receive messages for one unit without becoming duplicate financial accounts.

## How we edit an installed application

Developers edit the source project, verify changes in a separate test environment, and release the updated frontend and backend to the central host. Staff PCs retrieve the new web assets; they do not each receive a separately edited application or database.

Design a version-aware update prompt such as “An update is ready. Save your work and refresh.” Coordinate frontend, backend, and database changes so older open windows remain safe during rollout. Service-worker caching needs explicit version management; an update should not be assumed to appear instantly on every open PC. See [MDN's PWA caching guide](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Caching).

Record the deployed version, back up before risky data migrations, and maintain a rollback procedure. Some database changes need a forward repair rather than simply restoring an older application version.

## Sending reminders reliably

Run reminder schedules on the hosted server, independently of staff computers. Browser background work has lifecycle limits, so it is not the dependable clock for financial reminders; see [MDN's offline and background operation guide](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Offline_and_background_operation).

Generate one charge per applicable unit, charge type, and billing period. Record a payment once and allocate it to charges. The outstanding amount comes from charge amounts minus allocations and authorized adjustments. Show current-period balances and older arrears distinctly.

For example, an illustrative UGX 350,000 September charge with UGX 200,000 allocated has UGX 150,000 remaining. If August also has UGX 100,000 outstanding, the account total is UGX 250,000. A September-only reminder must distinguish its UGX 150,000 balance from total arrears.

Automatic reminders select eligible outstanding charges using configurable due dates and reminder rules. Manual reminders allow staff to select older periods, preview recipient-specific balances and text, then confirm sending. Recheck balances before dispatch, prevent duplicate jobs, and retain message snapshots and delivery results. A payment received after dispatch cannot recall an SMS already sent.

## Installation is not offline operation

Version one requires internet for sign-in, live balances, payment entry, and sending. If connectivity is lost, display a clear connection notice and prevent financial submissions from appearing successful. Cache the app shell only where appropriate; do not expose client financial records from shared-PC caches.

Server reminders continue while office PCs are offline, provided the host and SMS provider are operational. Full offline payment entry requires conflict resolution and is a separate feature.

## First release

1. Staff sign-in, roles, properties, units, and contact registration.
2. Configurable charge categories, recurring charges, and traceable historic arrears.
3. Manual payment entry with allocations, partial payments, credits, and reversals.
4. Automatic and manual SMS reminders, preview, duplicate protection, and delivery history.
5. Dashboard, basic exports, audit history, backups, and verified restore.
6. PC installation and safe centralized updates.

Keep automated payment collection, WhatsApp, tenant portals, native desktop packaging, and full offline editing outside this first release unless specifically requested.

## Decisions needed before implementation

Confirm operating country, currency, timezone, number of units and staff, billing dates, opening arrears, payment allocation policy, recipients, reminder frequency, and hosting budget. Choose an SMS provider after checking local coverage, sender registration, delivery reporting, privacy requirements, and current pricing. No provider or recurring cost is committed by this proposal.

## Proposed dashboard concept

The generated image is a visual proposal using fictional data and illustrative UGX amounts. It should emphasize outstanding balances, due and overdue accounts, recording payments, previewing reminders, and delivery outcomes. Its appearance is adjustable when the user provides reference templates; it is not evidence of a working application.
