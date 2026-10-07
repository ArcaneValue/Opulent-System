"""Opulent billing backend. Reminder delivery is simulated unless OPULENT_LIVE_SMS_ENABLED=true."""
import calendar
import csv
import hashlib
import hmac
import html
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

try:
    import psycopg
    INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError)
except ImportError:
    INTEGRITY_ERRORS = (sqlite3.IntegrityError,)

ROOT = Path(__file__).resolve().parent
DB = Path(os.environ.get('OPULENT_DB', str(ROOT / 'data' / 'opulent.sqlite3')))
DATABASE_URL = os.environ.get('DATABASE_URL', '')
VERSION = '1.11.0-pilot'
LOCK = threading.RLock()
FAILED_LOGINS = {}


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


@contextmanager
def connect(write=False):
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row
        connection = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        try:
            yield PostgresConnection(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return
    with LOCK:
        c = sqlite3.connect(DB, timeout=15)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                c.execute('BEGIN IMMEDIATE')
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()


class PostgresConnection:
    """Small compatibility layer for the application's parameterized SQL."""
    def __init__(self, connection):
        self.connection = connection

    @staticmethod
    def sql(statement):
        # psycopg uses percent-style binding; preserve SQL LIKE wildcards.
        statement = statement.replace('%', '%%').replace('?', '%s')
        if statement.lstrip().upper().startswith('INSERT OR IGNORE'):
            statement = re.sub(r'INSERT\s+OR\s+IGNORE', 'INSERT', statement, count=1, flags=re.I)
            statement = statement.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
        return statement

    def execute(self, statement, args=()):
        return self.connection.execute(self.sql(statement), args)

    def executemany(self, statement, args):
        return self.connection.cursor().executemany(self.sql(statement), args, returning=False)


def rows(c, sql, args=()):
    output = []
    for row in c.execute(sql, args).fetchall():
        item = dict(row)
        for key, value in item.items():
            if isinstance(value, Decimal) and value == value.to_integral_value():
                item[key] = int(value)
        output.append(item)
    return output


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def password_hash(password, salt=None):
    if not isinstance(password, str) or not 12 <= len(password) <= 200:
        raise Problem('Use a password between 12 and 200 characters.')
    salt = salt or secrets.token_hex(16)
    return salt + ':' + hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 310000).hex()


def password_ok(password, stored):
    try:
        return hmac.compare_digest(password_hash(password, stored.split(':')[0]), stored)
    except (ValueError, Problem):
        return False


def password_reused(c, password):
    """True when any existing staff account already uses this exact password."""
    return any(password_ok(password, row['password']) for row in rows(c, 'SELECT password FROM users'))


def text(d, key, limit=120):
    value = str(d.get(key, '')).strip()
    if not value or len(value) > limit or any(ord(ch) < 32 for ch in value):
        raise Problem(f'{key.replace("_", " ").capitalize()} is required (maximum {limit} characters).')
    return value


def number(d, key, low=1, high=2147483647):
    value = d.get(key)
    if isinstance(value, bool) or not str(value).isdigit() or not low <= int(value) <= high:
        raise Problem(f'Invalid {key.replace("_", " ")}.')
    return int(value)


def money(value):
    try:
        amount = Decimal(str(value).replace(',', '').strip())
        if not amount.is_finite() or amount <= 0 or amount > Decimal('1000000000000') or amount * 100 != (amount * 100).to_integral():
            raise Problem('Amount must be positive with at most two decimal places.')
        return int(amount * 100)
    except (InvalidOperation, ValueError):
        raise Problem('Enter a valid amount.')


def iso_date(value):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise Problem('Enter a valid date.')


def period(value):
    if not re.fullmatch(r'\d{4}-\d{2}', str(value)):
        raise Problem('Billing period must be YYYY-MM.')
    iso_date(str(value) + '-01')
    return value


def audit(c, actor, action, detail):
    c.execute('INSERT INTO audit(actor,action,detail,created) VALUES(?,?,?,?)', (actor, action, json.dumps(detail), stamp()))


SCHEMA = '''
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT CHECK(role IN ('admin','billing','viewer')) NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),csrf TEXT,expires REAL);
CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),currency TEXT NOT NULL DEFAULT 'UGX',country TEXT NOT NULL DEFAULT 'UG',utc_offset INTEGER NOT NULL DEFAULT 180,automatic INTEGER NOT NULL DEFAULT 0,lead_days INTEGER NOT NULL DEFAULT 7,repeat_days INTEGER NOT NULL DEFAULT 7,quiet_start INTEGER NOT NULL DEFAULT 18,quiet_end INTEGER NOT NULL DEFAULT 8,segment_price INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS properties(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,address TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS units(id INTEGER PRIMARY KEY,property_id INTEGER NOT NULL REFERENCES properties(id),block TEXT NOT NULL,label TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,owner TEXT NOT NULL DEFAULT '',UNIQUE(property_id,block,label));
CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY,unit_id INTEGER NOT NULL REFERENCES units(id),name TEXT NOT NULL,phone TEXT NOT NULL,kind TEXT CHECK(kind IN ('Tenant','Owner')) NOT NULL,notify INTEGER NOT NULL DEFAULT 1,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS charge_types(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY,unit_id INTEGER NOT NULL REFERENCES units(id),type_id INTEGER NOT NULL REFERENCES charge_types(id),amount INTEGER NOT NULL CHECK(amount>0),due_day INTEGER NOT NULL CHECK(due_day BETWEEN 1 AND 31),start_period TEXT NOT NULL,end_period TEXT,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS charges(id INTEGER PRIMARY KEY,unit_id INTEGER NOT NULL REFERENCES units(id),type_id INTEGER NOT NULL REFERENCES charge_types(id),period TEXT NOT NULL,due TEXT NOT NULL,amount INTEGER NOT NULL CHECK(amount>0),source TEXT NOT NULL,created TEXT NOT NULL,UNIQUE(unit_id,type_id,period));
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY,unit_id INTEGER NOT NULL REFERENCES units(id),amount INTEGER NOT NULL CHECK(amount>0),paid_on TEXT NOT NULL,reference TEXT NOT NULL,request_key TEXT UNIQUE NOT NULL,reversed INTEGER NOT NULL DEFAULT 0,reason TEXT,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS payment_receipt_sends(id INTEGER PRIMARY KEY,payment_id INTEGER NOT NULL REFERENCES payments(id),phone TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL,mode TEXT NOT NULL,provider_ref TEXT,detail TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS allocations(payment_id INTEGER REFERENCES payments(id),charge_id INTEGER REFERENCES charges(id),amount INTEGER NOT NULL CHECK(amount>0),PRIMARY KEY(payment_id,charge_id));
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,charge_id INTEGER NOT NULL REFERENCES charges(id),contact_id INTEGER NOT NULL REFERENCES contacts(id),phone TEXT NOT NULL,body TEXT NOT NULL,balance INTEGER NOT NULL,dedupe TEXT UNIQUE NOT NULL,status TEXT NOT NULL DEFAULT 'queued',mode TEXT NOT NULL DEFAULT 'simulation',actor TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,provider_ref TEXT,created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS previews(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),payload TEXT,expires REAL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS statements(id INTEGER PRIMARY KEY,title TEXT NOT NULL DEFAULT '',client TEXT NOT NULL DEFAULT '',unit_label TEXT NOT NULL DEFAULT '',monthly_fee TEXT NOT NULL DEFAULT '',period TEXT NOT NULL DEFAULT '',total_received TEXT NOT NULL DEFAULT '',total_due TEXT NOT NULL DEFAULT '',columns_json TEXT NOT NULL DEFAULT '[]',rows_json TEXT NOT NULL DEFAULT '[]',notes_json TEXT NOT NULL DEFAULT '[]',payment_json TEXT NOT NULL DEFAULT '[]',token TEXT UNIQUE NOT NULL,expires TEXT,created TEXT NOT NULL,updated TEXT NOT NULL,actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS statement_sends(id INTEGER PRIMARY KEY,statement_id INTEGER NOT NULL REFERENCES statements(id),phone TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',mode TEXT NOT NULL DEFAULT 'simulation',provider_ref TEXT,detail TEXT NOT NULL DEFAULT '',snapshot_json TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE VIEW IF NOT EXISTS charge_balances AS SELECT ch.*,COALESCE((SELECT SUM(a.amount) FROM allocations a JOIN payments p ON p.id=a.payment_id WHERE a.charge_id=ch.id AND p.reversed=0),0) paid,ch.amount-COALESCE((SELECT SUM(a.amount) FROM allocations a JOIN payments p ON p.id=a.payment_id WHERE a.charge_id=ch.id AND p.reversed=0),0) remaining FROM charges ch;
'''

