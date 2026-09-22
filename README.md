# Opulent Property Management

Staff condominium-fee and rent billing system. Local development uses SQLite; hosted deployment uses PostgreSQL with separate Railway web and reminder-worker services. The responsive frontend is an installable PWA. **Reminder delivery remains simulation-only.** A separate command can send one fixed test SMS to the Africa's Talking Sandbox simulator.

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
- `test_system.py`: financial, reminders, restore and HTTP security checks.
- `test_postgres.py`: hosted PostgreSQL billing and reminder workflow check.
- `worker.py`: dedicated hosted reminder scheduler.
- `sms_sandbox.py`: guarded, one-message Africa's Talking Sandbox smoke test.
- `tools/migrate_sqlite_to_postgres.py`: guarded one-time transfer tool.
- `data/opulent.sqlite3`: created on startup; not source code.
- `backups/`: administrator-created verified database backups.

`OPULENT_PORT` and `OPULENT_DB` environment variables allow separate local test instances. `AFRICASTALKING_USERNAME=sandbox` and `AFRICASTALKING_API_KEY` configure only the explicit sandbox test command; keys must stay outside source control. The automatic reminder worker never calls the provider. The default local server binds only to 127.0.0.1. The hosted adapter enforces the configured HTTPS host/origin and uses Secure cookies. This remains a single-organization pilot, with production limitations described in the guides.

See `IMPLEMENTATION_NOTES.md` for implemented behavior, design departures and production work. Original architecture and concept documents remain reference materials. Follow `AGENTS.md` for further changes.
