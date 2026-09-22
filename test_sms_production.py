import os
import unittest
from unittest.mock import patch

import sms_production_test


class FakeSms:
    def __init__(self):
        self.calls = []

    def send(self, message, recipients):
        self.calls.append((message, recipients))
        return {'SMSMessageData': {'Recipients': [{
            'number': recipients[0], 'status': 'Success', 'statusCode': 101,
            'messageId': 'ATXid_production_test', 'cost': 'UGX 35.0000'}]}}


class ProductionSmsTest(unittest.TestCase):
    def setUp(self):
        self.env = {
            'AFRICASTALKING_PRODUCTION_USERNAME': 'Opulent Condo',
            'AFRICASTALKING_PRODUCTION_API_KEY': 'test-only-key',
            'AFRICASTALKING_PRODUCTION_TEST_NUMBER': '+256764426108',
            'OPULENT_PRODUCTION_SMS_TEST_ENABLED': 'true',
        }

    def test_one_fixed_message_to_configured_number(self):
        fake = FakeSms()
        with patch.dict(os.environ, self.env, clear=False):
            result = sms_production_test.send_test_sms(True, fake)
        self.assertEqual(fake.calls, [(sms_production_test.TEST_MESSAGE, ['+256764426108'])])
        self.assertEqual(result['environment'], 'production')
        self.assertNotIn('test-only-key', repr(result))

    def test_requires_both_lock_and_explicit_confirmation(self):
        with patch.dict(os.environ, self.env, clear=False):
            with self.assertRaisesRegex(sms_production_test.ProductionSmsError, 'confirmation'):
                sms_production_test.send_test_sms(False, FakeSms())
        locked = {**self.env, 'OPULENT_PRODUCTION_SMS_TEST_ENABLED': 'false'}
        with patch.dict(os.environ, locked, clear=False):
            with self.assertRaisesRegex(sms_production_test.ProductionSmsError, 'locked'):
                sms_production_test.send_test_sms(True, FakeSms())

    def test_rejects_wrong_username_missing_key_and_bad_number(self):
        cases = [
            ({**self.env, 'AFRICASTALKING_PRODUCTION_USERNAME': 'sandbox'}, 'Sandbox credentials'),
            ({**self.env, 'AFRICASTALKING_PRODUCTION_USERNAME': ''}, 'USERNAME is not configured'),
            ({**self.env, 'AFRICASTALKING_PRODUCTION_API_KEY': ''}, 'not configured'),
            ({**self.env, 'AFRICASTALKING_PRODUCTION_TEST_NUMBER': '0764426108'}, 'international format'),
        ]
        for environment, message in cases:
            with self.subTest(message=message), patch.dict(os.environ, environment, clear=False):
                with self.assertRaisesRegex(sms_production_test.ProductionSmsError, message):
                    sms_production_test.send_test_sms(True, FakeSms())


if __name__ == '__main__':
    unittest.main()
