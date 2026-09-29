import os
import unittest
from unittest.mock import patch

import egosms
import sms_sandbox


def fake_transport(calls, response=None):
    def transport(endpoint, payload, timeout):
        calls.append((endpoint, payload))
        if response is not None:
            return response
        return {'Status': 'OK', 'Cost': 35, 'MsgFollowUpUniqueCode': 'sandbox-code'}
    return transport


class SandboxSmsTest(unittest.TestCase):
    def test_one_fixed_sandbox_message(self):
        calls = []
        with patch.dict(os.environ, {'EGOSMS_SANDBOX_USERNAME': 'sandbox-user', 'EGOSMS_SANDBOX_API_KEY': 'test-only-key'}, clear=False):
            result = sms_sandbox.send_test_sms('+256700000001', fake_transport(calls))
        self.assertEqual(len(calls), 1)
        endpoint, payload = calls[0]
        self.assertEqual(endpoint, egosms.SANDBOX_ENDPOINT)
        self.assertEqual(payload['msgdata'][0]['message'], sms_sandbox.TEST_MESSAGE)
        self.assertEqual(payload['msgdata'][0]['number'], '256700000001')
        self.assertEqual(result['environment'], 'sandbox')
        self.assertEqual(result['status'], 'accepted')
        self.assertNotIn('test-only-key', repr(result))

    def test_requires_both_credentials(self):
        for environment in ({'EGOSMS_SANDBOX_USERNAME': '', 'EGOSMS_SANDBOX_API_KEY': 'key'},
                            {'EGOSMS_SANDBOX_USERNAME': 'user', 'EGOSMS_SANDBOX_API_KEY': ''}):
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=False):
                with self.assertRaisesRegex(sms_sandbox.SandboxSmsError, 'must both be configured'):
                    sms_sandbox.send_test_sms('256700000001', fake_transport([]))

    def test_rejects_a_local_number(self):
        with patch.dict(os.environ, {'EGOSMS_SANDBOX_USERNAME': 'user', 'EGOSMS_SANDBOX_API_KEY': 'key'}, clear=False):
            with self.assertRaisesRegex(sms_sandbox.SandboxSmsError, 'international simulator'):
                sms_sandbox.send_test_sms('0700000001', fake_transport([]))

    def test_rejects_a_provider_rejection(self):
        response = {'Status': 'Failed', 'Message': 'Wrong Username or Password.'}
        with patch.dict(os.environ, {'EGOSMS_SANDBOX_USERNAME': 'user', 'EGOSMS_SANDBOX_API_KEY': 'key'}, clear=False):
            with self.assertRaisesRegex(sms_sandbox.SandboxSmsError, 'Wrong Username'):
                sms_sandbox.send_test_sms('256700000001', fake_transport([], response))


if __name__ == '__main__':
    unittest.main()
