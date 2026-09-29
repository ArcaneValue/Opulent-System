# Opulent Property Management

Staff condominium-fee and rent billing system. Local development uses SQLite; hosted deployment uses PostgreSQL with separate Railway web and reminder-worker services. The responsive frontend is an installable PWA. **Reminder delivery is simulated unless `OPULENT_LIVE_SMS_ENABLED=true`.** Live sending uses the EgoSMS (Pahappa Comms) API. Separate guarded commands can send one fixed test SMS to the EgoSMS sandbox or to one authorized production number.

## Run

Double-click `Start Opulent.cmd`, then open http://localhost:8765. Create your administrator account on first visit. Requires Python 3.13+. No package installation or frontend build step is needed.

Read `USER_GUIDE.md` for registration, alternate phones, exact billing-start dates, rent setup, manual penalty notices, reminder tests and backups. **Guided Demo** inside the app demonstrates the workflow without database changes. Read `RAILWAY_GUIDE.md` for step-by-step hosted deployment and installed-app updates.

## Verify

```powershell
python -m unittest test_system -v
node --check public/app.js
```

The tests use isolated temporary databases. Node is only needed for the optional JavaScript syntax check, not to run the application.

For the hosted adapter tests, install hosting requirements in a virtual environment and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest test_system test_hosting -v
```

Railway uses Docker, Gunicorn, PostgreSQL and a separate `worker.py` service. See `railway.env.example`; do not commit actual secrets. Real SMS remains a future, separately authorized integration.

## Files

- `server.py`: authentication, permissions, API, exact-money billing, audit and persistent reminder jobs.
- `public/`: frontend, app manifest, icon assets, update-aware service worker.
- `maintenance.py`: verified backup restore, with a pre-restore safety backup.
- `test_system.py`: financial, reminders, restore, HTTP security and live-send/webhook checks.
- `test_postgres.py`: hosted PostgreSQL billing and reminder workflow check.
- `worker.py`: dedicated hosted reminder scheduler.
- `egosms.py`: EgoSMS (Pahappa Comms) provider client; no transport unless explicitly called.
- `sms_sandbox.py`: guarded, one-message EgoSMS sandbox smoke test.
- `sms_production_test.py`: separately locked, one-recipient production smoke test; never used by the reminder worker.
- `tools/migrate_sqlite_to_postgres.py`: guarded one-time transfer tool.
- `data/opulent.sqlite3`: created on startup; not source code.
- `backups/`: administrator-created verified database backups.

`OPULENT_PORT` and `OPULENT_DB` environment variables allow separate local test instances. EgoSMS credentials (`EGOSMS_USERNAME`, `EGOSMS_API_KEY`, and the `EGOSMS_SANDBOX_*` pair) stay outside source control. The automatic reminder worker sends through EgoSMS only when `OPULENT_LIVE_SMS_ENABLED=true`; otherwise it records simulated outcomes. An accepted message is never labelled delivered until the EgoSMS delivery-report webhook confirms it. The default local server binds only to 127.0.0.1. The hosted adapter enforces the configured HTTPS host/origin and uses Secure cookies. This remains a single-organization pilot, with production limitations described in the guides.

See `IMPLEMENTATION_NOTES.md` for implemented behavior, design departures and production work. Original architecture and concept documents remain reference materials. Follow `AGENTS.md` for further changes.
