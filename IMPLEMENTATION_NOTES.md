# Implementation notes — 1.1.0 pilot

## Version 1.2.1 Africa's Talking Sandbox smoke test

Inspection confirmed that no SMS provider existed: the reminder worker only marked current jobs `simulated`. A separate `sms_sandbox.py` command now reads `AFRICASTALKING_USERNAME` and `AFRICASTALKING_API_KEY` from the process environment. It refuses usernames other than the literal `sandbox`, rejects missing keys and malformed numbers, sends one fixed non-billing message to one simulator number, and returns only non-secret response metadata. It never queries contacts or joins the automatic reminder path.

The official Africa's Talking Python SDK is pinned as a dependency. Placeholder variable names were added to `railway.env.example`; no key was committed. Unit tests use a fake SMS service and make no network request.

## Version 1.2 PostgreSQL and deployment preparation

Hosted mode now uses `DATABASE_URL` with PostgreSQL while local startup remains on SQLite. The same validated billing functions run through a small parameter-binding compatibility layer. PostgreSQL receives an idempotent initial schema and migration marker. A guarded one-time transfer tool verifies SQLite integrity, refuses a populated destination, copies linked records in one transaction, advances identity sequences, clears sessions, cancels queued reminders and disables automation for review.

Railway web and reminder processing are now separate services. The web service uses `OPULENT_EXTERNAL_WORKER=1`; the private worker runs `python worker.py` against the same PostgreSQL database. Platform-managed database backups replace the in-app SQLite backup button in hosted mode. A GitHub Actions workflow verifies SQLite, PostgreSQL and the Linux Docker image before deployment.

The active local demo was removed through its verified pre-demo snapshot. One staff administrator remains and all business records are empty. **32 tests passed**, including a PostgreSQL 17 container workflow and a separate clean SQLite-to-PostgreSQL transfer. The Docker image built successfully. Railway itself and real SMS delivery are not yet claimed as verified.

## Welcome splash

The main entry page now opens with a navy-and-gold Opulent Condo System welcome overlay. It fades into the existing sign-in, first-administrator setup, or dashboard for already signed-in staff. Authentication requests run immediately underneath; the overlay never waits for the network. JavaScript removes it after two seconds and CSS independently hides it after its brief animation. Reduced-motion settings show a brief static welcome instead. No authentication or database behavior changed. JavaScript syntax and HTTP delivery of the updated assets were checked; browser visual testing was not requested or performed.

## Version 1.1.1 reminder schedule

Automatic notices now have separate pre-due and due-date timing: one notice seven days before, one on the due date, then every seven days overdue while unpaid. Configurable overdue intervals are anchored to the due date, even if the pre-due lead is changed. New databases default to seven days of lead time. The local demo has automatic billing/reminders enabled with lead=7 and repeat=7; quiet hours remain unchanged. SMS remains simulated. A safety backup was taken before updating these settings. The original pre-demo snapshot remains available for eventual cleanup.

32 automated tests passed, including calendar boundaries, a differing lead interval, cleared-bill exclusion, duplicate scheduling, quiet hours, and existing billing/authentication/hosting/demo checks. The server was restarted with the updated worker. Missed send dates still require manual reminders; the server must be running during a permitted hour on the scheduled date.

## Version 1.1 additions

Contact registration now captures an optional alternate phone and required exact billing-start date. Contacts can be edited to fill historical information. The additive migration preserves existing contacts and financial records; existing unknown dates remain NULL and are labelled Not recorded. The date is informational and does not change recurring plans, generate arrears, prorate amounts or change payment policy.

Manual reminder previews accept up to 300 characters of staff-authored penalty wording, appended only for already-overdue charges. Preview/queue processing preserves and rechecks the notice snapshot. There is no card-control integration, monetary penalty calculation or automatic penalty selection. Staff can explicitly include alternate numbers in manual previews. Each selected charge/phone pair is consolidated; automatic reminders use primary numbers. Duplicate protection also recognizes legacy message keys during upgrades.

Guided Demo is a separate in-browser walkthrough with a fictional Pacific Victoria account, historic billing date, partial payment, optional notice and simulation. It never submits database changes or SMS jobs. The previous persistent-demo loading action is no longer presented in the UI.

