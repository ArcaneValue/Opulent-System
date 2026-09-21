# Opulent condominium-fee reminder system — agent guidelines

These instructions apply throughout this project. This file lives in the project root as `AGENTS.md` so compatible coding agents discover it.

## Authorization to implement

- Default to discussion, suggestions, architecture, estimates, and explanations.
- Do not create or modify application code, install dependencies, change databases, deploy, or configure live services unless the user's current instruction explicitly uses the standalone word **implement** to authorize that work (case-insensitive).
- A quoted example, a reference document, or a request such as “do not implement” is not authorization. “Can you build it?” without **implement** remains a planning request.
- Authorization covers the specified scope only. Complete routine work within that scope without repeatedly asking permission; unrelated features need a new instruction.
- Explicit requests to create or revise planning documents, these guidelines, or concept images authorize those artifacts without authorizing the application itself.
- Never send live SMS, contact clients, or import real client records without explicit authorization for that action. Use fictional records and a provider sandbox for development.

## Product purpose and scope

- Build an internal Opulent staff system. Owners and tenants need no app, download, account, or login; they receive SMS reminders.
- Support properties, blocks, units, owner/tenant contacts, multiple contact numbers, billing periods, charges, payments, balances, and notification history.
- Make charge types configurable: start with condominium fees and allow rent and other categories later.
- Provide automatic scheduled reminders and manual reminders for selected current or historical periods. Manual sends must show recipients, period, message, and estimated cost before confirmation.
- Register and validate phone numbers with an explicit country code. A phone number is a contact address, not a unique identity or login credential.
- Keep currency, country, timezone, billing rules, and SMS provider configurable. UGX in examples is illustrative until confirmed.

## Recommended architecture

- Start with an online-first, staff-only progressive web app (PWA) installable on Windows PCs, a central backend, a relational database, and a persistent server-side reminder worker.
- Keep financial records authoritative on the server. Do not create separate databases on staff PCs or depend on an open browser for scheduled sending.
- Enforce staff authentication and role permissions on the backend; hiding navigation or installation links is insufficient.
- Publish updates centrally with versioned caching and a safe refresh prompt. Protect unsaved work and maintain compatibility during rollout.
- Treat a packaged desktop installer or full offline editing as later scope unless the user explicitly requires it.

## Correctness and reliability

- Track charges and payment allocations explicitly. Use exact decimal amounts or integer minor units; never floating-point arithmetic for money.
- Define partial payments, credits, overpayments, reversals, and opening arrears before implementation. Never silently alter past bills when a recurring fee changes.
- Import historical arrears as traceable records; avoid counting both an opening balance and the same historic charges.
- Recalculate outstanding balances before sending and skip cleared charges. Define how simultaneous payments and sends are handled.
- Make charge generation and message scheduling idempotent. Use persistent jobs, bounded retries, and duplicate prevention; reconcile uncertain provider responses before resending.
- Distinguish queued, provider-accepted, delivered, failed, and unknown SMS states. Provider acceptance does not prove delivery or that the recipient read it.
- Store provider credentials only on the server. Record sender, recipients, billing period, message snapshot, provider reference, and outcome in an audit trail.
- Configure reminder timing, quiet hours, contact preferences, and permitted recipients. Confirm local messaging requirements and provider support before production use.
- Restrict access to personal and financial data, minimize sensitive message content, back up records, and verify restoration.

## Working method and explanations

- Prioritize a dependable usable workflow before decorative design. Concept images are proposals; incorporate the user's later templates before finalizing the visual design.
- State assumptions and unresolved decisions. Ask focused questions only when they materially affect scope or correctness.
- For a complex task or major change, explain in plain language: what changed, how information moves through the system, why the approach was chosen, how it was verified, and any limitations or next steps.
- Put these explanation requirements here; store evolving architecture and change explanations in separate project documents and summarize them in chat.
- Take the time needed for correctness without promising zero mistakes. Run meaningful checks for balance calculations, payment allocation, duplicate prevention, staff access, reminder selection, and update behavior when those features are implemented.
- Report completed work and test evidence accurately. Never describe an untested concept as production-ready.