POSTGRES_SCHEMA = '''
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT CHECK(role IN ('admin','billing','viewer')) NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id BIGINT REFERENCES users(id),csrf TEXT,expires DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),currency TEXT NOT NULL DEFAULT 'UGX',country TEXT NOT NULL DEFAULT 'UG',utc_offset INTEGER NOT NULL DEFAULT 180,automatic INTEGER NOT NULL DEFAULT 0,lead_days INTEGER NOT NULL DEFAULT 7,repeat_days INTEGER NOT NULL DEFAULT 7,quiet_start INTEGER NOT NULL DEFAULT 18,quiet_end INTEGER NOT NULL DEFAULT 8,segment_price BIGINT NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS properties(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,name TEXT UNIQUE NOT NULL,address TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS units(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,property_id BIGINT NOT NULL REFERENCES properties(id),block TEXT NOT NULL,label TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,owner TEXT NOT NULL DEFAULT '',UNIQUE(property_id,block,label));
CREATE TABLE IF NOT EXISTS contacts(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,unit_id BIGINT NOT NULL REFERENCES units(id),name TEXT NOT NULL,phone TEXT NOT NULL,kind TEXT CHECK(kind IN ('Tenant','Owner')) NOT NULL,notify INTEGER NOT NULL DEFAULT 1,active INTEGER NOT NULL DEFAULT 1,alternate_phone TEXT NOT NULL DEFAULT '',billing_start TEXT);
CREATE TABLE IF NOT EXISTS charge_types(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS plans(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,unit_id BIGINT NOT NULL REFERENCES units(id),type_id BIGINT NOT NULL REFERENCES charge_types(id),amount BIGINT NOT NULL CHECK(amount>0),due_day INTEGER NOT NULL CHECK(due_day BETWEEN 1 AND 31),start_period TEXT NOT NULL,end_period TEXT,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS charges(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,unit_id BIGINT NOT NULL REFERENCES units(id),type_id BIGINT NOT NULL REFERENCES charge_types(id),period TEXT NOT NULL,due TEXT NOT NULL,amount BIGINT NOT NULL CHECK(amount>0),source TEXT NOT NULL,created TEXT NOT NULL,UNIQUE(unit_id,type_id,period));
CREATE TABLE IF NOT EXISTS payments(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,unit_id BIGINT NOT NULL REFERENCES units(id),amount BIGINT NOT NULL CHECK(amount>0),paid_on TEXT NOT NULL,reference TEXT NOT NULL,request_key TEXT UNIQUE NOT NULL,reversed INTEGER NOT NULL DEFAULT 0,reason TEXT,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS payment_receipt_sends(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,payment_id BIGINT NOT NULL REFERENCES payments(id),phone TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL,mode TEXT NOT NULL,provider_ref TEXT,detail TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS allocations(payment_id BIGINT REFERENCES payments(id),charge_id BIGINT REFERENCES charges(id),amount BIGINT NOT NULL CHECK(amount>0),PRIMARY KEY(payment_id,charge_id));
CREATE TABLE IF NOT EXISTS messages(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,charge_id BIGINT NOT NULL REFERENCES charges(id),contact_id BIGINT NOT NULL REFERENCES contacts(id),phone TEXT NOT NULL,body TEXT NOT NULL,balance BIGINT NOT NULL,dedupe TEXT UNIQUE NOT NULL,status TEXT NOT NULL DEFAULT 'queued',mode TEXT NOT NULL DEFAULT 'simulation',actor TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,provider_ref TEXT,created TEXT NOT NULL,updated TEXT NOT NULL,penalty TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS previews(token TEXT PRIMARY KEY,user_id BIGINT REFERENCES users(id),payload TEXT,expires DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS audit(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS statements(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,title TEXT NOT NULL DEFAULT '',client TEXT NOT NULL DEFAULT '',unit_label TEXT NOT NULL DEFAULT '',monthly_fee TEXT NOT NULL DEFAULT '',period TEXT NOT NULL DEFAULT '',total_received TEXT NOT NULL DEFAULT '',total_due TEXT NOT NULL DEFAULT '',columns_json TEXT NOT NULL DEFAULT '[]',rows_json TEXT NOT NULL DEFAULT '[]',notes_json TEXT NOT NULL DEFAULT '[]',payment_json TEXT NOT NULL DEFAULT '[]',token TEXT UNIQUE NOT NULL,expires TEXT,created TEXT NOT NULL,updated TEXT NOT NULL,actor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS statement_sends(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,statement_id BIGINT NOT NULL REFERENCES statements(id),phone TEXT NOT NULL,body TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',mode TEXT NOT NULL DEFAULT 'simulation',provider_ref TEXT,detail TEXT NOT NULL DEFAULT '',snapshot_json TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE OR REPLACE VIEW charge_balances AS SELECT ch.*,COALESCE((SELECT SUM(a.amount) FROM allocations a JOIN payments p ON p.id=a.payment_id WHERE a.charge_id=ch.id AND p.reversed=0),0) paid,ch.amount-COALESCE((SELECT SUM(a.amount) FROM allocations a JOIN payments p ON p.id=a.payment_id WHERE a.charge_id=ch.id AND p.reversed=0),0) remaining FROM charges ch;
'''


