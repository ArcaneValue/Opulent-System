# Opulent Condo — Staff Guide

A short, practical guide to the Opulent condominium-fee system for the staff who use it.
You do **not** need to install any software from a file — Opulent runs in your web browser.

**Website address (keep this):** `https://opulent-web-production-67ba.up.railway.app`

---

## 1. Get set up (once, per person)

### a. Create your own account
Open the website address. If you don't have an account yet, click **“Create a staff account”**. Fill in:

- **Your name**
- **Staff email** (used to sign in — any email you can remember)
- **Password** — at least 12 characters, and different from everyone else's

Click **Create administrator account**. You are now an **Administrator** with full access, and you are signed in straight away.

> **Switching between the two screens:** on the sign-in page there is a **“Create a staff account”** link, and on the sign-up page a **“Sign in”** link — use them to move between the two at any time.

### b. Adding someone later (optional)
An administrator can also add a colleague from **Settings → Add staff** (name, staff email, an initial password and a role). But each person can equally create their own account using the steps above.

> **Passwords must be unique.** The system refuses an email that is already registered, and refuses a password that is already used on another account. This is a security feature — use a different password for each person.

### c. Install it on your laptop (recommended)
1. Open the website address in **Microsoft Edge**.
2. Sign in.
3. Open the Edge menu **(…)** → **Apps** → **Install this site as an app**.
4. Confirm and click **Install**. Pin it to your taskbar or Start menu.

Opulent now opens in its own window like an app. You can also just bookmark the address and use it in the browser.

---

## 2. How the work fits together

Opulent is built around four ideas:

| Step | What it means | Where |
|---|---|---|
| **Property & Units** | The building and each unit (e.g. Block A / A01) | Properties & Units |
| **Contacts** | The people who get reminders — tenants and owners, with phone numbers | Contacts |
| **Charges** | What each unit owes (condo fee, rent, or a one-off amount) | Charges |
| **Payments** | Money you have received | Payments |

Then **Reminders** turns unpaid charges into text messages.

**Every screen has a “? Help” button** in the top corner — it opens a short walkthrough for that page. The **User Guide** page lists all the walkthroughs in one place.

---

## 3. Register your buildings and people

### Add a property and its units
1. **Properties & Units → Add property** → name and address/location.
2. **Add unit** → choose the **property**, enter the **owner's name** (optional), and a **unit label** (e.g. A01).
   Each unit label must be unique within its property.
3. Use **Deactivate** for a unit you no longer bill — its history stays.

### Register tenants and owners
1. **Contacts → Register contact**.
2. Choose the unit, then **Tenant** or **Owner**.
3. Enter the name.
4. Enter the phone number as a **full international number beginning with +**, with no spaces — for example `+2567xxxxxxxx`.
5. Choose whether they receive reminders.
6. Optionally add an **alternate phone**, and the **billing start date**.
7. **Save**.

Use **Mute SMS** to stop messages for one person, or **Deactivate** when they leave.

---

## 4. Set the fees and record payments

### Set a monthly fee
1. **Charges → Set recurring fee** → unit, category (Condo Fee or Rent), monthly amount, due day, first period → **Save**.
2. Click **Generate a billing period** and choose the month to create the bills.
   Running the same month again never duplicates a charge.

> For a past amount or arrears, use **Charges → Add charge** and enter the original period, due date, amount and a reason.

### Record a payment
1. **Payments → Record payment**.
2. Choose the unit, the amount, the date received and a receipt/bank reference.
3. Save. The money is applied to the unit’s **oldest unpaid charges first**; anything left over stays as **credit** for future charges.

To fix a mistake, click **Reverse**, give a reason, then record the correct payment separately.

---

## 5. Send reminders

### Manually (you decide who and when)
1. Open **Reminders**.
2. Filter by month, unit, category or overdue.
3. Tick the charges you want to remind (or **Select outstanding**).
4. Optionally type a **notice** (up to 300 characters) — it is added only to charges that are already overdue.
5. Click **Preview selected**. Review every recipient, number, message and estimated cost.
6. Click **Send** (live) — messages go out to the real phones shown.

### Automatically (the system sends on schedule)
Automatic reminders are **enabled**. The server sends on its own:

- **7 days before** the due date,
- **on** the due date,
- then **every 7 days** while the charge stays unpaid.

Automatic reminders use **primary phone numbers only** and pause during **quiet hours** (default 18:00–08:00). Automatic sending runs on the hosted server, so it works even when your PC is off.

### What the message status means
| Status | Meaning |
|---|---|
| **queued** | Waiting to be sent |
| **accepted** | The provider took the message |
| **delivered** | The phone received it |
| **failed** | The provider refused it (check the number) |
| **unknown** | No response — needs a check before resending |
| **cancelled** | Data changed, so it was not sent (a good thing) |

---

## 6. Build and send a statement

Open **Statements** in the side menu.

1. Fill in the header — title, client, unit, monthly fee, period, totals.
2. Edit the table. Every cell is editable; use **+ Row** / **+ Column** to change its size. The default is 5 rows by 5 columns.
3. Optionally choose a unit and click **Fill from records** to copy its real quarterly charges and payments into the table, then edit anything.
4. Add your **Notes** and **Payment details** (one per line).
5. Click **Save**, then **Preview** to see what the tenant will see.
6. In **Send this statement**, pick a registered number or type one (e.g. `0772 494 627`), then click **Send SMS**. The tenant receives a link that opens the statement in any browser — no login needed.
7. **Statement history** below lists every send and its status.

Links are permanent unless you set an expiry date. The app refreshes itself every five minutes, so colleagues' new entries appear without signing out.

## 7. Passwords & security

- Use **at least 12 characters**, and a **different password for each person**.
- The system blocks duplicate emails and reused passwords.
- Change your password any time in **Settings → Change my password** (this signs you out everywhere).
- Staff sign-in is required to see any data. Residents need no account — they only receive SMS.
- Don’t share your login. If someone leaves, tell an administrator so their access can be handled.

---

## 8. Quick daily routine

1. **Sign in** and check the **Dashboard** — “Accounts requiring attention” shows who owes money.
2. **Record payments** as money comes in.
3. **Send reminders** for anything still outstanding (or let the automatic schedule handle it).
4. **Check the Reminders page** to see message statuses.

---

## 9. Need help?

- Click **? Help** on any screen for a short walkthrough.
- Open **User Guide** for the full list of walkthroughs.
- Remember: residents never log in — they just get a text message.