A Flask WSGI adapter and Gunicorn/Docker/Railway configuration provide a hosted single-instance pilot path. Local startup stays unchanged. Hosted mode requires a configured HTTPS origin, durable storage paths and a private first-admin setup code; it issues Secure cookies and rejects foreign hosts/origins. The hosted worker runs in the same single Gunicorn process. No GitHub push or Railway deployment was performed. Docker image execution could not be checked locally because Docker Desktop's Linux engine was not running.

Read RAILWAY_GUIDE.md for the exact procedure, volume-backed SQLite limitations, backup instructions and centralized updates. Setting DATABASE_URL alone does not migrate this app to PostgreSQL. No live SMS provider is connected.

## What was built

The first usable local application now includes staff sign-in and administrator setup; backend admin/billing/viewer permissions; properties, blocks and active/inactive units; tenant/owner registration and multiple opted-in numbers per unit; configurable charge categories; recurring monthly plans and repeat-safe charge generation; historical manual charges; payment allocation, account credit and audited reversal; selected-period reminder previews and persistent simulated-message processing; automatic current-month generation and reminders with quiet hours; dashboard, balance reports, CSV export, audit history, backups and a restore tool; a PWA manifest and safe update prompt; and a full user guide.

## How information moves

The browser submits an authenticated JSON request. The backend validates it and runs related billing changes inside one database transaction. Financial amounts are stored as integer hundredths, avoiding floating-point arithmetic on the server. Payments allocate to the oldest outstanding unit charge, with excess retained as credit. A balance view derives totals from charges and non-reversed payment allocations.

A reminder preview takes a snapshot of recipients, amounts and text. Confirmation compares it against current data and creates deduplicated database jobs. The background server thread checks those jobs every 15 seconds and rechecks the snapshot. Eligible jobs become simulated; stale jobs become cancelled. It never invokes an external SMS provider.

Persistent job records survive server restarts. The browser is not the scheduler. The local process must remain running; reminders while this PC is switched off require deployment to an always-running host.

## Deliberate departures from the proposal

The original document describes a hosted PostgreSQL design with real provider callbacks. This release uses SQLite and a same-PC Python HTTP server to make the first working version immediately runnable without provider credentials or paid hosting. SQLite is a relational database, but this is not a hosted multi-PC deployment. One database serves all staff accounts using this instance; network access is restricted.

The frontend uses accessible standard browser controls and plain JavaScript/CSS, avoiding a build dependency. The PWA has a manifest and PNG icons. Its service worker stores no personal or financial records and offers an update prompt rather than silently refreshing open forms. There is no full offline editing or native `.exe` installer.

The country, currency and UTC+3 values are initial examples, editable before financial entries. The timezone is a fixed offset, not a daylight-saving-aware named timezone. Two decimal places are supported. There is no currency conversion.

## Financial policy in this release

- One charge per unit/category/month. Extra same-period assessments need a separate category.
- All balances belong to units, not individual occupant liability accounts.
- Allocation is oldest due date first across categories. No staff-selected allocation policy yet.
- Excess payments become credit and cover future charges.
- Reversed payments stay in history and no longer reduce balances.
- Recurring plan changes only affect subsequently generated missing charges.
- Billed charge correction/void, refunds and credit-note adjustments are not yet implemented.
- Payment retries from the same form are idempotent. A completely new form is a new entry; references alone are not duplicate keys.

## Verification

21 automated tests cover exact amounts, partial payments, oldest-first allocation, credit and reversals, short-month recurring due dates, duplicate charges/plans, historic periods, multi-contact selection, opt-out, preview races, repeat-safe sends, post-queue cancellation, automatic quiet hours including previously queued jobs and duplicate protection, currency locking, verified backup and actual restore, authentication, CSRF, origin/host checks, backend roles and static assets. Final results are recorded in `VERIFICATION.md`.

Browser verification is recorded separately in `VERIFICATION.md`. No external SMS delivery, multi-PC network deployment or production load test is claimed.

## Remaining production work

Real provider transport and callbacks are intentionally absent. No live SMS authorization has been given. Provider selection, local sender approval, recipient policies, pricing and credentials need to be confirmed first. A future transport must separate queued, accepted, delivered, failed and unknown states and safely reconcile timeouts before retrying.

Production also needs a HTTPS host and framework/server hardening, supervised processes, database migration management, scheduled secure backups, operational monitoring, staff lifecycle/recovery, audit/notification retention rules, financial corrections and load testing. Existing schema setup is not a migration framework. These are concrete operating limitations of the local pilot.
