# Verification — pilot

## Version 1.2 checks

**32 automated tests passed**, including the complete SQLite suite and a live PostgreSQL 17 container workflow covering schema initialization, linked property/contact records, exact-money partial allocation, reminder queueing, simulated processing and JSON-safe state output. A clean SQLite administrator database was transferred to a separate PostgreSQL database and verified. The Linux production Docker image built successfully. JavaScript syntax passed.

The fictional company demo was removed from the active local database by restoring its verified pre-demo baseline. One administrator remains; properties, units, contacts, charges, payments and messages are empty. A pre-removal safety backup preserves the demo state outside source control. Automatic scheduling is disabled.

PostgreSQL support, an explicit migration marker, a guarded SQLite transfer tool, a separate hosted reminder worker, Railway environment templates and GitHub verification workflow are present. No live SMS was sent. Railway production operation, delivery callbacks, load testing and practised Railway backup restoration remain deployment-stage checks.

## Version 1.1 checks

**29 automated tests passed** against isolated temporary databases, including the existing financial/security suite, contact edit and exact historical billing-start dates, optional alternate-number validation and explicit selection, duplicate-number consolidation, overdue-only manual penalty notices, worker snapshot preservation, additive upgrade safety and legacy-message duplicate prevention. The hosted Flask adapter checks passed for setup-code protection, Secure cookies, CSRF/origin/hostname enforcement, healthchecks, bounded request bodies and failure on invalid configuration. Python compilation and JavaScript syntax checks passed.

No browser walkthrough of the version 1.1 additions is claimed; prior browser observations below apply to version 1.0. The new demo is intentionally a frontend-only illustration; database-facing reminder tests exercised the actual server functions.

The application has not been deployed to Railway. A Docker build/run could not be verified because the local Docker Desktop Linux engine was not running. The actual WSGI request adapter was exercised through Flask's test client. Manual notice wording does not act on any elevator card, and no real SMS was sent.

The live local database was backed up with SQLite's backup API and checked for integrity before the 1.1 startup migration. No real records were imported or changed by the test suite.

## Version 1.0 checks

Final automated result: **21 tests passed** using isolated temporary databases, covering financial calculations, allocations, credits/reversals, recurring and historical charges, reminder races and duplicate protection, automatic scheduling and quiet hours, backup integrity and actual restore, staff roles, authentication, CSRF and same-origin restrictions. Queued automatic jobs cannot block deliberate manual simulations while automation is disabled or during quiet hours. See `test_system.py`.

Python compilation and JavaScript syntax checks passed. Browser inspection used a separate database at `work/ui-test.sqlite3` and a test server on port 8766. The main database and administrator setup were left untouched by these test interactions.

## Browser observations

- Signed in with an isolated test account and loaded fictional property/unit/contact records.
- Recorded a UGX 200,000 partial payment against a UGX 350,000 charge. Dashboard and reminder preview both showed UGX 150,000 remaining.
- Previewed and confirmed one test reminder. History transitioned from queued to simulated with reference SIM-1. No external SMS was sent.
- Created an independent UGX 800,000 Rent recurring plan for A01 and generated the selected month's rent charge without duplicating existing condo charges.
- Registered an owner as a second unit contact and verified the saved row.
- Opened the in-app User Guide and confirmed startup, registration, rent, payment and reminder instructions were visible.
- Inspected the desktop dashboard at 1366×900 and the narrow layout at 430 pixels. After the overflow fix, measured document width was 415 pixels within the 430-pixel viewport. Temporary viewport override was reset.
- Captured browser error/warning logs: empty at the check.
- Stopped the test server and reloaded. The service worker displayed “Opulent cannot reach the server” with instructions to restart it and an explicit warning that changes cannot be saved offline.
- Started the main application on port 8765 and verified its first-run administrator setup screen. No default administrator credentials or test financial records were inserted into the main database.

## Limits of verification

No live SMS transport exists, and real phone delivery was not tested. Edge's installed-app workflow is documented but was not used to install a shortcut on the user's PC during testing. A production HTTPS deployment, centralized PostgreSQL migration, multi-PC access, full operational recovery and production load/security evaluation remain unverified work.
