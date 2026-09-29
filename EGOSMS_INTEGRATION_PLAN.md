# EgoSMS integration plan

Status: **planning document — no code changed.** Implementation begins only after an explicit
**implement** instruction. This file is a proposal and may be revised after the first sandbox test.

## Goal

Replace the Africa's Talking SMS layer with the **EgoSMS (Pahappa) Comms API** so the hosted
system can send real reminder SMS to unit contacts. Sender ID starts as the EgoSMS default and
becomes a configurable value so a custom sender ID can be added later without structural change.

## Current state (verified 2026-09-29)

- `server.py` reminder worker records every automatic message as `simulated` and never calls a
  provider (`worker_tick()`, ~line 353). The `messages` table already has `status`, `mode`,
  `provider_ref`, `attempts` and a unique `dedupe` column.
- `sms_sandbox.py` and `sms_production_test.py` are guarded, single-message Africa's Talking tests.
- `requirements.txt` pins `africastalking==2.0.3`; `Dockerfile` copies both test modules.
- Railway runs Web (Gunicorn), Postgres and Worker (`worker.py`) services; worker is simulation-only.
- Docs and env templates reference only `AFRICASTALKING_*` variables.

## EgoSMS API facts (from developers.pahappa.com, 2026-09-29)

| Item | Value |
|---|---|
| Live send endpoint | `POST https://comms.egosms.co/api/v1/json/` |
| Sandbox send endpoint | `POST https://comms-test.pahappa.net/api/v1/json/` |
| Auth | `userdata.username` + `userdata.password` (the API key). From Comms → Settings → API Settings (KYC once). |
| Number format | International **without** leading `+` or `00`, e.g. `256700111222` |
| Sender ID | Optional; defaults to `EgoSMS`; **max 11 characters** |
| Priority | `0` (most urgent) … `4` (defer); default `1` |
| Batch limit | 1000 message objects per request |
| Success body | `{"Status":"OK","Cost":<number>,"MsgFollowUpUniqueCode":"<hex>"}` |
| Failure body | `{"Status":"Failed","Message":"<text>"}` — **HTTP is still 200** |
| Delivery reports | EgoSMS POSTs to your configured **Transaction Status** webhook |
| Webhook payload | `{"MsgFollowUpUniqueCode","number","Status" (e.g. "Success"),"deliveryDate"}` |
| Balance | `{"method":"Balance","userdata":{...}}` → `{"Status":"OK","Balance":<int>}` |
| Idempotency | **None documented** for `SendSms` — a transport failure may already have sent |

### Lessons the plan must respect

1. HTTP 200 does not mean success — always read `Status`.
2. A failed **API** call is not retryable as-is; a failed **transport** call may have sent already.
   Reconcile via `MsgFollowUpUniqueCode` / Transaction Status before resending.
3. Provider acceptance ≠ delivery. Only a webhook outcome proves delivery.

## Design

### Request shape (per batch)

```json
{
  "method": "SendSms",
  "userdata": { "username": "<EGOSMS_USERNAME>", "password": "<EGOSMS_API_KEY>" },
  "msgdata": [
    { "number": "256700111222", "message": "…", "senderid": "EgoSMS", "priority": 1 }
  ]
}
```

### Status model (aligns with AGENTS.md)

| Event | `messages.status` | `provider_ref` |
|---|---|---|
| Queued locally | `queued` | – |
| `SendSms` Status = OK | `accepted` | `MsgFollowUpUniqueCode` |
| `SendSms` Status = Failed | `failed` | Message stored in audit |
| HTTP/timeout transport error | `unknown` | – (reconcile before resend) |
| Webhook Status = `Success` | `delivered` | matched by code |
| Webhook other outcome | `failed` | matched by code |

## Files to change

### New
- **`egosms.py`** — provider client. No new dependency required (stdlib `urllib.request`), or use the
  official `comms-sdk`. Functions:
  - `normalize_number(phone)` → strip `+`/`00`, validate `256…`.
  - `send_messages(messages, *, username, api_key, sender_id, endpoint, priority=1, timeout=…)`
    → returns parsed `(ok, cost, follow_up_code)` or raises `EgoSmsError`.
  - `balance(...)` (optional, for a future low-balance warning).
  - Never logs credentials; returns only non-secret metadata.

### Modified
- **`sms_sandbox.py`** — repoint to `https://comms-test.pahappa.net/api/v1/json/`, read
  `EGOSMS_SANDBOX_USERNAME` / `EGOSMS_SANDBOX_API_KEY`, keep the one-fixed-message guard.
