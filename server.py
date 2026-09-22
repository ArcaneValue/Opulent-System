"""Opulent billing backend. Reminder delivery remains simulated."""
import calendar
import csv
import hashlib
import hmac
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
VERSION = '1.2.2-pilot'
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
        amount = Decimal(str(value))
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
CREATE TABLE IF NOT EXISTS units(id INTEGER PRIMARY KEY,property_id INTEGER NOT NULL REFERENCES properties(id),block TEXT NOT NULL,label TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,UNIQUE(property_id,block,label));
CREATE TABLE IF NOT EXISTS contacts(id INTEGER PRIMARY KEY,unit_id INTEGER NOT NULL REFERENCES units(id),name TEXT NOT NULL,phone TEXT NOT NULL,kind TEXT CHECK(kind IN ('Tenant','Owner')) NOT NULL,notify INTEGER NOT NULL DEFAULT 1,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS charge_types(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS plans(id INTEGER PRIMARY KEY,unit_id INTEGER NOT NULL REFERENCES units(id),type_id INTEGER NOT NULL REFERENCES charge_types(id),amount INTEGER NOT NULL CHECK(amount>0),due_day INTEGER NOT NULL CHECK(due_day BETWEEN 1 AND 31),start_period TEXT NOT NULL,end_period TEXT,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS charges(id INTEGER PRIMARY KEY,unit_id INTEGER NOT NULL REFERENCES units(id),type_id INTEGER NOT NULL REFERENCES charge_types(id),period TEXT NOT NULL,due TEXT NOT NULL,amount INTEGER NOT NULL CHECK(amount>0),source TEXT NOT NULL,created TEXT NOT NULL,UNIQUE(unit_id,type_id,period));
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY,unit_id INTEGER NOT NULL REFERENCES units(id),amount INTEGER NOT NULL CHECK(amount>0),paid_on TEXT NOT NULL,reference TEXT NOT NULL,request_key TEXT UNIQUE NOT NULL,reversed INTEGER NOT NULL DEFAULT 0,reason TEXT,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS allocations(payment_id INTEGER REFERENCES payments(id),charge_id INTEGER REFERENCES charges(id),amount INTEGER NOT NULL CHECK(amount>0),PRIMARY KEY(payment_id,charge_id));
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,charge_id INTEGER NOT NULL REFERENCES charges(id),contact_id INTEGER NOT NULL REFERENCES contacts(id),phone TEXT NOT NULL,body TEXT NOT NULL,balance INTEGER NOT NULL,dedupe TEXT UNIQUE NOT NULL,status TEXT NOT NULL DEFAULT 'queued',mode TEXT NOT NULL DEFAULT 'simulation',actor TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,provider_ref TEXT,created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS previews(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),payload TEXT,expires REAL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL,created TEXT NOT NULL);
CREATE VIEW IF NOT EXISTS charge_balances AS SELECT ch.*,COALESCE((SELECT SUM(a.amount) FROM allocations a JOIN payments p ON p.id=a.payment_id WHERE a.charge_id=ch.id AND p.reversed=0),0) paid,ch.amount-COALESCE((SELECT SUM(a.amount) FROM allocations a JOIN payments p ON p.id=a.payment_id WHERE a.charge_id=ch.id AND p.reversed=0),0) remaining FROM charges ch;
'''

POSTGRES_SCHEMA = '''
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT CHECK(role IN ('admin','billing','viewer')) NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id BIGINT REFERENCES users(id),csrf TEXT,expires DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),currency TEXT NOT NULL DEFAULT 'UGX',country TEXT NOT NULL DEFAULT 'UG',utc_offset INTEGER NOT NULL DEFAULT 180,automatic INTEGER NOT NULL DEFAULT 0,lead_days INTEGER NOT NULL DEFAULT 7,repeat_days INTEGER NOT NULL DEFAULT 7,quiet_start INTEGER NOT NULL DEFAULT 18,quiet_end INTEGER NOT NULL DEFAULT 8,segment_price BIGINT NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS properties(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,name TEXT UNIQUE NOT NULL,address TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS units(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,property_id BIGINT NOT NULL REFERENCES properties(id),block TEXT NOT NULL,label TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,UNIQUE(property_id,block,label));
CREATE TABLE IF NOT EXISTS contacts(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,unit_id BIGINT NOT NULL REFERENCES units(id),name TEXT NOT NULL,phone TEXT NOT NULL,kind TEXT CHECK(kind IN ('Tenant','Owner')) NOT NULL,notify INTEGER NOT NULL DEFAULT 1,active INTEGER NOT NULL DEFAULT 1,alternate_phone TEXT NOT NULL DEFAULT '',billing_start TEXT);
CREATE TABLE IF NOT EXISTS charge_types(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS plans(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,unit_id BIGINT NOT NULL REFERENCES units(id),type_id BIGINT NOT NULL REFERENCES charge_types(id),amount BIGINT NOT NULL CHECK(amount>0),due_day INTEGER NOT NULL CHECK(due_day BETWEEN 1 AND 31),start_period TEXT NOT NULL,end_period TEXT,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS charges(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,unit_id BIGINT NOT NULL REFERENCES units(id),type_id BIGINT NOT NULL REFERENCES charge_types(id),period TEXT NOT NULL,due TEXT NOT NULL,amount BIGINT NOT NULL CHECK(amount>0),source TEXT NOT NULL,created TEXT NOT NULL,UNIQUE(unit_id,type_id,period));
CREATE TABLE IF NOT EXISTS payments(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,unit_id BIGINT NOT NULL REFERENCES units(id),amount BIGINT NOT NULL CHECK(amount>0),paid_on TEXT NOT NULL,reference TEXT NOT NULL,request_key TEXT UNIQUE NOT NULL,reversed INTEGER NOT NULL DEFAULT 0,reason TEXT,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS allocations(payment_id BIGINT REFERENCES payments(id),charge_id BIGINT REFERENCES charges(id),amount BIGINT NOT NULL CHECK(amount>0),PRIMARY KEY(payment_id,charge_id));
CREATE TABLE IF NOT EXISTS messages(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,charge_id BIGINT NOT NULL REFERENCES charges(id),contact_id BIGINT NOT NULL REFERENCES contacts(id),phone TEXT NOT NULL,body TEXT NOT NULL,balance BIGINT NOT NULL,dedupe TEXT UNIQUE NOT NULL,status TEXT NOT NULL DEFAULT 'queued',mode TEXT NOT NULL DEFAULT 'simulation',actor TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,provider_ref TEXT,created TEXT NOT NULL,updated TEXT NOT NULL,penalty TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS previews(token TEXT PRIMARY KEY,user_id BIGINT REFERENCES users(id),payload TEXT,expires DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS audit(id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,detail TEXT NOT NULL,created TEXT NOT NULL);
CREATE OR REPLACE VIEW charge_balances AS SELECT ch.*,COALESCE((SELECT SUM(a.amount) FROM allocations a JOIN payments p ON p.id=a.payment_id WHERE a.charge_id=ch.id AND p.reversed=0),0) paid,ch.amount-COALESCE((SELECT SUM(a.amount) FROM allocations a JOIN payments p ON p.id=a.payment_id WHERE a.charge_id=ch.id AND p.reversed=0),0) remaining FROM charges ch;
'''


def init_db():
    if DATABASE_URL:
        with connect(True) as c:
            for statement in POSTGRES_SCHEMA.split(';'):
                if statement.strip():
                    c.execute(statement)
            c.execute('INSERT INTO schema_migrations(version,applied_at) VALUES(1,?) ON CONFLICT(version) DO NOTHING', (stamp(),))
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
            if not matching or matching['balance'] != message['balance'] or matching['body'] != message['body'] or matching['phone'] != message['phone']:
                status, ref = 'cancelled', None
            else:
                # Deliberately no provider transport. A simulated outcome is never labelled delivered.
                status, ref = 'simulated', 'SIM-' + str(message['id'])
            c.execute('UPDATE messages SET status=?,provider_ref=?,attempts=attempts+1,updated=? WHERE id=?', (status, ref, stamp(), message['id']))
            audit(c, 'worker', 'message_' + status, {'message_id': message['id']})
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
    return {'version': VERSION, 'database_engine': 'postgresql' if DATABASE_URL else 'sqlite', 'user': user, 'settings': settings(c), 'today': today(c).isoformat(), 'sms_mode': 'simulation',
            'properties': rows(c, 'SELECT * FROM properties ORDER BY name'),
            'units': rows(c, 'SELECT u.*,p.name property FROM units u JOIN properties p ON p.id=u.property_id ORDER BY p.name,u.block,u.label'),
            'contacts': rows(c, 'SELECT c.*,u.label unit FROM contacts c JOIN units u ON u.id=c.unit_id ORDER BY c.name'),
            'types': rows(c, 'SELECT * FROM charge_types ORDER BY id'), 'plans': rows(c, 'SELECT p.*,u.label unit,t.name type FROM plans p JOIN units u ON u.id=p.unit_id JOIN charge_types t ON t.id=p.type_id ORDER BY p.id DESC'),
            'charges': charge_list(c), 'payments': payments,
            'messages': rows(c, 'SELECT * FROM messages ORDER BY id DESC LIMIT 500'),
            'staff': rows(c, 'SELECT id,name,email,role FROM users ORDER BY id') if user['role'] == 'admin' else [],
            'audit': rows(c, 'SELECT * FROM audit ORDER BY id DESC LIMIT 200') if user['role'] == 'admin' else []}


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
        c.execute('INSERT INTO units(property_id,block,label) VALUES(?,?,?)', (number(d, 'property_id'), text(d, 'block', 40), text(d, 'label', 40)))
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
        values = (number(d, 'unit_id'), text(d, 'name'), phone, kind, number(d, 'notify', 0, 1), alternate, start)
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
        existing = c.execute('SELECT * FROM payments WHERE request_key=?', (key,)).fetchone()
        if existing:
            if (existing['unit_id'], existing['amount'], existing['paid_on'], existing['reference']) != (unit, amount, paid_on, reference):
                raise Problem('This payment request was already used with different details.', 409)
            return {'duplicate': True}
        c.execute('INSERT INTO payments(unit_id,amount,paid_on,reference,request_key,created) VALUES(?,?,?,?,?,?)', (unit, amount, paid_on, reference, key, stamp()))
        apply_credit(c, unit)
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
        return {'token': token, 'items': items, 'estimated_cost': sum(i['segments'] for i in items) * s['segment_price'], 'currency': s['currency'], 'expires_in': 600, 'mode': 'simulation'}
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
        c.execute('INSERT INTO users(name,email,password,role) VALUES(?,?,?,?)', (text(d, 'name'), email, password_hash(d.get('password')), role))
    elif route == 'password':
        stored = c.execute('SELECT password FROM users WHERE id=?', (user['id'],)).fetchone()[0]
        if not password_ok(d.get('current_password'), stored):
            raise Problem('Current password is incorrect.')
        c.execute('UPDATE users SET password=? WHERE id=?', (password_hash(d.get('new_password')), user['id']))
        c.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
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

    def reply(self, value, status=200, cookie=None, content_type='application/json'):
        raw = json.dumps(value).encode() if content_type == 'application/json' else value
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
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

    def trusted_origin(self):
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
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise Problem('Cross-site requests are not permitted.', 403)

    def do_GET(self):
        try:
            self.trusted_origin()
            path = urlparse(self.path).path
            if path == '/api/status':
                with connect() as c:
                    self.reply({'setup_required': not bool(c.execute('SELECT 1 FROM users LIMIT 1').fetchone()), 'setup_token_required':bool(os.environ.get('OPULENT_PUBLIC_URL')), 'version': VERSION})
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
            self.trusted_origin()
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise Problem('JSON requests only.', 415)
            route = urlparse(self.path).path.removeprefix('/api/')
            if not self.path.startswith('/api/'):
                raise Problem('Not found.', 404)
            cookie = None
            with connect(True) as c:
                if route in ('setup', 'login'):
                    if route == 'setup':
                        if c.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                            raise Problem('Setup has already been completed.', 409)
                        if os.environ.get('OPULENT_PUBLIC_URL'):
                            expected_token = os.environ.get('OPULENT_SETUP_TOKEN','')
                            if len(expected_token)<24 or not hmac.compare_digest(str(d.get('setup_token','')),expected_token):
                                raise Problem('A valid deployment setup code is required.',403)
                        email = text(d, 'email', 200).lower()
                        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                            raise Problem('Enter a valid staff email.')
                        c.execute("INSERT INTO users(name,email,password,role) VALUES(?,?,?,'admin')", (text(d, 'name'), email, password_hash(d.get('password'))))
                        audit(c, email, 'setup', {})
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
    print(f'Opulent {VERSION}: http://localhost:{port} — SMS SIMULATION ONLY', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
