# Deploy Opulent through GitHub and Railway

Opulent 1.2 uses PostgreSQL when hosted. Local development continues to use SQLite. SMS remains simulation-only until a provider is selected and separately authorized.

## Services

Create three Railway services in one project:

1. **Opulent Web** — this GitHub repository; Dockerfile start command; public HTTPS domain; health check `/healthz`.
2. **Postgres** — Railway PostgreSQL. It is the authoritative hosted database and needs scheduled backups.
3. **Opulent Worker** — the same repository and Dockerfile; start command `python worker.py`; no public domain.

Both application services use the same private `DATABASE_URL`. Set `OPULENT_EXTERNAL_WORKER=1` on the web service so it never runs a second scheduler. Keep one worker replica.

## Web variables

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
OPULENT_EXTERNAL_WORKER=1
OPULENT_PUBLIC_URL=https://YOUR-FINAL-DOMAIN
OPULENT_SETUP_TOKEN=A-PRIVATE-RANDOM-VALUE-AT-LEAST-24-CHARACTERS
```

Railway provides `PORT`. Never commit actual values. The setup token protects first-administrator registration.

## Worker variables

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
AFRICASTALKING_USERNAME=sandbox
AFRICASTALKING_API_KEY=YOUR_PRIVATE_SANDBOX_KEY
```

The worker has no domain. Its reminder loop records simulated outcomes only. The Africa's Talking credentials are used solely when an administrator deliberately runs `python sms_sandbox.py +256...` inside the worker service. The command refuses any username other than `sandbox`, validates one international number and uses a fixed harmless message. Sandbox messages appear in Africa's Talking's simulator rather than on a real handset.

## Safe deployment

1. Keep the GitHub repository private and connect `main` to both application services.
2. Add PostgreSQL and reference its private `DATABASE_URL` from web and worker.
3. Generate the final domain and set that exact HTTPS origin in `OPULENT_PUBLIC_URL`.
4. Enable GitHub **Wait for CI**. The workflow checks SQLite, PostgreSQL, the hosted adapter and Docker build.
5. Deploy staging first and use only fictional contacts.
6. Verify login, charges, partial payment, reminder simulation, worker operation and persistence across redeployment.
7. Configure and test PostgreSQL backups before production records.
8. Use a separate production environment/database. Never connect staging to production data.

The clean local administrator can be transferred with `tools/migrate_sqlite_to_postgres.py`, although creating a new hosted administrator is simpler while no business records exist. The migration tool refuses a populated destination, clears sessions, cancels pending jobs and disables automation for review.

## Updates and installation

Develop locally, run checks, verify staging, back up production and merge approved changes into `main`. Railway rebuilds web and worker from the same commit. Staff keep the same installed shortcut and refresh after the update prompt. Database changes require compatible, versioned migrations.

Staff receive the final HTTPS URL. In Edge they open it, sign in, then choose **More tools → Apps → Install this site as an app**. No Python, Docker or database is installed on their PCs.

Never store databases, backups, exports, `.env` files, setup tokens, SMS credentials or phone lists in GitHub.

## SMS and recovery

Railway does not create an SMS account. The prepared smoke test uses Africa's Talking Sandbox only. Keep its API key in Railway variables, never GitHub. Sign in to the Africa's Talking Sandbox simulator using the recipient number, then run `railway ssh --service "Opulent Worker" python sms_sandbox.py +256...` from the linked project folder. Replace `+256...` with that simulator number. This does not connect automatic reminders or contact a real handset.

Live delivery remains a separate change: register the sender ID, add explicit live-mode controls, implement authenticated delivery callbacks and test authorized real numbers before enabling it.

Use Railway PostgreSQL scheduled backups and practise restoring into staging. Code rollback does not reverse a database migration. Verify balances and automation settings before restarting a restored worker.
