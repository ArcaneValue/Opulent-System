import unittest

import egosms


class NormalizeNumberTest(unittest.TestCase):
    def test_accepts_and_strips_international_prefixes(self):
        self.assertEqual(egosms.normalize_number('+256700111222'), '256700111222')
        self.assertEqual(egosms.normalize_number('00256700111222'), '256700111222')
        self.assertEqual(egosms.normalize_number(' 256 700 111 222 '), '256700111222')
        self.assertEqual(egosms.normalize_number('+256 (700) 111-222'), '256700111222')

    def test_rejects_local_or_invalid_numbers(self):
        for value in ('0700000001', '', 'abc', '+0123', '256'):
            with self.subTest(value=value), self.assertRaises(egosms.EgoSmsError):
                egosms.normalize_number(value)


class SendMessagesTest(unittest.TestCase):
    def test_builds_the_documented_payload_and_parses_success(self):
        seen = {}

        def transport(endpoint, payload, timeout):
            seen['endpoint'], seen['payload'] = endpoint, payload
            return {'Status': 'OK', 'Cost': 0.09, 'MsgFollowUpUniqueCode': 'abc123'}

        result = egosms.send_messages([{'number': '+256700111222', 'message': 'Hello'}],
                                      username='api-user', api_key='api-key',
                                      sender_id='EgoSMS', endpoint=egosms.SANDBOX_ENDPOINT,
                                      transport=transport)
        self.assertEqual(result['status'], 'accepted')
        self.assertEqual(result['follow_up_code'], 'abc123')
        self.assertEqual(result['cost'], 0.09)
        self.assertEqual(seen['endpoint'], egosms.SANDBOX_ENDPOINT)
        self.assertEqual(seen['payload']['method'], 'SendSms')
        self.assertEqual(seen['payload']['userdata'], {'username': 'api-user', 'password': 'api-key'})
        self.assertEqual(seen['payload']['msgdata'][0]['number'], '256700111222')
        self.assertEqual(seen['payload']['msgdata'][0]['senderid'], 'EgoSMS')
        self.assertEqual(seen['payload']['msgdata'][0]['priority'], 1)

    def test_api_level_failure_raises(self):
        def transport(endpoint, payload, timeout):
            return {'Status': 'Failed', 'Message': 'Wrong Username or Password.'}

        with self.assertRaisesRegex(egosms.EgoSmsError, 'Wrong Username'):
            egosms.send_messages([{'number': '256700111222', 'message': 'Hi'}],
                                 username='u', api_key='k', transport=transport)

    def test_transport_failure_has_its_own_type(self):
        def transport(endpoint, payload, timeout):
            raise egosms.EgoSmsTransportError('no response')

        with self.assertRaises(egosms.EgoSmsTransportError):
            egosms.send_messages([{'number': '256700111222', 'message': 'Hi'}],
                                 username='u', api_key='k', transport=transport)

    def test_rejects_missing_credentials_sender_id_and_batch(self):
        good = lambda endpoint, payload, timeout: {'Status': 'OK', 'Cost': 1, 'MsgFollowUpUniqueCode': 'x'}
        with self.assertRaisesRegex(egosms.EgoSmsError, 'not configured'):
            egosms.send_messages([{'number': '256700111222', 'message': 'Hi'}], username='', api_key='', transport=good)
        with self.assertRaisesRegex(egosms.EgoSmsError, 'sender ID'):
            egosms.send_messages([{'number': '256700111222', 'message': 'Hi'}], username='u', api_key='k', sender_id='this-is-too-long', transport=good)
        with self.assertRaisesRegex(egosms.EgoSmsError, 'at most 1000'):
            egosms.send_messages([{'number': '256700111222', 'message': 'Hi'}] * 1001, username='u', api_key='k', transport=good)


class BalanceTest(unittest.TestCase):
    def test_balance_returns_the_reported_value(self):
        def transport(endpoint, payload, timeout):
            self.assertEqual(payload['method'], 'Balance')
            return {'Status': 'OK', 'Balance': 2700}

        self.assertEqual(egosms.balance(username='u', api_key='k', transport=transport), 2700)


if __name__ == '__main__':
    unittest.main()
