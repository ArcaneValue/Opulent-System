import os
import unittest
from unittest.mock import patch

import egosms
import sms_production_test


def fake_transport(response=None, captured=None):
    def transport(endpoint, payload, timeout):
        if captured is not None:
            captured['endpoint'], captured['payload'] = endpoint, payload
        if response is not None:
            return response
        return {'Status': 'OK', 'Cost': 35, 'MsgFollowUpUniqueCode': 'prod-code'}
    return transport


class ProductionSmsTest(unittest.TestCase):
    def setUp(self):
        self.env = {
            'EGOSMS_USERNAME': 'opulent-live',
            'EGOSMS_API_KEY': 'test-only-key',
            'EGOSMS_PRODUCTION_TEST_NUMBER': '+256764426108',
            'OPULENT_PRODUCTION_SMS_TEST_ENABLED': 'true',
        }

    def test_one_fixed_message_to_the_configured_number(self):
        captured = {}
        with patch.dict(os.environ, self.env, clear=False):
            result = sms_production_test.send_test_sms(True, fake_transport(captured=captured))
        self.assertEqual(captured['endpoint'], egosms.LIVE_ENDPOINT)
        self.assertEqual(captured['payload']['msgdata'][0]['number'], '256764426108')
        self.assertEqual(captured['payload']['msgdata'][0]['message'], sms_production_test.TEST_MESSAGE)
        self.assertEqual(result['environment'], 'production')
        self.assertNotIn('test-only-key', repr(result))

    def test_requires_both_lock_and_explicit_confirmation(self):
        with patch.dict(os.environ, self.env, clear=False):
            with self.assertRaisesRegex(sms_production_test.ProductionSmsError, 'confirmation'):
                sms_production_test.send_test_sms(False, fake_transport())
        locked = {**self.env, 'OPULENT_PRODUCTION_SMS_TEST_ENABLED': 'false'}
        with patch.dict(os.environ, locked, clear=False):
            with self.assertRaisesRegex(sms_production_test.ProductionSmsError, 'locked'):
                sms_production_test.send_test_sms(True, fake_transport())

    def test_rejects_missing_credentials_and_bad_number(self):
        cases = [
            ({**self.env, 'EGOSMS_USERNAME': ''}, 'USERNAME is not configured'),
            ({**self.env, 'EGOSMS_API_KEY': ''}, 'not configured'),
            ({**self.env, 'EGOSMS_PRODUCTION_TEST_NUMBER': '0764426108'}, 'international format'),
        ]
        for environment, message in cases:
            with self.subTest(message=message), patch.dict(os.environ, environment, clear=False):
                with self.assertRaisesRegex(sms_production_test.ProductionSmsError, message):
                    sms_production_test.send_test_sms(True, fake_transport())


if __name__ == '__main__':
    unittest.main()
