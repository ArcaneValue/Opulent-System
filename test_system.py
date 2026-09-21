import http.client
import json
import sqlite3
import socket
import os
import tempfile
import threading
import unittest
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import server


class FinancialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = server.DB
        server.DB = Path(self.temp.name) / 'test.sqlite3'
        server.init_db()
        self.user = {'id': 1, 'email': 'test@example.test', 'role': 'admin'}
        with server.connect(True) as c:
            c.execute("INSERT INTO users(id,name,email,password,role) VALUES(1,'Tester','test@example.test',?,'admin')", (server.password_hash('TestingPassword123!'),))
            server.mutate(c, 'properties', {'name':'Test building','address':'Fictional'}, self.user)
            server.mutate(c, 'units', {'property_id':1,'block':'A','label':'A01'}, self.user)
            server.mutate(c, 'contacts', {'unit_id':1,'name':'Test tenant','phone':'+256700000001','kind':'Tenant','notify':1,'billing_start':'2025-05-17'}, self.user)

    def tearDown(self):
        server.DB = self.previous
        self.temp.cleanup()

    def mutate(self, route, data):
        with server.connect(True) as c:
            return server.mutate(c, route, data, self.user)

    def charge(self, amount='350000', period='2026-09', due='2026-09-30', type_id=1):
        return self.mutate('charges', {'unit_id':1,'type_id':type_id,'amount':amount,'period':period,'due':due,'source':'Test'})

    def payment(self, amount, key='payment-1'):
        return self.mutate('payments', {'unit_id':1,'amount':amount,'paid_on':'2020-01-01','reference':'TEST','request_key':key})

    def balances(self):
        with server.connect() as c:
            return server.charge_list(c)

    def test_partial_payment_and_idempotent_retry(self):
        self.charge()
        self.payment('200000')
        self.assertEqual(self.balances()[0]['remaining'], 15000000)
        self.assertTrue(self.payment('200000')['duplicate'])
        self.assertEqual(self.balances()[0]['paid'], 20000000)
        with self.assertRaises(server.Problem):
            self.payment('200001')

    def test_oldest_first_and_overpayment_credit_covers_future_charge(self):
        self.charge('100','2026-08','2026-08-30')
        self.charge('100','2026-09','2026-09-30',2)
        self.payment('250')
        self.assertEqual([c['remaining'] for c in self.balances()], [0,0])
        self.charge('100','2026-10','2026-10-30')
        self.assertEqual(self.balances()[-1]['remaining'], 5000)

    def test_reversal_restores_balance_and_preserves_record(self):
        self.charge('100')
        self.payment('60')
        self.mutate('reverse', {'id':1,'reason':'Wrong unit'})
        self.assertEqual(self.balances()[0]['remaining'],10000)
        with server.connect() as c:
            self.assertEqual(c.execute('SELECT reversed FROM payments').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM allocations').fetchone()[0],1)
        with self.assertRaises(server.Problem):
            self.mutate('reverse', {'id':1,'reason':'Again'})

    def test_credit_on_other_payment_is_reallocated_after_reversal(self):
        self.charge('100')
        self.payment('100','a')
        self.payment('60','b')
        self.mutate('reverse',{'id':1,'reason':'Mistake'})
        self.assertEqual(self.balances()[0]['remaining'],4000)

    def test_recurring_idempotence_and_short_month(self):
        self.mutate('plans',{'unit_id':1,'type_id':1,'amount':'123.45','due_day':31,'start_period':'2026-01'})
        self.assertEqual(self.mutate('generate',{'period':'2026-02'})['created'],1)
        self.assertEqual(self.mutate('generate',{'period':'2026-02'})['created'],0)
        self.assertEqual(self.balances()[0]['due'],'2026-02-28')
        self.assertEqual(self.balances()[0]['amount'],12345)

    def test_overlapping_plan_rejected_and_stop_preserves_charge(self):
        plan={'unit_id':1,'type_id':1,'amount':'100','due_day':1,'start_period':'2026-01'}
        self.mutate('plans',plan)
        with self.assertRaises(server.Problem):
            self.mutate('plans',plan)
        self.mutate('generate',{'period':'2026-01'})
        self.mutate('plan-status',{'id':1})
        self.assertEqual(self.mutate('generate',{'period':'2026-02'})['created'],0)
        self.assertEqual(len(self.balances()),1)

    def test_duplicate_historical_charge_rejected(self):
        self.charge()
        with self.assertRaises(sqlite3.IntegrityError):
            self.charge()
        self.assertEqual(len(self.balances()),1)

    def test_invalid_money_and_phone(self):
        for amount in ('1.001','NaN','Infinity','0','-1'):
            with self.assertRaises(server.Problem):
                server.money(amount)
        self.assertEqual(server.money('0.01'),1)
        with self.assertRaises(server.Problem):
            self.mutate('contacts',{'unit_id':1,'name':'X','phone':'0700000001','kind':'Tenant','notify':1})

    def test_multiple_contacts_and_notification_opt_out(self):
        self.charge()
        self.mutate('contacts',{'unit_id':1,'name':'Owner','phone':'+256700000002','kind':'Owner','notify':1,'billing_start':'2025-05-17'})
        self.assertEqual(len(self.mutate('preview',{'charge_ids':[1]})['items']),2)
        self.mutate('contact-status',{'id':2,'active':1,'notify':0})
        self.assertEqual(len(self.mutate('preview',{'charge_ids':[1]})['items']),1)

    def test_preview_send_idempotent_and_worker_simulated(self):
        self.charge()
        preview=self.mutate('preview',{'charge_ids':[1]})
        self.assertEqual(preview['items'][0]['balance'],35000000)
        self.assertEqual(self.mutate('send',{'token':preview['token']})['queued'],1)
        self.assertEqual(self.mutate('send',{'token':preview['token']})['queued'],0)
        server.worker_tick()
        with server.connect() as c:
            self.assertEqual(c.execute('SELECT status FROM messages').fetchone()[0],'simulated')

    def test_payment_between_preview_and_confirmation_rejected(self):
        self.charge()
        preview=self.mutate('preview',{'charge_ids':[1]})
        self.payment('1')
        with self.assertRaises(server.Problem) as err:
            self.mutate('send',{'token':preview['token']})
        self.assertEqual(err.exception.status,409)

    def test_payment_after_queue_cancels_stale_message(self):
        self.charge()
        preview=self.mutate('preview',{'charge_ids':[1]})
        self.mutate('send',{'token':preview['token']})
        self.payment('350000')
        server.worker_tick()
        with server.connect() as c:
            self.assertEqual(c.execute('SELECT status FROM messages').fetchone()[0],'cancelled')

    def test_automatic_schedule_and_duplicate_prevention(self):
        with server.connect(True) as c:
            c.execute('UPDATE settings SET automatic=1,lead_days=0,repeat_days=7')
            s=server.settings(c)
            local=server.datetime.now(server.timezone.utc)+timedelta(minutes=s['utc_offset'])
            # Quiet hours deliberately placed away from the current local hour.
            c.execute('UPDATE settings SET quiet_start=?,quiet_end=?',((local.hour+1)%24,(local.hour+2)%24))
            due=server.today(c).isoformat()
        self.charge('100',due[:7],due)
        server.worker_tick()
        server.worker_tick()
        with server.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM messages').fetchone()[0],1)

    def test_due_date_anchored_reminder_calendar(self):
        due = server.date(2026, 10, 3)
        selected = [offset for offset in range(-10, 23)
                    if server.reminder_due(due + timedelta(days=offset), due, 7, 7)]
        self.assertEqual(selected, [-7, 0, 7, 14, 21])
        # A different lead time must not shift due-date or overdue notifications.
        selected = [offset for offset in range(-10, 16)
                    if server.reminder_due(due + timedelta(days=offset), due, 3, 7)]
        self.assertEqual(selected, [-3, 0, 7, 14])

    def test_automatic_calendar_excludes_cleared_bill(self):
        with server.connect(True) as c:
            local = server.datetime.now(server.timezone.utc) + timedelta(minutes=server.settings(c)['utc_offset'])
            c.execute('UPDATE settings SET automatic=1,lead_days=7,repeat_days=7,quiet_start=?,quiet_end=?',
                      ((local.hour+1)%24, (local.hour+2)%24))
            due = server.today(c).isoformat()
        self.charge('100', due[:7], due)
        self.payment('100')
        server.worker_tick()
        with server.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM messages').fetchone()[0], 0)

    def test_quiet_hours_block_automatic_messages(self):
        with server.connect(True) as c:
            s=server.settings(c)
            h=(server.datetime.now(server.timezone.utc)+timedelta(minutes=s['utc_offset'])).hour
            c.execute('UPDATE settings SET automatic=1,lead_days=0,quiet_start=?,quiet_end=?',(h,(h+1)%24))
            due=server.today(c).isoformat()
        self.charge('100',due[:7],due)
        server.worker_tick()
        with server.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM messages').fetchone()[0],0)

    def test_viewer_forbidden_and_billing_cannot_add_staff(self):
        self.user['role']='viewer'
        with self.assertRaises(server.Problem) as err:
            self.charge()
        self.assertEqual(err.exception.status,403)
        self.user['role']='billing'
        with self.assertRaises(server.Problem):
            self.mutate('staff',{})

    def test_queued_automatic_jobs_respect_quiet_hours_and_disable(self):
        self.charge()
        with server.connect(True) as c:
            items=server.preview_items(c,[1])
            server.queue(c,items,'scheduler','automatic:test')
            for i in range(100):
                server.queue(c,items,'scheduler',f'automatic:pending{i}')
            server.queue(c,items,'test@example.test','manual:test')
        server.worker_tick()
        with server.connect(True) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM messages WHERE status='queued'").fetchone()[0],101)
            self.assertEqual(c.execute("SELECT status FROM messages WHERE dedupe LIKE 'manual:%'").fetchone()[0],'simulated')
            s=server.settings(c)
            h=(server.datetime.now(server.timezone.utc)+timedelta(minutes=s['utc_offset'])).hour
            c.execute('UPDATE settings SET automatic=1,quiet_start=?,quiet_end=?',(h,(h+1)%24))
        server.worker_tick()
        with server.connect() as c:
            self.assertEqual(c.execute('SELECT status FROM messages').fetchone()[0],'queued')

    def test_currency_cannot_relabel_existing_money(self):
        self.charge()
        with server.connect() as c:
            s=server.settings(c)
        s.update(currency='USD',segment_price='0')
        with self.assertRaises(server.Problem):
            self.mutate('settings',s)

    def test_contact_dates_alternate_and_edit_without_creating_charges(self):
        data={'unit_id':1,'name':'Historic owner','phone':'+256700000010','alternate_phone':'+256700000011','kind':'Owner','notify':1,'billing_start':'2025-05-17'}
        self.mutate('contacts',data)
        with server.connect() as c:
            row=dict(c.execute('SELECT * FROM contacts WHERE id=2').fetchone())
        self.assertEqual(row['billing_start'],'2025-05-17')
        self.assertEqual(row['alternate_phone'],'+256700000011')
        self.assertEqual(self.balances(),[])
        data.update(id=2,billing_start='2025-05-25',alternate_phone='')
        self.mutate('contact-edit',data)
        with server.connect() as c:
            self.assertEqual(c.execute('SELECT billing_start FROM contacts WHERE id=2').fetchone()[0],'2025-05-25')
        for invalid in ('2025-02-30','',None):
            data['billing_start']=invalid
            with self.assertRaises(server.Problem):self.mutate('contacts',data)
        data.update(billing_start='2025-05-17',alternate_phone='0700000001')
        with self.assertRaises(server.Problem):self.mutate('contacts',data)
        data['alternate_phone']=data['phone']
        with self.assertRaises(server.Problem):self.mutate('contacts',data)

    def test_manual_penalty_only_overdue_and_preserved_by_worker(self):
        with server.connect() as c:current=server.today(c)
        overdue=(current-timedelta(days=3)).isoformat()
        upcoming=(current+timedelta(days=3)).isoformat()
        self.charge('100',overdue[:7],overdue)
        self.charge('100',upcoming[:7],upcoming,2)
        notice='Elevator card may be deactivated under property policy.'
        p=self.mutate('preview',{'charge_ids':[1,2],'penalty':notice})
        self.assertIn(notice,p['items'][0]['body'])
        self.assertNotIn(notice,p['items'][1]['body'])
        self.mutate('send',{'token':p['token']})
        server.worker_tick()
        with server.connect() as c:
            self.assertEqual([r['status'] for r in c.execute('SELECT status FROM messages')],['simulated','simulated'])
            self.assertEqual(c.execute('SELECT penalty FROM messages WHERE charge_id=1').fetchone()[0],notice)
            self.assertEqual(server.preview_items(c,[1])[0]['penalty'],'')

    def test_alternate_opt_in_dedup_and_contact_change_rejection(self):
        self.charge()
        self.mutate('contact-edit',{'id':1,'unit_id':1,'name':'Tenant','phone':'+256700000001','alternate_phone':'+256700000002','kind':'Tenant','notify':1,'billing_start':'2025-05-17'})
        self.assertEqual(len(self.mutate('preview',{'charge_ids':[1]})['items']),1)
        p=self.mutate('preview',{'charge_ids':[1],'include_alternate':True})
        self.assertEqual(len(p['items']),2)
        self.assertEqual(p['items'][1]['recipient_type'],'Alternate')
        self.assertEqual(self.mutate('send',{'token':p['token']})['queued'],2)
        self.assertEqual(self.mutate('send',{'token':p['token']})['queued'],0)
        server.worker_tick()
        with server.connect() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM messages WHERE status='simulated'").fetchone()[0],2)
        # Another contact with the same number must not double-send this charge.
        self.mutate('contacts',{'unit_id':1,'name':'Shared number','phone':'+256700000002','kind':'Owner','notify':1,'billing_start':'2025-05-17'})
        self.assertEqual(len(self.mutate('preview',{'charge_ids':[1],'include_alternate':True})['items']),2)
        p=self.mutate('preview',{'charge_ids':[1],'include_alternate':True})
        self.mutate('contact-status',{'id':1,'active':0,'notify':1})
        with self.assertRaises(server.Problem):self.mutate('send',{'token':p['token']})

    def test_additive_migration_preserves_legacy_contacts_and_balances(self):
        self.charge()
        self.payment('10')
        with server.connect(True) as c:
            c.execute('ALTER TABLE contacts DROP COLUMN alternate_phone')
            c.execute('ALTER TABLE contacts DROP COLUMN billing_start')
            c.execute('ALTER TABLE messages DROP COLUMN penalty')
            c.execute('PRAGMA user_version=1')
        server.init_db()
        server.init_db()
        self.assertEqual(self.balances()[0]['remaining'],34999000)
        with server.connect() as c:
            row=c.execute('SELECT * FROM contacts').fetchone()
            self.assertIsNone(row['billing_start'])
            self.assertEqual(row['phone'],'+256700000001')
            self.assertEqual(row['alternate_phone'],'')

    def test_upgrade_does_not_repeat_legacy_automatic_message(self):
        self.charge()
        with server.connect(True) as c:
            items=server.preview_items(c,[1])
            server.queue(c,items,'scheduler','automatic:test')
            c.execute("UPDATE messages SET dedupe='automatic:test:1:1'")
            self.assertEqual(server.queue(c,items,'scheduler','automatic:test'),0)

    def test_backup_and_restore_data_integrity(self):
        self.charge()
        self.payment('10')
        old_root=server.ROOT
        server.ROOT=Path(self.temp.name)
        try:
            file=server.save_backup()
            with closing(sqlite3.connect(file)) as c:
                self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(c.execute('SELECT remaining FROM charge_balances').fetchone()[0],34999000)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM payments').fetchone()[0],1)
            import maintenance
            self.payment('20','second-payment')
            with socket.socket() as guard:
                guard.bind(('127.0.0.1',0))
                test_port=guard.getsockname()[1]
            with patch.dict(os.environ,{'OPULENT_PORT':str(test_port)}):
                maintenance.restore(file)
            self.assertEqual(self.balances()[0]['remaining'],34999000)
            with server.connect() as c:
                self.assertEqual(c.execute('SELECT automatic FROM settings').fetchone()[0],0)
        finally:
            server.ROOT=old_root


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.previous=server.DB
        server.DB=Path(self.temp.name)/'http.sqlite3'
        server.init_db()
        self.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()
        self.cookie=''
        self.csrf=''

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        server.DB=self.previous
        self.temp.cleanup()

    def request(self,method,path,data=None,headers=None):
        h={'Host':f'localhost:{self.http.server_port}','Cookie':self.cookie,'Content-Type':'application/json','X-CSRF-Token':self.csrf}
        h.update(headers or {})
        conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=5)
        conn.request(method,path,json.dumps(data) if data is not None else None,h)
        response=conn.getresponse()
        body=response.read()
        cookie=response.getheader('Set-Cookie')
        if cookie:self.cookie=cookie.split(';')[0]
        status=response.status
        result=json.loads(body) if 'application/json' in response.getheader('Content-Type','') else body
        conn.close()
        return status,result

    def setup(self):
        self.assertEqual(self.request('POST','/api/setup',{'name':'Admin','email':'admin@example.test','password':'TestingPassword123!'})[0],200)
        status,data=self.request('GET','/api/state')
        self.assertEqual(status,200)
        self.csrf=data['user']['csrf']

    def test_authentication_and_csrf_and_origin(self):
        self.assertEqual(self.request('GET','/api/state')[0],401)
        self.setup()
        self.assertEqual(self.request('POST','/api/properties',{'name':'X','address':'Y'}, {'X-CSRF-Token':''})[0],403)
        self.assertEqual(self.request('POST','/api/properties',{'name':'X','address':'Y'}, {'Origin':'https://other.example'})[0],403)
        self.assertEqual(self.request('GET','/api/state',headers={'Host':'attacker.example'})[0],403)
        self.assertEqual(self.request('POST','/api/properties',{'name':'X','address':'Y'})[0],200)
        self.assertEqual(self.request('POST','/api/logout',{})[0],200)
        self.assertEqual(self.request('GET','/api/state')[0],401)

    def test_static_files_and_setup_once(self):
        for route in ('/','/app.js','/style.css','/manifest.webmanifest','/icon-192.png','/icon-512.png','/sw.js'):
            self.assertEqual(self.request('GET',route)[0],200)
        self.assertEqual(self.request('GET','/../server.py')[0],404)
        self.setup()
        self.assertEqual(self.request('POST','/api/setup',{'name':'Other','email':'a@b.test','password':'TestingPassword123!'})[0],409)

    def test_backend_role_access(self):
        self.setup()
        self.assertEqual(self.request('POST','/api/staff',{'name':'Viewer','email':'viewer@example.test','password':'TestingPassword123!','role':'viewer'})[0],200)
        self.request('POST','/api/logout',{})
        self.assertEqual(self.request('POST','/api/login',{'email':'viewer@example.test','password':'TestingPassword123!'})[0],200)
        _,data=self.request('GET','/api/state')
        self.csrf=data['user']['csrf']
        self.assertEqual(data['staff'],[])
        self.assertEqual(data['audit'],[])
        self.assertEqual(self.request('POST','/api/properties',{'name':'X','address':'Y'})[0],403)
        self.assertEqual(self.request('POST','/api/backup',{})[0],403)
        self.assertEqual(self.request('POST','/api/password',{'current_password':'TestingPassword123!','new_password':'NewTestingPassword123!'})[0],200)
        self.assertEqual(self.request('GET','/api/state')[0],401)


if __name__ == '__main__':
    unittest.main(verbosity=2)