def init_db():
    if DATABASE_URL:
        with connect(True) as c:
            for statement in POSTGRES_SCHEMA.split(';'):
                if statement.strip():
                    c.execute(statement)
            c.execute('INSERT INTO schema_migrations(version,applied_at) VALUES(1,?) ON CONFLICT(version) DO NOTHING', (stamp(),))
            c.execute("ALTER TABLE units ADD COLUMN IF NOT EXISTS owner TEXT NOT NULL DEFAULT ''")
            c.execute("ALTER TABLE statement_sends ADD COLUMN IF NOT EXISTS detail TEXT NOT NULL DEFAULT ''")
            c.execute("ALTER TABLE statement_sends ADD COLUMN IF NOT EXISTS snapshot_json TEXT NOT NULL DEFAULT ''")
            c.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS client_name TEXT NOT NULL DEFAULT ''")
            c.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS billing_period TEXT NOT NULL DEFAULT ''")
            c.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS receipt_phone TEXT NOT NULL DEFAULT ''")
            c.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS receipt_token TEXT UNIQUE")
            c.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS receipt_snapshot TEXT NOT NULL DEFAULT ''")
            c.execute('INSERT INTO settings(id) VALUES(1) ON CONFLICT(id) DO NOTHING')
            c.executemany('INSERT INTO charge_types(name) VALUES(?) ON CONFLICT(name) DO NOTHING', [('Condo Fee',), ('Rent',)])
        return
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript(SCHEMA)
        c.execute('INSERT OR IGNORE INTO settings(id) VALUES(1)')
        c.executemany('INSERT OR IGNORE INTO charge_types(name) VALUES(?)', [('Condo Fee',), ('Rent',)])
        # Additive migration: preserve existing contact/payment/charge records.
        contact_columns = {r['name'] for r in c.execute('PRAGMA table_info(contacts)')}
        if 'alternate_phone' not in contact_columns:
            c.execute("ALTER TABLE contacts ADD COLUMN alternate_phone TEXT NOT NULL DEFAULT ''")
        if 'billing_start' not in contact_columns:
            c.execute('ALTER TABLE contacts ADD COLUMN billing_start TEXT')
        if 'penalty' not in {r['name'] for r in c.execute('PRAGMA table_info(messages)')}:
            c.execute("ALTER TABLE messages ADD COLUMN penalty TEXT NOT NULL DEFAULT ''")
        if 'owner' not in {r['name'] for r in c.execute('PRAGMA table_info(units)')}:
            c.execute("ALTER TABLE units ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
        if 'detail' not in {r['name'] for r in c.execute('PRAGMA table_info(statement_sends)')}:
            c.execute("ALTER TABLE statement_sends ADD COLUMN detail TEXT NOT NULL DEFAULT ''")
        if 'snapshot_json' not in {r['name'] for r in c.execute('PRAGMA table_info(statement_sends)')}:
            c.execute("ALTER TABLE statement_sends ADD COLUMN snapshot_json TEXT NOT NULL DEFAULT ''")
        payment_columns = {r['name'] for r in c.execute('PRAGMA table_info(payments)')}
        for column, definition in (('client_name', "TEXT NOT NULL DEFAULT ''"), ('billing_period', "TEXT NOT NULL DEFAULT ''"),
                                   ('receipt_phone', "TEXT NOT NULL DEFAULT ''"), ('receipt_token', 'TEXT'),
                                   ('receipt_snapshot', "TEXT NOT NULL DEFAULT ''")):
            if column not in payment_columns:
                c.execute(f'ALTER TABLE payments ADD COLUMN {column} {definition}')
        c.execute('CREATE UNIQUE INDEX IF NOT EXISTS payments_receipt_token_idx ON payments(receipt_token)')
        # Old previews did not contain the new recipient/notice options.
        if c.execute('PRAGMA user_version').fetchone()[0] < 2:
            c.execute('DELETE FROM previews')
            c.execute('PRAGMA user_version=2')


def settings(c):
    return dict(c.execute('SELECT * FROM settings WHERE id=1').fetchone())


def today(c):
    return (datetime.now(timezone.utc) + timedelta(minutes=settings(c)['utc_offset'])).date()


def charge_list(c):
    return rows(c, '''SELECT b.*,u.label unit,u.block,p.name property,t.name type FROM charge_balances b JOIN units u ON u.id=b.unit_id JOIN properties p ON p.id=u.property_id JOIN charge_types t ON t.id=b.type_id ORDER BY b.due,b.id''')


def apply_credit(c, unit_id):
    # Oldest charge first; reversals never erase the original payment or its audit.
    credits = rows(c, '''SELECT p.id,p.amount-COALESCE(SUM(a.amount),0) available FROM payments p LEFT JOIN allocations a ON a.payment_id=p.id WHERE p.unit_id=? AND p.reversed=0 GROUP BY p.id HAVING p.amount-COALESCE(SUM(a.amount),0)>0 ORDER BY p.paid_on,p.id''', (unit_id,))
    for payment in credits:
        available = payment['available']
        for charge in rows(c, 'SELECT id,remaining FROM charge_balances WHERE unit_id=? AND remaining>0 ORDER BY due,id', (unit_id,)):
            take = min(available, charge['remaining'])
            c.execute('INSERT INTO allocations(payment_id,charge_id,amount) VALUES(?,?,?) ON CONFLICT(payment_id,charge_id) DO UPDATE SET amount=allocations.amount+excluded.amount', (payment['id'], charge['id'], take))
            available -= take
            if not available:
                break


def generate(c, billing_period, actor):
    period(billing_period)
    year, month = map(int, billing_period.split('-'))
    created = 0
    for plan in rows(c, '''SELECT p.* FROM plans p JOIN units u ON u.id=p.unit_id WHERE p.active=1 AND u.active=1 AND p.start_period<=? AND (p.end_period IS NULL OR p.end_period>=?)''', (billing_period, billing_period)):
        due = date(year, month, min(plan['due_day'], calendar.monthrange(year, month)[1])).isoformat()
        result = c.execute('INSERT OR IGNORE INTO charges(unit_id,type_id,period,due,amount,source,created) VALUES(?,?,?,?,?,?,?)', (plan['unit_id'], plan['type_id'], billing_period, due, plan['amount'], 'Recurring plan', stamp()))
        created += result.rowcount
        apply_credit(c, plan['unit_id'])
    if created:
        audit(c, actor, 'generate_charges', {'period': billing_period, 'created': created})
    return created


def rendered_message(c, charge, contact, penalty=''):
    s = settings(c)
    def fmt(value):
        return f'{s["currency"]} {Decimal(value)/100:,.2f}'
    body = f'Opulent: {charge["unit"]} {charge["type"]} for {charge["period"]}. Charged: {fmt(charge["amount"])}. Paid: {fmt(charge["paid"])}. Remaining: {fmt(charge["remaining"])}. Due {charge["due"]}.'
    return body + (' Notice: ' + penalty if penalty and charge['due'] < today(c).isoformat() else '')


def preview_items(c, ids, penalty='', include_alternate=False):
    items = []
    seen = set()
    for charge in charge_list(c):
        if charge['id'] not in ids or charge['remaining'] <= 0:
            continue
        if not c.execute('SELECT 1 FROM units WHERE id=? AND active=1', (charge['unit_id'],)).fetchone():
            continue
        for contact in rows(c, 'SELECT * FROM contacts WHERE unit_id=? AND active=1 AND notify=1 ORDER BY id', (charge['unit_id'],)):
            body = rendered_message(c, charge, contact, penalty)
            phones = [(contact['phone'], 'Primary')]
            if include_alternate and contact['alternate_phone']:
                phones.append((contact['alternate_phone'], 'Alternate'))
            for phone, recipient_type in phones:
                if (charge['id'], phone) in seen:
                    continue
                seen.add((charge['id'], phone))
                applied_penalty = penalty if charge['due'] < today(c).isoformat() else ''
                items.append({'charge_id': charge['id'], 'contact_id': contact['id'], 'name': contact['name'], 'phone': phone, 'recipient_type': recipient_type, 'unit': charge['unit'], 'period': charge['period'], 'body': body, 'balance': charge['remaining'], 'segments': sms_segments(body), 'penalty': applied_penalty})
    return items


def sms_segments(body):
    # Conservative estimate. Provider encoding/pricing must be verified before live use.
    gsm = "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
    extension = '^{}\\[~]|€'
    if all(ch in gsm or ch in extension for ch in body):
        length = sum(2 if ch in extension else 1 for ch in body)
        return 1 if length <= 160 else (length + 152) // 153
    length = len(body.encode('utf-16-be')) // 2
    return 1 if length <= 70 else (length + 66) // 67


def queue(c, items, actor, key):
    count = 0
    for item in items:
        legacy_dedupe = f'{key}:{item["charge_id"]}:{item["contact_id"]}'
        if c.execute('SELECT 1 FROM messages WHERE dedupe=?',(legacy_dedupe,)).fetchone():
            continue
        dedupe = f'{key}:{item["charge_id"]}:{item["contact_id"]}:{item["phone"]}'
        result = c.execute('INSERT OR IGNORE INTO messages(charge_id,contact_id,phone,body,balance,dedupe,actor,created,updated,penalty) VALUES(?,?,?,?,?,?,?,?,?,?)', (item['charge_id'], item['contact_id'], item['phone'], item['body'], item['balance'], dedupe, actor, stamp(), stamp(), item.get('penalty','')))
        count += result.rowcount
    return count


def reminder_due(on_date, due_date, lead_days, repeat_days):
    """Pre-due notice once; due-day and overdue notices anchored to the due date."""
    days_overdue = (on_date - due_date).days
    return days_overdue == -lead_days or (days_overdue >= 0 and days_overdue % repeat_days == 0)


def live_sms_enabled():
    return os.environ.get('OPULENT_LIVE_SMS_ENABLED', '').strip().lower() == 'true'


def sms_mode():
    return 'live' if live_sms_enabled() else 'simulation'


def deliver_message(message):
    """Send one reminder through EgoSMS; returns (status, provider_ref, detail).

    Transport failures become 'unknown' and are deliberately never retried
    automatically. The outcome is reconciled through the follow-up code before
    any resend, because EgoSMS offers no idempotency key.
    """
    import egosms
    try:
        result = egosms.send_one(
            message['phone'], message['body'],
            username=os.environ.get('EGOSMS_USERNAME', '').strip(),
            api_key=os.environ.get('EGOSMS_API_KEY', '').strip(),
            sender_id=os.environ.get('EGOSMS_SENDER_ID', egosms.DEFAULT_SENDER_ID),
            endpoint=os.environ.get('EGOSMS_ENDPOINT', egosms.LIVE_ENDPOINT),
        )
    except egosms.EgoSmsTransportError:
        return 'unknown', None, {}
    except egosms.EgoSmsError as exc:
        return 'failed', None, {'error': str(exc)[:200]}
    return 'accepted', result['follow_up_code'], {'cost': result['cost']}


def apply_delivery_report(c, payload):
    """Record an EgoSMS Transaction Status report against the matching message."""
    code = str(payload.get('MsgFollowUpUniqueCode', '')).strip()
    outcome = str(payload.get('Status', '')).strip()
    if not code:
        return 0
    status = 'delivered' if outcome.lower() == 'success' else 'failed'
    updated = c.execute('UPDATE messages SET status=?,updated=? WHERE provider_ref=?', (status, stamp(), code)).rowcount
    updated += c.execute('UPDATE payment_receipt_sends SET status=?,updated=? WHERE provider_ref=?', (status, stamp(), code)).rowcount
    audit(c, 'egosms', 'delivery_' + status, {'code': code, 'outcome': outcome, 'updated': updated})
    return updated


def normalize_phone(value):
    """Accept 0772..., 256772..., or +256772... and return the +256... form."""
    digits = re.sub(r'[\s()\-\.]', '', str(value or ''))
    if digits.startswith('+'):
        normalized = digits
    elif digits.startswith('00'):
        normalized = '+' + digits[2:]
    elif digits.startswith('0'):
        normalized = '+256' + digits[1:]
    elif digits.startswith('256'):
        normalized = '+' + digits
    else:
        normalized = '+' + digits
    if not re.fullmatch(r'\+[1-9]\d{7,14}', normalized):
        raise Problem('Enter a phone number such as 0772 494 627 or +256772494627.')
    return normalized


def statement_link(token):
    base = os.environ.get('OPULENT_PUBLIC_URL', '').rstrip('/')
    return f'{base}/s/{token}'


def receipt_link(token):
    base = os.environ.get('OPULENT_PUBLIC_URL', '').rstrip('/')
    return f'{base}/r/{token}'


def receipt_snapshot(c, payment_id):
    payment = c.execute('''SELECT p.*,u.label unit,u.owner,pr.name property FROM payments p
                           JOIN units u ON u.id=p.unit_id JOIN properties pr ON pr.id=u.property_id
                           WHERE p.id=?''', (payment_id,)).fetchone()
    applied = rows(c, '''SELECT ch.period,ch.due,t.name type,a.amount FROM allocations a
                         JOIN charges ch ON ch.id=a.charge_id JOIN charge_types t ON t.id=ch.type_id
                         WHERE a.payment_id=? ORDER BY ch.due,ch.id''', (payment_id,))
    outstanding = rows(c, '''SELECT ch.period,ch.due,t.name type,ch.remaining FROM charge_balances ch
                             JOIN charge_types t ON t.id=ch.type_id
                             WHERE ch.unit_id=? AND ch.remaining>0 ORDER BY ch.due,ch.id''', (payment['unit_id'],))
    credit = int(c.execute('''SELECT COALESCE(SUM(p.amount-COALESCE((SELECT SUM(a.amount) FROM allocations a WHERE a.payment_id=p.id),0)),0) AS total
                               FROM payments p WHERE p.unit_id=? AND p.reversed=0''', (payment['unit_id'],)).fetchone()['total'])
    return {'payment_id': payment_id, 'property': payment['property'], 'unit': payment['unit'],
            'client': payment['client_name'], 'billing_period': payment['billing_period'],
            'paid_on': payment['paid_on'], 'reference': payment['reference'], 'currency': settings(c)['currency'],
            'amount': payment['amount'], 'allocated': applied, 'outstanding': outstanding,
            'balance_after': sum(item['remaining'] for item in outstanding), 'credit_after': credit,
            'recorded_at': payment['created']}


def receipt_sms_body(snapshot, token):
    amount = f'{Decimal(snapshot["amount"])/100:,.2f}'
    balance = f'{Decimal(snapshot["balance_after"])/100:,.2f}'
    return f'Opulent receipt: {snapshot["currency"]} {amount} received for Unit {snapshot["unit"]}. Balance after payment: {snapshot["currency"]} {balance}. View receipt: {receipt_link(token)}'


def receipt_page(snapshot, reversed_payment=False):
    def amount(value):
        return f'{_esc(snapshot["currency"])} {Decimal(value)/100:,.2f}'
    fields = (('Client', snapshot['client']), ('Property', snapshot['property']), ('Unit', snapshot['unit']),
              ('Payment quarter (staff label)', snapshot['billing_period']), ('Amount received', amount(snapshot['amount'])),
              ('Payment date', snapshot['paid_on']), ('Reference', snapshot['reference']),
              ('Balance after this payment', amount(snapshot['balance_after'])), ('Credit after this payment', amount(snapshot['credit_after'])))
    details = ''.join(f'<div class="f"><span>{_esc(label)}</span><b>{_esc(value)}</b></div>' for label,value in fields)
    applied = ''.join(f'<tr><td>{_esc(item["type"])}</td><td>{_esc(item["period"])}</td><td>{_esc(item["due"])}</td><td>{amount(item["amount"])}</td></tr>' for item in snapshot['allocated'])
    outstanding = ''.join(f'<tr><td>{_esc(item["type"])}</td><td>{_esc(item["period"])}</td><td>{_esc(item["due"])}</td><td>{amount(item["remaining"])}</td></tr>' for item in snapshot['outstanding'])
    warning = '<p class="warning">This payment was reversed. This receipt is void.</p>' if reversed_payment else ''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Opulent payment receipt</title>
<style>body{{font-family:Segoe UI,system-ui,sans-serif;color:#173247;background:#f3f6f9;margin:0;padding:18px}}.card{{max-width:850px;margin:auto;background:white;border:1px solid #dbe4eb;border-radius:12px;padding:26px}}.brand{{font:600 22px Georgia,serif;letter-spacing:2px;color:#102c42}}h1{{font-size:22px}}.f{{display:flex;gap:10px;margin:7px 0}}.f span{{min-width:220px;color:#6b7e8e}}table{{width:100%;border-collapse:collapse;margin:14px 0}}th,td{{border:1px solid #ccd9e3;padding:8px;text-align:left}}th{{background:#f0f4f8}}.warning{{background:#fff0ed;color:#8a2424;padding:12px;border-radius:8px}}@media(max-width:600px){{.f{{display:block}}.f span{{display:block}}}}</style></head><body><main class="card"><div class="brand">OPULENT</div><h1>Payment receipt</h1>{warning}{details}<h2>Applied to charges</h2>{'<table><tr><th>Category</th><th>Period</th><th>Due date</th><th>Amount applied</th></tr>'+applied+'</table>' if applied else '<p>No charge allocation yet; the payment is account credit.</p>'}<h2>Outstanding after payment</h2>{'<table><tr><th>Category</th><th>Period</th><th>Due date</th><th>Remaining</th></tr>'+outstanding+'</table>' if outstanding else '<p>No outstanding charges at the time this payment was recorded.</p>'}<p>Payments cover the oldest unpaid charges first. The selected quarter is a staff label and may differ from the charges listed above.</p><p style="font-size:12px;color:#6b7e8e">This is a snapshot from {_esc(snapshot['recorded_at'])}. Later transactions may change the current account balance.</p></main></body></html>'''


def statement_sms_body(row):
    label = row['unit_label'] or row['client'] or 'your unit'
    return f'Opulent: Condominium fee statement for {label} is ready. View it here: {statement_link(row["token"])}'


def statement_snapshot(row):
    """Preserve exactly the statement fields visible when a send is recorded."""
    fields = ('title', 'client', 'unit_label', 'monthly_fee', 'period', 'total_received',
              'total_due', 'columns_json', 'rows_json', 'notes_json', 'payment_json')
    return json.dumps({field: row[field] for field in fields})


def _esc(value):
    return html.escape(str(value if value is not None else ''))


def statement_page(row):
    """A read-only HTML statement for the tenant to open in any browser."""
    columns = json.loads(row['columns_json'] or '[]')
    rows_data = json.loads(row['rows_json'] or '[]')
    notes = json.loads(row['notes_json'] or '[]')
    payment = json.loads(row['payment_json'] or '[]')
    head = ''.join(f'<th>{_esc(c)}</th>' for c in columns)
    body = ''
    for item in rows_data:
        cells = ''.join(f'<td>{_esc(x)}</td>' for x in item.get('cells', []))
        body += f'<tr><th scope="row">{_esc(item.get("label"))}</th>{cells}</tr>'
    fields = ''.join(f'<div class="f"><span>{_esc(label)}</span><b>{_esc(value)}</b></div>' for label, value in (
        ('Client', row['client']), ('Unit', row['unit_label']), ('Monthly Condo fee', row['monthly_fee']), ('Statement Period', row['period']),
        ('Total Payment Received', row['total_received']), ('Total Amount Due', row['total_due'])))
    notes_html = ''.join(f'<li>{_esc(n)}</li>' for n in notes)
    payment_html = ''.join(f'<div>{_esc(p)}</div>' for p in payment)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(row['title'])}</title>
<style>
body{{font-family:Segoe UI,system-ui,sans-serif;color:#173247;background:#f3f6f9;margin:0;padding:18px}}
.card{{max-width:900px;margin:0 auto;background:#fff;border:1px solid #dbe4eb;border-radius:12px;padding:26px}}
.brand{{font:600 22px Georgia,serif;letter-spacing:2px;color:#102c42}}
.brand small{{display:block;font:400 11px Segoe UI,sans-serif;letter-spacing:0;color:#6b7e8e;margin-top:4px}}
h1{{font-size:19px;margin:22px 0 12px}}
.f{{display:flex;gap:10px;font-size:14px;margin:3px 0}}
.f span{{min-width:210px;color:#6b7e8e}}
table{{width:100%;border-collapse:collapse;margin:14px 0}}
th,td{{border:1px solid #ccd9e3;padding:8px;font-size:14px;text-align:left}}
thead th{{background:#f0f4f8}}
.notes{{border:1px solid #ccd9e3;border-radius:8px;padding:14px;margin-top:16px}}
.notes li{{margin:6px 0;font-size:14px}}
.pay{{margin-top:12px;font-size:14px;line-height:1.8}}
</style></head>
<body><div class="card">
<div class="brand">OPULENT<small>Unlocking property opportunities</small></div>
<h1>{_esc(row['title'])}</h1>
{fields}
<table><thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table>
<div class="notes"><b>NOTES:</b><ol>{notes_html}</ol><div class="pay">{payment_html}</div></div>
<p style="font-size:12px;color:#6b7e8e;margin-top:18px">This statement was prepared by Opulent Properties. Use your browser's Print or Save as PDF to keep a copy.</p>
</div></body></html>'''


def statement_message_page(title, message):
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{_esc(title)}</title></head><body style="font-family:Segoe UI,sans-serif;padding:40px"><h1>{_esc(title)}</h1><p>{_esc(message)}</p></body></html>'


def worker_tick():
    with connect(True) as c:
        s = settings(c)
        local = datetime.now(timezone.utc) + timedelta(minutes=s['utc_offset'])
        h = local.hour
        quiet = (s['quiet_start'] <= h < s['quiet_end']) if s['quiet_start'] < s['quiet_end'] else (h >= s['quiet_start'] or h < s['quiet_end'])
        if s['automatic']:
            generate(c, local.strftime('%Y-%m'), 'scheduler')
            if not quiet:
                eligible = []
                for ch in charge_list(c):
                    due = date.fromisoformat(ch['due'])
                    if reminder_due(local.date(), due, s['lead_days'], s['repeat_days']):
                        eligible.append(ch['id'])
                queue(c, preview_items(c, eligible), 'scheduler', 'automatic:' + local.date().isoformat())
        for message in rows(c, "SELECT * FROM messages WHERE status='queued' AND (dedupe NOT LIKE 'automatic:%' OR ?=1) ORDER BY id LIMIT 100", (int(bool(s['automatic']) and not quiet),)):
            if message['dedupe'].startswith('automatic:') and (quiet or not s['automatic']):
                continue
            fresh = preview_items(c, [message['charge_id']], message['penalty'], True)
            matching = next((item for item in fresh if item['contact_id'] == message['contact_id'] and item['phone'] == message['phone']), None)
            mode, detail = 'simulation', {}
            if not matching or matching['balance'] != message['balance'] or matching['body'] != message['body'] or matching['phone'] != message['phone']:
                status, ref = 'cancelled', None
            elif live_sms_enabled():
                mode = 'live'
                status, ref, detail = deliver_message(message)
            else:
                # A simulated outcome is never labelled delivered.
                status, ref = 'simulated', 'SIM-' + str(message['id'])
            c.execute('UPDATE messages SET status=?,provider_ref=?,mode=?,attempts=attempts+1,updated=? WHERE id=?', (status, ref, mode, stamp(), message['id']))
            audit(c, 'worker', 'message_' + status, {'message_id': message['id'], **detail})
        c.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
        c.execute('DELETE FROM previews WHERE expires<?', (time.time(),))


def worker_loop(stop):
    while not stop.is_set():
        try:
            worker_tick()
        except Exception as exc:
            print('Reminder worker error:', type(exc).__name__, flush=True)
        stop.wait(15)


def snapshot(c, user):
    payments = rows(c, '''SELECT p.*,u.label unit,COALESCE((SELECT SUM(amount) FROM allocations WHERE payment_id=p.id),0) allocated FROM payments p JOIN units u ON u.id=p.unit_id ORDER BY p.id DESC''')
    return {'version': VERSION, 'database_engine': 'postgresql' if DATABASE_URL else 'sqlite', 'user': user, 'settings': settings(c), 'today': today(c).isoformat(), 'sms_mode': sms_mode(),
            'properties': rows(c, 'SELECT * FROM properties ORDER BY name'),
            'units': rows(c, 'SELECT u.*,p.name property FROM units u JOIN properties p ON p.id=u.property_id ORDER BY p.name,u.block,u.label'),
            'contacts': rows(c, 'SELECT c.*,u.label unit FROM contacts c JOIN units u ON u.id=c.unit_id ORDER BY c.name'),
            'types': rows(c, 'SELECT * FROM charge_types ORDER BY id'), 'plans': rows(c, 'SELECT p.*,u.label unit,t.name type FROM plans p JOIN units u ON u.id=p.unit_id JOIN charge_types t ON t.id=p.type_id ORDER BY p.id DESC'),
            'charges': charge_list(c), 'payments': payments,
            'receipt_sends': rows(c, 'SELECT * FROM payment_receipt_sends ORDER BY id DESC LIMIT 2000'),
            'messages': rows(c, 'SELECT * FROM messages ORDER BY id DESC LIMIT 2000'),
            'statements': rows(c, 'SELECT * FROM statements ORDER BY id DESC LIMIT 2000'),
            'statement_sends': rows(c, 'SELECT ss.*, st.title statement_title, st.unit_label statement_unit FROM statement_sends ss JOIN statements st ON st.id=ss.statement_id ORDER BY ss.id DESC LIMIT 2000'),
            'staff': rows(c, 'SELECT id,name,email,role FROM users ORDER BY id') if user['role'] == 'admin' else [],
            'audit': rows(c, 'SELECT * FROM audit ORDER BY id DESC LIMIT 2000') if user['role'] == 'admin' else []}


def save_backup():
    if DATABASE_URL:
        raise Problem('PostgreSQL backups are managed by the hosting platform. Create and verify a Railway database backup.', 409)
    folder = Path(os.environ.get('OPULENT_BACKUPS', str(ROOT / 'backups')))
    folder.mkdir(exist_ok=True)
    target = folder / ('opulent-' + datetime.now().strftime('%Y%m%d-%H%M%S-') + secrets.token_hex(3) + '.sqlite3')
    with connect() as c:
        backup = sqlite3.connect(target)
        try:
            c.backup(backup)
            if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise Problem('Backup integrity check failed.', 500)
        finally:
            backup.close()
    return target


def mutate(c, route, d, user):
    actor = user['email']
    if user['role'] == 'viewer' and route != 'password':
        raise Problem('Read-only staff cannot change records.', 403)
    if route in ('settings', 'staff', 'backup', 'demo') and user['role'] != 'admin':
        raise Problem('Administrator access required.', 403)
    result = {}
    if route == 'properties':
        c.execute('INSERT INTO properties(name,address) VALUES(?,?)', (text(d, 'name'), text(d, 'address', 300)))
    elif route == 'units':
        owner = str(d.get('owner', '')).strip()
        if len(owner) > 120:
            raise Problem('Owner name must be at most 120 characters.')
        c.execute('INSERT INTO units(property_id,block,label,owner) VALUES(?,?,?,?)', (number(d, 'property_id'), '', text(d, 'label', 40), owner))
    elif route == 'unit-status':
        if not c.execute('UPDATE units SET active=? WHERE id=?', (number(d, 'active', 0, 1), number(d, 'id'))).rowcount:
            raise Problem('Unit not found.', 404)
    elif route in ('contacts', 'contact-edit'):
        phone = text(d, 'phone', 16)
        if not re.fullmatch(r'\+[1-9]\d{7,14}', phone):
            raise Problem('Phone must include a country code, for example +256 followed by the number (8–15 digits).')
        kind = text(d, 'kind')
        if kind not in ('Tenant', 'Owner'):
            raise Problem('Choose Tenant or Owner.')
        alternate = str(d.get('alternate_phone','')).strip()
        if alternate and not re.fullmatch(r'\+[1-9]\d{7,14}', alternate):
            raise Problem('Alternate phone must include a valid country code, or be left empty.')
        if alternate == phone:
            raise Problem('Alternate phone must differ from the primary phone.')
        start = iso_date(d.get('billing_start'))
        # A contact always belongs to a unit. The unit may be chosen directly, or
        # typed as a property plus unit label; a typed unit is created when new,
        # so it then appears in charges, reminders and statements.
        if d.get('unit_id') not in (None, ''):
            unit_id = number(d, 'unit_id')
            if not c.execute('SELECT 1 FROM units WHERE id=?', (unit_id,)).fetchone():
                raise Problem('That unit was not found.', 404)
        else:
            property_id = number(d, 'property_id')
            if not c.execute('SELECT 1 FROM properties WHERE id=?', (property_id,)).fetchone():
                raise Problem('Choose a property for this contact.', 404)
            unit_label = text(d, 'unit_label', 40)
            found = c.execute('SELECT id FROM units WHERE property_id=? AND label=?', (property_id, unit_label)).fetchone()
            if found:
                unit_id = found['id']
            else:
                c.execute('INSERT INTO units(property_id,block,label,owner) VALUES(?,?,?,?)', (property_id, '', unit_label, ''))
                unit_id = c.execute('SELECT id FROM units WHERE property_id=? AND label=?', (property_id, unit_label)).fetchone()['id']
        values = (unit_id, text(d, 'name'), phone, kind, number(d, 'notify', 0, 1), alternate, start)
        if route == 'contacts':
            c.execute('INSERT INTO contacts(unit_id,name,phone,kind,notify,alternate_phone,billing_start) VALUES(?,?,?,?,?,?,?)', values)
        elif not c.execute('UPDATE contacts SET unit_id=?,name=?,phone=?,kind=?,notify=?,alternate_phone=?,billing_start=? WHERE id=?', (*values,number(d,'id'))).rowcount:
            raise Problem('Contact not found.',404)
    elif route == 'contact-status':
        if not c.execute('UPDATE contacts SET active=?,notify=? WHERE id=?', (number(d, 'active', 0, 1), number(d, 'notify', 0, 1), number(d, 'id'))).rowcount:
            raise Problem('Contact not found.', 404)
    elif route == 'types':
        c.execute('INSERT INTO charge_types(name) VALUES(?)', (text(d, 'name', 60),))
    elif route == 'plans':
        start = period(d.get('start_period'))
        end = period(d['end_period']) if d.get('end_period') else None
        if end and end < start:
            raise Problem('End period must follow the start period.')
        unit_id, type_id = number(d, 'unit_id'), number(d, 'type_id')
        if c.execute('SELECT 1 FROM plans WHERE unit_id=? AND type_id=? AND active=1 AND start_period<=? AND (end_period IS NULL OR end_period>=?)', (unit_id, type_id, end or '9999-12', start)).fetchone():
            raise Problem('An overlapping active plan already exists. End or disable it before creating another.')
        c.execute('INSERT INTO plans(unit_id,type_id,amount,due_day,start_period,end_period) VALUES(?,?,?,?,?,?)', (unit_id, type_id, money(d.get('amount')), number(d, 'due_day', 1, 31), start, end))
    elif route == 'plan-status':
        if not c.execute('UPDATE plans SET active=0 WHERE id=?', (number(d, 'id'),)).rowcount:
            raise Problem('Plan not found.', 404)
    elif route == 'generate':
        result['created'] = generate(c, period(d.get('period')), actor)
    elif route == 'charges':
        unit = number(d, 'unit_id')
        source = text(d, 'source', 200)
        c.execute('INSERT INTO charges(unit_id,type_id,period,due,amount,source,created) VALUES(?,?,?,?,?,?,?)', (unit, number(d, 'type_id'), period(d.get('period')), iso_date(d.get('due')), money(d.get('amount')), source, stamp()))
        apply_credit(c, unit)
    elif route == 'payments':
        key = text(d, 'request_key', 80)
        unit, amount = number(d, 'unit_id'), money(d.get('amount'))
        paid_on, reference = iso_date(d.get('paid_on')), text(d, 'reference', 120)
        if paid_on > today(c).isoformat():
            raise Problem('Payment date cannot be in the future.')
        unit_row = c.execute('SELECT label,owner FROM units WHERE id=?', (unit,)).fetchone()
        if not unit_row:
            raise Problem('Unit not found.', 404)
        contact = c.execute("SELECT name,phone FROM contacts WHERE unit_id=? AND active=1 ORDER BY CASE kind WHEN 'Tenant' THEN 0 ELSE 1 END,id LIMIT 1", (unit,)).fetchone()
        client_name = text(d, 'client_name', 120) if str(d.get('client_name') or '').strip() else (contact['name'] if contact else unit_row['owner'] or 'Unit '+unit_row['label'])
        billing_period = str(d.get('billing_period') or f'{paid_on[:4]}-Q{(int(paid_on[5:7])-1)//3+1}').strip()
        if not re.fullmatch(r'(?:19|20|21)\d{2}-Q[1-4]', billing_period):
            raise Problem('Payment quarter must be YYYY-Q1, Q2, Q3 or Q4.')
        chosen_phone = str((d.get('receipt_phone') or d.get('registered_phone') or '') if ('receipt_phone' in d or 'registered_phone' in d) else (contact['phone'] if contact else '')).strip()
        receipt_phone = normalize_phone(chosen_phone) if chosen_phone else ''
        existing = c.execute('SELECT * FROM payments WHERE request_key=?', (key,)).fetchone()
        if existing:
            if (existing['unit_id'], existing['amount'], existing['paid_on'], existing['reference'], existing['client_name'], existing['billing_period'], existing['receipt_phone']) != (unit, amount, paid_on, reference, client_name, billing_period, receipt_phone):
                raise Problem('This payment request was already used with different details.', 409)
            return {'duplicate': True, 'id': existing['id']}
        token = secrets.token_urlsafe(24)
        c.execute('INSERT INTO payments(unit_id,amount,paid_on,reference,request_key,created,client_name,billing_period,receipt_phone,receipt_token) VALUES(?,?,?,?,?,?,?,?,?,?)', (unit, amount, paid_on, reference, key, stamp(), client_name, billing_period, receipt_phone, token))
        apply_credit(c, unit)
        payment_id = c.execute('SELECT id FROM payments WHERE request_key=?', (key,)).fetchone()['id']
        c.execute('UPDATE payments SET receipt_snapshot=? WHERE id=?', (json.dumps(receipt_snapshot(c, payment_id)), payment_id))
        result['id'] = payment_id
    elif route == 'receipt-preview':
        payment = c.execute('SELECT * FROM payments WHERE id=?', (number(d, 'id'),)).fetchone()
        if not payment or not payment['receipt_token'] or not payment['receipt_snapshot']:
            raise Problem('A receipt is not available for this payment.', 404)
        if payment['reversed']:
            raise Problem('This payment was reversed; its receipt cannot be sent.', 409)
        phone = normalize_phone(d.get('phone') or payment['receipt_phone'])
        snapshot_data = json.loads(payment['receipt_snapshot'])
        body = receipt_sms_body(snapshot_data, payment['receipt_token'])
        token = secrets.token_urlsafe(24)
        c.execute('INSERT INTO previews(token,user_id,payload,expires) VALUES(?,?,?,?)',
                  (token, user['id'], json.dumps({'kind':'receipt','id':payment['id'],'phone':phone,'body':body}), time.time()+600))
        result.update({'token':token,'phone':phone,'body':body,'snapshot':snapshot_data,
                       'estimated_cost':sms_segments(body)*settings(c)['segment_price'],'currency':settings(c)['currency'],
                       'mode':sms_mode(),'expires_in':600})
    elif route == 'receipt-send':
        preview_row = c.execute('SELECT * FROM previews WHERE token=? AND user_id=? AND expires>?',
                                (str(d.get('token') or ''), user['id'], time.time())).fetchone()
        if not preview_row:
            raise Problem('Receipt preview expired. Preview it again before sending.', 409)
        payload = json.loads(preview_row['payload'])
        if payload.get('kind') != 'receipt':
            raise Problem('Invalid receipt preview.', 409)
        c.execute('DELETE FROM previews WHERE token=?', (preview_row['token'],))
        payment = c.execute('SELECT * FROM payments WHERE id=?', (payload['id'],)).fetchone()
        if not payment or payment['reversed'] or not payment['receipt_token']:
            raise Problem('Payment is unavailable or reversed.', 409)
        body, phone = payload['body'], payload['phone']
        if body != receipt_sms_body(json.loads(payment['receipt_snapshot']), payment['receipt_token']):
            raise Problem('Receipt changed. Preview it again.', 409)
        mode, status, ref = sms_mode(), 'simulated', 'SIM-R'+str(payment['id'])
        detail = 'Test mode: the receipt message was recorded but not sent.'
        if live_sms_enabled():
            import egosms
            mode = 'live'
            username, api_key = os.environ.get('EGOSMS_USERNAME','').strip(), os.environ.get('EGOSMS_API_KEY','').strip()
            if not os.environ.get('OPULENT_PUBLIC_URL','').strip():
                status, ref, detail = 'failed', None, 'Public receipt URL is not configured.'
            elif not username or not api_key:
                status, ref, detail = 'failed', None, 'SMS credentials are not configured on this service.'
            else:
                try:
                    sent = egosms.send_one(phone, body, username=username, api_key=api_key,
                                           sender_id=os.environ.get('EGOSMS_SENDER_ID', egosms.DEFAULT_SENDER_ID),
                                           endpoint=os.environ.get('EGOSMS_ENDPOINT', egosms.LIVE_ENDPOINT))
                    status, ref, detail = 'accepted', sent['follow_up_code'], 'Accepted by EgoSMS.'
                except egosms.EgoSmsTransportError:
                    status, ref, detail = 'unknown', None, 'EgoSMS did not respond; the outcome is unknown.'
                except egosms.EgoSmsError as exc:
                    status, ref, detail = 'failed', None, str(exc)[:300]
        c.execute('INSERT INTO payment_receipt_sends(payment_id,phone,body,status,mode,provider_ref,detail,created,updated) VALUES(?,?,?,?,?,?,?,?,?)',
                  (payment['id'], phone, body, status, mode, ref, detail, stamp(), stamp()))
        result.update({'status':status,'phone':phone,'detail':detail,'link':receipt_link(payment['receipt_token'])})
    elif route == 'reverse':
        payment = c.execute('SELECT * FROM payments WHERE id=?', (number(d, 'id'),)).fetchone()
        if not payment or payment['reversed']:
            raise Problem('Payment not found or already reversed.')
        c.execute('UPDATE payments SET reversed=1,reason=? WHERE id=?', (text(d, 'reason', 300), payment['id']))
        # Released charges may now be covered by other existing unallocated credits.
        apply_credit(c, payment['unit_id'])
    elif route == 'preview':
        ids = d.get('charge_ids')
        if not isinstance(ids, list) or not ids or len(ids) > 1000 or any(type(i) is not int or i < 1 for i in ids):
            raise Problem('Select at least one charge (up to 1000).')
        if not isinstance(d.get('penalty',''),str):
            raise Problem('Penalty notice must be text.')
        penalty = d.get('penalty','').strip()
        if len(penalty) > 300 or any(ord(ch)<32 and ch not in '\r\n\t' for ch in penalty):
            raise Problem('Penalty notice must be at most 300 characters.')
        penalty = ' '.join(penalty.split())
        include_alternate = d.get('include_alternate',False)
        if type(include_alternate) is not bool:
            raise Problem('Invalid alternate-number selection.')
        items = preview_items(c, ids, penalty, include_alternate)
        token = secrets.token_urlsafe(32)
        payload = {'charge_ids':ids,'penalty':penalty,'include_alternate':include_alternate,'items':items}
        c.execute('INSERT INTO previews(token,user_id,payload,expires) VALUES(?,?,?,?)', (token, user['id'], json.dumps(payload), time.time() + 600))
        s = settings(c)
        return {'token': token, 'items': items, 'estimated_cost': sum(i['segments'] for i in items) * s['segment_price'], 'currency': s['currency'], 'expires_in': 600, 'mode': sms_mode()}
    elif route == 'send':
        token = text(d, 'token', 100)
        preview = c.execute('SELECT * FROM previews WHERE token=? AND user_id=? AND expires>?', (token, user['id'], time.time())).fetchone()
        if not preview:
            raise Problem('Preview expired. Preview the reminders again.', 409)
        payload = json.loads(preview['payload'])
        old = payload['items']
        fresh = preview_items(c, payload['charge_ids'], payload['penalty'], payload['include_alternate'])
        # De-duplicate the charge list within preview_items, then compare the full snapshot.
        if fresh != old:
            raise Problem('Balances or contacts changed. Preview again before confirming.', 409)
        result['queued'] = queue(c, fresh, actor, 'manual:' + token)
    elif route == 'settings':
        current = settings(c)
        currency = text(d, 'currency', 3).upper()
        country = text(d, 'country', 2).upper()
        if not re.fullmatch('[A-Z]{3}', currency) or not re.fullmatch('[A-Z]{2}', country):
            raise Problem('Use a three-letter currency and two-letter country code.')
        if currency != current['currency'] and c.execute('SELECT 1 FROM charges UNION ALL SELECT 1 FROM payments LIMIT 1').fetchone():
            raise Problem('Currency is locked after financial records exist; currency conversion is not supported.')
        offset = d.get('utc_offset')
        if isinstance(offset, bool) or not re.fullmatch(r'-?\d+', str(offset)) or not -720 <= int(offset) <= 840:
            raise Problem('UTC offset must be between -720 and 840 minutes.')
        price = d.get('segment_price', '0')
        price_minor = 0 if str(price) in ('0', '0.00') else money(price)
        qstart, qend = number(d, 'quiet_start', 0, 23), number(d, 'quiet_end', 0, 23)
        if qstart == qend:
            raise Problem('Quiet hour start and end must differ.')
        c.execute('UPDATE settings SET currency=?,country=?,utc_offset=?,automatic=?,lead_days=?,repeat_days=?,quiet_start=?,quiet_end=?,segment_price=? WHERE id=1', (currency, country, int(offset), number(d, 'automatic', 0, 1), number(d, 'lead_days', 0, 30), number(d, 'repeat_days', 1, 90), qstart, qend, price_minor))
    elif route == 'staff':
        role = text(d, 'role')
        if role not in ('admin', 'billing', 'viewer'):
            raise Problem('Invalid staff role.')
        email = text(d, 'email', 200).lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            raise Problem('Enter a valid staff email.')
        if c.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone():
            raise Problem('That email already belongs to a staff account. Use a different email address.', 409)
        if password_reused(c, d.get('password')):
            raise Problem('That password is already in use on another account. Choose a different password.', 409)
        c.execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)', (text(d, 'name'), email, password_hash(d.get('password')), role))
    elif route == 'password':
        stored = c.execute('SELECT password FROM users WHERE id=?', (user['id'],)).fetchone()['password']
        if not password_ok(d.get('current_password'), stored):
            raise Problem('Current password is incorrect.')
        if password_reused(c, d.get('new_password')):
            raise Problem('That password has already been used on an Opulent account. Choose a different password.', 409)
        c.execute('UPDATE users SET password=? WHERE id=?', (password_hash(d.get('new_password')), user['id']))
        c.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
    elif route == 'statement-save':
        s = d.get('statement')
        if not isinstance(s, dict):
            raise Problem('Invalid statement data.')
        def cell(value, limit=200):
            item = str(value if value is not None else '').strip()
            if len(item) > limit:
                raise Problem(f'A statement entry is too long (maximum {limit} characters).')
            return item
        def cell_list(value, limit=20):
            if value is None:
                return []
            if not isinstance(value, list) or len(value) > limit:
                raise Problem('Invalid statement list.')
            return [cell(v) for v in value]
        columns = cell_list(s.get('columns'), 8) or ['Quarter 1', 'Quarter 2', 'Quarter 3', 'Quarter 4']
        raw_rows = s.get('rows')
        if not isinstance(raw_rows, list) or not raw_rows or len(raw_rows) > 24:
            raise Problem('A statement needs between 1 and 24 rows.')
        statement_rows = []
        for item in raw_rows:
            if not isinstance(item, dict) or not isinstance(item.get('cells'), list) or len(item['cells']) > 8:
                raise Problem('Invalid statement row.')
            statement_rows.append({'label': cell(item.get('label', '')), 'cells': [cell(x) for x in item['cells']]})
        notes = cell_list(s.get('notes'), 20)
        payment = cell_list(s.get('payment'), 20)
        expires = cell(s.get('expires'))
        if expires:
            expires = iso_date(expires)
        values = (cell(s.get('title')), cell(s.get('client')), cell(s.get('unit_label')), cell(s.get('monthly_fee')),
                  cell(s.get('period')), cell(s.get('total_received')), cell(s.get('total_due')),
                  json.dumps(columns), json.dumps(statement_rows), json.dumps(notes), json.dumps(payment), expires)
        statement_id = s.get('id')
        if statement_id:
            try:
                statement_id = int(statement_id)
            except (TypeError, ValueError):
                raise Problem('Invalid statement reference.')
            if not c.execute('SELECT 1 FROM statements WHERE id=?', (statement_id,)).fetchone():
                raise Problem('Statement not found.', 404)
            c.execute('''UPDATE statements SET title=?,client=?,unit_label=?,monthly_fee=?,period=?,total_received=?,total_due=?,columns_json=?,rows_json=?,notes_json=?,payment_json=?,expires=?,updated=?,actor=? WHERE id=?''',
                      (*values, stamp(), actor, statement_id))
        else:
            token = secrets.token_urlsafe(16)
            c.execute('''INSERT INTO statements(title,client,unit_label,monthly_fee,period,total_received,total_due,columns_json,rows_json,notes_json,payment_json,expires,token,created,updated,actor) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                      (*values, token, stamp(), stamp(), actor))
            statement_id = c.execute('SELECT id FROM statements WHERE token=?', (token,)).fetchone()['id']
        result['id'] = statement_id
        result['token'] = c.execute('SELECT token FROM statements WHERE id=?', (statement_id,)).fetchone()['token']
        audit(c, actor, 'statement_save', {'id': statement_id})
    elif route == 'statement-delete':
        statement_id = number(d, 'id')
        c.execute('DELETE FROM statement_sends WHERE statement_id=?', (statement_id,))
        c.execute('DELETE FROM statements WHERE id=?', (statement_id,))
        audit(c, actor, 'statement_delete', {'id': statement_id})
    elif route == 'statement-send':
        row = c.execute('SELECT * FROM statements WHERE id=?', (number(d, 'id'),)).fetchone()
        if not row:
            raise Problem('Save the statement before sending it.', 409)
        phone = normalize_phone(d.get('phone'))
        body = statement_sms_body(row)
        mode, status, ref = sms_mode(), 'simulated', 'SIM-S' + str(row['id'])
        detail = 'Test mode: the message was recorded but not sent.'
        if live_sms_enabled():
            import egosms
            mode = 'live'
            username = os.environ.get('EGOSMS_USERNAME', '').strip()
            api_key = os.environ.get('EGOSMS_API_KEY', '').strip()
            if not username or not api_key:
                status, ref, detail = 'failed', None, 'SMS credentials are not configured on this service.'
            else:
                try:
                    sent = egosms.send_one(
                        phone, body,
                        username=username, api_key=api_key,
                        sender_id=os.environ.get('EGOSMS_SENDER_ID', egosms.DEFAULT_SENDER_ID),
                        endpoint=os.environ.get('EGOSMS_ENDPOINT', egosms.LIVE_ENDPOINT),
                    )
                    status, ref, detail = 'accepted', sent['follow_up_code'], 'Accepted by EgoSMS.'
                except egosms.EgoSmsTransportError:
                    status, ref, detail = 'unknown', None, 'EgoSMS did not respond; the outcome is unknown.'
                except egosms.EgoSmsError as exc:
                    status, ref, detail = 'failed', None, str(exc)[:300]
        c.execute('INSERT INTO statement_sends(statement_id,phone,body,status,mode,provider_ref,detail,snapshot_json,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (row['id'], phone, body, status, mode, ref, detail, statement_snapshot(row), stamp(), stamp()))
        audit(c, actor, 'statement_send', {'id': row['id'], 'phone': phone, 'status': status})
        result['status'] = status
        result['phone'] = phone
        result['detail'] = detail
        result['link'] = statement_link(row['token'])
    elif route == 'demo':
        if c.execute('SELECT 1 FROM properties LIMIT 1').fetchone():
            raise Problem('Demo records can only be added to an empty property database.')
        c.execute("INSERT INTO properties(name,address) VALUES('Serena Heights (demo)','Fictional property — test records only')")
        property_id = c.execute('SELECT last_insert_rowid()').fetchone()[0]
        month = today(c).strftime('%Y-%m')
        for idx, name in enumerate(('Alex K. (demo)', 'Sam N. (demo)', 'Jamie M. (demo)'), 1):
            c.execute('INSERT INTO units(property_id,block,label) VALUES(?,?,?)', (property_id, 'A', f'A0{idx}'))
            unit = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute("INSERT INTO contacts(unit_id,name,phone,kind,notify,billing_start) VALUES(?,?,?,'Tenant',1,?)", (unit, name, '+25670000000' + str(idx), today(c).isoformat()))
            c.execute('INSERT INTO plans(unit_id,type_id,amount,due_day,start_period) VALUES(?,?,?,?,?)', (unit, 1, 35000000, 30, month))
        generate(c, month, actor)
    else:
        raise Problem('Unknown operation.', 404)
    # Never write passwords or CSRF/session/preview secrets into the audit log.
    safe = {k: v for k, v in d.items() if 'password' not in k and k not in ('token', 'request_key')}
    audit(c, actor, route, safe)
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = 'Opulent'

    def log_message(self, fmt, *args):
        # Do not log URLs, contact data, tokens, or body content.
        pass

    def reply(self, value, status=200, cookie=None, content_type='application/json', csp=None):
        raw = json.dumps(value).encode() if content_type == 'application/json' else value
        if isinstance(raw, str):
            raw = raw.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', csp or "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(raw)

    def body(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 100000:
                raise Problem('Request is empty or too large.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (ValueError, json.JSONDecodeError):
            raise Problem('Invalid request body.')

    def session(self, c, csrf=False):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
        except Exception:
            raise Problem('Sign in to continue.', 401)
        token = cookie.get('opulent_session')
        session = c.execute('SELECT u.id,u.name,u.email,u.role,s.csrf,s.token FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?', (token.value if token else '', time.time())).fetchone()
        if not session:
            raise Problem('Sign in to continue.', 401)
        if csrf and not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
            raise Problem('Security token expired. Refresh and sign in again.', 403)
        return dict(session)

    def trusted_origin(self, mutating=False):
        host = self.headers.get('Host', '')
        public = os.environ.get('OPULENT_PUBLIC_URL','').rstrip('/')
        if public:
            allowed = (urlparse(public).netloc,)
            expected_origin = public
        else:
            allowed = (f'localhost:{self.server.server_port}',f'127.0.0.1:{self.server.server_port}')
            expected_origin = 'http://' + host
        if host not in allowed:
            raise Problem('This hostname is not configured for Opulent.', 403)
        origin = self.headers.get('Origin')
        if origin and origin != expected_origin:
            raise Problem('Cross-origin requests are not permitted.', 403)
        # Only state-changing requests are blocked when they originate from another site.
        # Ordinary navigation (following a link from a message or email) must still load the app.
        if mutating and self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise Problem('Cross-site requests are not permitted.', 403)

    def delivery_report(self, payload, token):
        # EgoSMS Transaction Status webhook. The unguessable path token is the
        # only credential; the report only ever matches an existing provider_ref.
        expected = os.environ.get('EGOSMS_WEBHOOK_TOKEN', '')
        if len(expected) < 24 or not hmac.compare_digest(token, expected):
            raise Problem('Not found.', 404)
        with connect(True) as c:
            apply_delivery_report(c, payload)
        self.reply({'ok': True})

    def reply_html(self, markup, status=200):
        self.reply(markup.encode('utf-8'), status, content_type='text/html; charset=utf-8',
                   csp="default-src 'none'; style-src 'unsafe-inline'; img-src 'self'")

    def do_GET(self):
        try:
            self.trusted_origin()
            path = urlparse(self.path).path
            if path == '/api/status':
                with connect() as c:
                    self.reply({'setup_required': not bool(c.execute('SELECT 1 FROM users LIMIT 1').fetchone()), 'version': VERSION})
            elif path in ('/api/state', '/api/export'):
                with connect() as c:
                    user = self.session(c)
                    if path == '/api/state':
                        self.reply(snapshot(c, {k: v for k, v in user.items() if k != 'token'}))
                    else:
                        out = io.StringIO(newline='')
                        writer = csv.writer(out)
                        writer.writerow(['Property', 'Block', 'Unit', 'Category', 'Period', 'Due', 'Amount', 'Paid', 'Remaining', 'Currency'])
                        for ch in charge_list(c):
                            cells = [ch['property'], ch['block'], ch['unit'], ch['type'], ch['period'], ch['due'], str(Decimal(ch['amount'])/100), str(Decimal(ch['paid'])/100), str(Decimal(ch['remaining'])/100), settings(c)['currency']]
                            writer.writerow(["'" + str(v) if str(v).startswith(('=', '+', '-', '@', '\t', '\r')) else v for v in cells])
                        self.reply(out.getvalue().encode('utf-8-sig'), content_type='text/csv; charset=utf-8')
            elif path.startswith('/s/'):
                token = path[3:].strip('/')
                with connect() as c:
                    row = c.execute('SELECT * FROM statements WHERE token=?', (token,)).fetchone()
                    current = today(c).isoformat()
                if not row:
                    self.reply_html(statement_message_page('Statement not found', 'This statement link is not valid.'), 404)
                elif row['expires'] and row['expires'] < current:
                    self.reply_html(statement_message_page('Link expired', 'This statement link is no longer available.'), 410)
                else:
                    self.reply_html(statement_page(row))
            elif path.startswith('/r/'):
                token = path[3:].strip('/')
                with connect() as c:
                    row = c.execute('SELECT receipt_snapshot,reversed FROM payments WHERE receipt_token=?', (token,)).fetchone()
                if not row or not row['receipt_snapshot']:
                    self.reply_html(statement_message_page('Receipt not found', 'This receipt link is not valid.'), 404)
                else:
                    self.reply_html(receipt_page(json.loads(row['receipt_snapshot']), bool(row['reversed'])))
            else:
                allowed = {'/': 'index.html', '/index.html': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/manifest.webmanifest': 'manifest.webmanifest', '/sw.js': 'sw.js', '/icon.svg': 'icon.svg', '/icon-192.png': 'icon-192.png', '/icon-512.png': 'icon-512.png'}
                if path not in allowed:
                    raise Problem('Not found.', 404)
                file = ROOT / 'public' / allowed[path]
                types = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.webmanifest': 'application/manifest+json', '.svg': 'image/svg+xml', '.png': 'image/png'}
                self.reply(file.read_bytes(), content_type=types[file.suffix])
        except Problem as exc:
            self.reply({'error': str(exc)}, exc.status)

    def do_POST(self):
        try:
            # Consume bounded bodies before an early rejection, avoiding TCP resets
            # on Windows when a response is sent with unread request bytes.
            d = self.body()
            self.trusted_origin(mutating=True)
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise Problem('JSON requests only.', 415)
            path = urlparse(self.path).path
            if path.startswith('/webhooks/egosms/'):
                self.delivery_report(d, path[len('/webhooks/egosms/'):].strip('/'))
                return
            route = urlparse(self.path).path.removeprefix('/api/')
            if not self.path.startswith('/api/'):
                raise Problem('Not found.', 404)
            cookie = None
            with connect(True) as c:
                if route in ('setup', 'login', 'register'):
                    if route == 'setup':
                        if c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                            raise Problem('Setup has already been completed.', 409)
                        email = text(d, 'email', 200).lower()
                        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                            raise Problem('Enter a valid staff email.')
                        c.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,'admin')", (text(d, 'name'), email, password_hash(d.get('password'))))
                        audit(c, email, 'setup', {})
                    if route == 'register':
                        # Open self-service registration: each staff member creates their own
                        # administrator account. A shared join code will gate this later.
                        email = text(d, 'email', 200).lower()
                        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                            raise Problem('Enter a valid staff email.')
                        if c.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone():
                            raise Problem('That email already belongs to a staff account. Sign in instead, or use a different email.', 409)
                        if password_reused(c, d.get('password')):
                            raise Problem('That password is already in use on another account. Choose a different password.', 409)
                        c.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,'admin')", (text(d, 'name'), email, password_hash(d.get('password'))))
                        audit(c, email, 'register', {})
                    email = text(d, 'email', 200).lower()
                    key = (self.client_address[0], email)
                    failures = [t for t in FAILED_LOGINS.get(key, []) if t > time.time() - 900]
                    if len(failures) >= 8:
                        raise Problem('Too many attempts. Try again in 15 minutes.', 429)
                    user = c.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
                    if not user or not password_ok(d.get('password'), user['password']):
                        FAILED_LOGINS[key] = failures + [time.time()]
                        raise Problem('Email or password is incorrect.', 401)
                    FAILED_LOGINS.pop(key, None)
                    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                    c.execute('INSERT INTO sessions VALUES(?,?,?,?)', (token, user['id'], csrf, time.time() + 28800))
                    cookie = f'opulent_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800' + ('; Secure' if os.environ.get('OPULENT_PUBLIC_URL') else '')
                    result = {'ok': True}
                else:
                    user = self.session(c, True)
                    if route == 'logout':
                        c.execute('DELETE FROM sessions WHERE token=?', (user['token'],))
                        cookie = 'opulent_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0' + ('; Secure' if os.environ.get('OPULENT_PUBLIC_URL') else '')
                        result = {'ok': True}
                    elif route == 'backup':
                        if user['role'] != 'admin':
                            raise Problem('Administrator access required.', 403)
                        # Backup outside this transaction to avoid holding a write lock while copying.
                        result = {'backup_pending': True}
                    else:
                        result = mutate(c, route, d, user)
            if route == 'backup':
                target = save_backup()
                with connect(True) as c:
                    audit(c, user['email'], 'backup', {'file': target.name})
                result = {'file': str(target)}
            self.reply(result, cookie=cookie)
        except Problem as exc:
            self.reply({'error': str(exc)}, exc.status)
        except INTEGRITY_ERRORS:
            self.reply({'error': 'A duplicate record or invalid linked record was detected. Check your selection. One charge is allowed per unit, category and period.'}, 409)
        except Exception as exc:
            print('Request error:', type(exc).__name__, flush=True)
            self.reply({'error': 'The operation failed. No partial changes were saved.'}, 500)


def main():
    init_db()
    port = int(os.environ.get('OPULENT_PORT', '8765'))
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    stop = threading.Event()
    threading.Thread(target=worker_loop, args=(stop,), daemon=True).start()
    print(f'Opulent {VERSION}: http://localhost:{port} — SMS mode: {sms_mode()}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