- **`sms_production_test.py`** — repoint to live endpoint, read `EGOSMS_*` + one configured test
  number, keep the enable-switch + `--confirm-send-one` locks.
- **`server.py`** —
  - `worker_tick()`: when `OPULENT_LIVE_SMS_ENABLED=true`, send via `egosms.py` and apply the status
    model; otherwise keep `simulated`. On transport error set `unknown` and do **not** auto-resend.
  - `snapshot()` / preview: report actual `sms_mode` (`live` when enabled, else `simulation`).
  - Add a delivery-report route `POST /webhooks/egosms/<EGOSMS_WEBHOOK_TOKEN>`: acknowledge 200
    immediately, then update the matching message and audit it.
- **`requirements.txt`** — remove `africastalking` (keep until cutover if a fallback is wanted).
- **`Dockerfile`** — add `egosms.py` to the COPY list.
- **`.github/workflows/verify.yml`** — keep test names; add `test_egosms`.
- **`railway.env.example`**, **`README.md`**, **`RAILWAY_GUIDE.md`**, **`IMPLEMENTATION_NOTES.md`**,
  **`VERIFICATION.md`** — update to EgoSMS.

### Tests
- **`test_egosms.py`** — number normalization; OK/Failed/transport parsing. Fake transport, no network.
- **`test_sms_sandbox.py`**, **`test_sms_production.py`** — rewrite against a fake EgoSMS transport:
  fixed message, single recipient, disabled-by-default lock, credential and format validation.
- Extend `test_system.py` for the status transitions and webhook matching.

## Configuration variables

| Variable | Service | Purpose |
|---|---|---|
| `EGOSMS_USERNAME` | Worker | Comms API username |
| `EGOSMS_API_KEY` | Worker | Comms API key (secret) |
| `EGOSMS_SENDER_ID` | Worker | Default `EgoSMS`; ≤11 chars; change later for custom ID |
| `EGOSMS_ENDPOINT` | Worker | Default live endpoint |
| `EGOSMS_SANDBOX_USERNAME` / `_API_KEY` | Worker | Sandbox-only smoke test credentials |
| `OPULENT_LIVE_SMS_ENABLED` | Worker | **`false`** until live sending is authorized |
| `EGOSMS_PRODUCTION_TEST_NUMBER` | Worker | One authorized test number |
| `OPULENT_PRODUCTION_SMS_TEST_ENABLED` | Worker | `false`; temporary for one test |
| `EGOSMS_WEBHOOK_TOKEN` | Web | Unguessable path segment for the delivery-report route |

**Secrets never go into Git, chat, or an AI prompt.** Set them in the Railway dashboard or CLI.

## Phased rollout

1. **Phase 1 — Config:** add EgoSMS variables in Railway; keep `OPULENT_LIVE_SMS_ENABLED=false`.
2. **Phase 2 — Sandbox test (no real phones):** `egosms.py` + rewritten `sms_sandbox.py`; run one
   fixed message against the sandbox endpoint. Unit tests with a fake transport.
3. **Phase 3 — Guarded production single message:** rewritten `sms_production_test.py`; one authorized
   number, temporarily enabled. Still not wired into reminders.
4. **Phase 4 — Live transport:** wire `worker_tick()` behind `OPULENT_LIVE_SMS_ENABLED`, with the
   status model, dedupe, bounded attempts and no blind resend.
5. **Phase 5 — Delivery reports:** webhook route + token; match by `MsgFollowUpUniqueCode`.
6. **Phase 6 — Docs, cleanup, Africa's Talking removal.**

## Test plan

- Unit: normalization, response parsing, guard rejections, status transitions, webhook matching.
- Sandbox: one fixed message to the EgoSMS sandbox; confirm `Status`/`Cost`/code.
- Guarded production: one message to one authorized number; enable, send, disable.
- Live dry run on staging with fictional contacts before any real client.
- Confirm quiet hours, duplicate protection and balance recheck still hold.

## Risks / open questions

- **No idempotency key** — duplicates are possible on transport failure; the plan relies on
  reconcile-before-resend. Confirm acceptable.
- **Sender ID is ≤11 chars** — a custom `Opulent`/`OPULENT` value must be registered/approved later.
- **Sandbox realism** — the EgoSMS sandbox may not mirror live delivery timing.
- **Balance monitoring** — messages fail silently if credits run out; consider a low-balance alert.
- **Webhook security** — public HTTPS endpoint; protect with an unguessable token and/or IP allowlist.
- **Keep or drop Africa's Talking files** — decided by the user at cutover.
