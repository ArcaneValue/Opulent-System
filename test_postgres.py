import os
import json
import unittest
from datetime import timedelta
from urllib.parse import urlparse

import server


URL = os.environ.get('OPULENT_TEST_POSTGRES_URL', '')


@unittest.skipUnless(URL, 'OPULENT_TEST_POSTGRES_URL is not configured')
class PostgreSQLWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not urlparse(URL).path.endswith('_test'):
            raise RuntimeError('PostgreSQL tests require a database name ending in _test.')
        server.DATABASE_URL = URL
        import psycopg
        with psycopg.connect(URL, autocommit=True) as connection:
            connection.execute('DROP SCHEMA public CASCADE')
            connection.execute('CREATE SCHEMA public')
        server.init_db()

    def test_billing_reminder_and_json_snapshot(self):
        user = {'id': 1, 'email': 'postgres-test@example.test', 'role': 'admin'}
        with server.connect(True) as c:
            c.execute("INSERT INTO users(name,email,password,role) VALUES('Tester','postgres-test@example.test',?,'admin')", (server.password_hash('TestingPassword123!'),))
            server.mutate(c, 'properties', {'name':'Test building','address':'Fictional'}, user)
            property_id = c.execute('SELECT id FROM properties').fetchone()['id']
            server.mutate(c, 'units', {'property_id':property_id,'block':'A','label':'A01'}, user)
            unit_id = c.execute('SELECT id FROM units').fetchone()['id']
            server.mutate(c, 'contacts', {'unit_id':unit_id,'name':'Test tenant','phone':'+256700000001','kind':'Tenant','notify':1,'billing_start':'2025-05-17'}, user)
            category = c.execute("SELECT id FROM charge_types WHERE name='Condo Fee'").fetchone()['id']
            due = server.today(c).isoformat()
            server.mutate(c, 'charges', {'unit_id':unit_id,'type_id':category,'amount':'350000','period':due[:7],'due':due,'source':'Test'}, user)
            charge_id = c.execute('SELECT id FROM charges').fetchone()['id']
            server.mutate(c, 'payments', {'unit_id':unit_id,'amount':'125000','paid_on':due,'reference':'TEST','request_key':'pg-test-payment'}, user)
            self.assertEqual(server.queue(c, server.preview_items(c, [charge_id]), user['email'], 'pg-test'), 1)
        server.worker_tick()
        with server.connect() as c:
            charge = server.charge_list(c)[0]
            self.assertEqual((charge['paid'], charge['remaining']), (12500000, 22500000))
            self.assertEqual(c.execute('SELECT status FROM messages').fetchone()['status'], 'simulated')
            state = server.snapshot(c, {**user, 'name':'Tester'})
            self.assertEqual(state['database_engine'], 'postgresql')
            self.assertIsInstance(state['charges'][0]['remaining'], int)
            json.dumps(state)


if __name__ == '__main__':
    unittest.main()
