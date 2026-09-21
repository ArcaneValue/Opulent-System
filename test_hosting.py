"""Exercise the actual hosted Flask adapter, without a paid Railway deployment."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server
from webapp import create_app


class HostingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old_db=server.DB
        server.DB=Path(self.temp.name)/'hosted.sqlite3'
        self.environment=patch.dict(os.environ,{'OPULENT_PUBLIC_URL':'https://opulent.example.test','OPULENT_SETUP_TOKEN':'PrivateTestSetupCode1234567890','OPULENT_DB':str(server.DB),'OPULENT_BACKUPS':str(Path(self.temp.name)/'backups')})
        self.environment.start()
        self.client=create_app(start_worker=False).test_client()
        self.origin='https://opulent.example.test'

    def tearDown(self):
        self.environment.stop()
        server.DB=self.old_db
        self.temp.cleanup()

    def get(self,path,**kwargs):
        return self.client.get(path,base_url=self.origin,**kwargs)

    def post(self,path,data,**kwargs):
        return self.client.post(path,json=data,base_url=self.origin,**kwargs)

    def test_setup_code_secure_cookie_and_authenticated_api(self):
        status=self.get('/api/status').json
        self.assertTrue(status['setup_token_required'])
        data={'name':'Host admin','email':'host@example.test','password':'PrivateTestingPassword123!'}
        self.assertEqual(self.post('/api/setup',data).status_code,403)
        self.assertTrue(self.get('/api/status').json['setup_required'])
        data['setup_token']='PrivateTestSetupCode1234567890'
        response=self.post('/api/setup',data)
        self.assertEqual(response.status_code,200)
        self.assertIn('Secure',response.headers['Set-Cookie'])
        state=self.get('/api/state').json
        csrf=state['user']['csrf']
        self.assertEqual(self.post('/api/properties',{'name':'Test','address':'Fictional'},headers={'X-CSRF-Token':csrf}).status_code,200)
        self.assertEqual(self.post('/api/properties',{'name':'Other','address':'Fictional'}).status_code,403)
        self.assertEqual(self.post('/api/properties',{'name':'Other','address':'Fictional'},headers={'X-CSRF-Token':csrf,'Origin':'https://other.example.test'}).status_code,403)
        self.assertNotIn('setup_token',str(state['audit']))

    def test_healthcheck_static_and_unknown_host(self):
        response=self.client.get('/healthz',base_url='http://healthcheck.railway.app')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['sms_mode'],'simulation')
        self.assertEqual(self.get('/').status_code,200)
        self.assertIn('frame-ancestors',self.get('/').headers['Content-Security-Policy'])
        self.assertEqual(self.client.get('/api/status',base_url='https://attacker.example.test').status_code,403)
        self.assertEqual(self.get('/server.py').status_code,404)
        self.assertEqual(self.post('/api/login',{'payload':'x'*100001}).status_code,413)

    def test_invalid_hosting_configuration_fails_closed(self):
        for url in ('http://example.test','https://example.test/path','https://user:pass@example.test'):
            with patch.dict(os.environ,{'OPULENT_PUBLIC_URL':url}):
                with self.assertRaises(RuntimeError):create_app(start_worker=False)
        with patch.dict(os.environ,{'OPULENT_SETUP_TOKEN':'short'}):
            with self.assertRaises(RuntimeError):create_app(start_worker=False)


if __name__=='__main__':
    unittest.main(verbosity=2)
