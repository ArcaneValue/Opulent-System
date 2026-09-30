# Deploy Opulent through GitHub and Railway

Opulent 1.4 uses PostgreSQL when hosted. Local development continues to use SQLite. SMS delivery is simulated until `OPULENT_LIVE_SMS_ENABLED=true`; live sending uses EgoSMS (Pahappa Comms) and is authorized separately.

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
```

Railway provides `PORT`. Never commit actual values. The first administrator account is created once on the deployed site; after that, staff sign in and administrators add further accounts in Settings.

## Worker variables

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
EGOSMS_USERNAME=YOUR_COMMS_API_USERNAME
EGOSMS_API_KEY=YOUR_PRIVATE_COMMS_API_KEY
EGOSMS_SENDER_ID=EgoSMS
EGOSMS_ENDPOINT=https://comms.egosms.co/api/v1/json/
EGOSMS_SANDBOX_USERNAME=YOUR_SANDBOX_API_USERNAME
EGOSMS_SANDBOX_API_KEY=YOUR_PRIVATE_SANDBOX_API_KEY
OPULENT_LIVE_SMS_ENABLED=false
```

The worker has no domain. With `OPULENT_LIVE_SMS_ENABLED=false` its reminder loop records simulated outcomes only. Set it to `true` only after a live send is separately authorized. The `EGOSMS_SANDBOX_*` credentials are used solely when an administrator deliberately runs `python sms_sandbox.py 256...` inside the worker service. The command always targets the EgoSMS sandbox endpoint (`https://comms-test.pahappa.net/api/v1/json/`), validates one international number and uses a fixed harmless message.

Add these on the web service only:

```text
EGOSMS_WEBHOOK_TOKEN=A-PRIVATE-RANDOM-VALUE-AT-LEAST-24-CHARACTERS
```

Register `https://YOUR-FINAL-DOMAIN/webhooks/egosms/EGOSMS_WEBHOOK_TOKEN` as the Transaction Status webhook in EgoSMS Settings → API Settings. The token is the only credential on that public route.

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

Railway does not create an SMS account. EgoSMS (Pahappa) provides the sandbox and live APIs. Keep its credentials in Railway variables, never GitHub.

Railway SSH requires a registered key: generate one once with `ssh-keygen -t ed25519 -C "opulent-railway"`, then register its public half with `railway ssh keys add --key "$HOME/.ssh/id_ed25519.pub" --name "Opulent PC"`. From the linked project folder run `railway ssh --service "Opulent Worker" python sms_sandbox.py 256...` and replace `256...` with the sandbox recipient number in international format without a leading `+` or `00`. This does not connect automatic reminders or contact a real handset.

Live reminders remain a separate change: register the sender ID, keep `OPULENT_LIVE_SMS_ENABLED=false` until a live send is authorized, configure the Transaction Status webhook, and test authorized real numbers before enabling it.

### Guarded production smoke test

Production sending uses `EGOSMS_USERNAME`, `EGOSMS_API_KEY` and a single `EGOSMS_PRODUCTION_TEST_NUMBER` on the worker. `OPULENT_PRODUCTION_SMS_TEST_ENABLED` must normally remain `false`. The standalone command has no recipient argument and does not read contacts or reminder jobs. For one authorized test, temporarily set the lock to `true`, run `railway ssh --service "Opulent Worker" python sms_production_test.py --confirm-send-one`, then immediately return the lock to `false`. This command does not enable automatic live reminders.

Use Railway PostgreSQL scheduled backups and practise restoring into staging. Code rollback does not reverse a database migration. Verify balances and automation settings before restarting a restored worker.
