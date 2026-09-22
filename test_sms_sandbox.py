import os
import unittest
from unittest.mock import patch

import sms_sandbox


class FakeSms:
    def __init__(self):
        self.calls = []

    def send(self, message, recipients):
        self.calls.append((message, recipients))
        return {'SMSMessageData': {'Recipients': [{
            'number': recipients[0], 'status': 'Success', 'statusCode': 101,
            'messageId': 'ATXid_sandbox_test', 'cost': 'KES 0.8000'}]}}


class SandboxSmsTest(unittest.TestCase):
    def test_one_fixed_sandbox_message(self):
        fake = FakeSms()
        with patch.dict(os.environ, {'AFRICASTALKING_USERNAME':'sandbox', 'AFRICASTALKING_API_KEY':'test-only-key'}, clear=False):
            result = sms_sandbox.send_test_sms('+256700000001', fake)
        self.assertEqual(fake.calls, [(sms_sandbox.TEST_MESSAGE, ['+256700000001'])])
        self.assertEqual(result['environment'], 'sandbox')
        self.assertEqual(result['status_code'], 101)
        self.assertNotIn('test-only-key', repr(result))

    def test_rejects_live_username_missing_key_and_bad_number(self):
        with patch.dict(os.environ, {'AFRICASTALKING_USERNAME':'opulent-live', 'AFRICASTALKING_API_KEY':'secret'}, clear=False):
            with self.assertRaisesRegex(sms_sandbox.SandboxSmsError, 'exactly sandbox'):
                sms_sandbox.send_test_sms('+256700000001', FakeSms())
        with patch.dict(os.environ, {'AFRICASTALKING_USERNAME':'sandbox', 'AFRICASTALKING_API_KEY':''}, clear=False):
            with self.assertRaisesRegex(sms_sandbox.SandboxSmsError, 'not configured'):
                sms_sandbox.send_test_sms('+256700000001', FakeSms())
        with patch.dict(os.environ, {'AFRICASTALKING_USERNAME':'sandbox', 'AFRICASTALKING_API_KEY':'secret'}, clear=False):
            with self.assertRaisesRegex(sms_sandbox.SandboxSmsError, 'international simulator'):
                sms_sandbox.send_test_sms('0700000001', FakeSms())

    def test_rejects_ambiguous_provider_response(self):
        class Ambiguous:
            def send(self, message, recipients):
                return {'SMSMessageData': {'Recipients': []}}
        with patch.dict(os.environ, {'AFRICASTALKING_USERNAME':'sandbox', 'AFRICASTALKING_API_KEY':'secret'}, clear=False):
            with self.assertRaisesRegex(sms_sandbox.SandboxSmsError, 'unexpected'):
                sms_sandbox.send_test_sms('+256700000001', Ambiguous())


if __name__ == '__main__':
    unittest.main()
