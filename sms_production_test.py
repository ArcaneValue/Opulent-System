"""Guarded one-message Africa's Talking production smoke test.

This command is deliberately separate from reminder processing. It has no
recipient argument and can only use the single number configured in Railway.
"""
import argparse
import json
import os
import re

EXPECTED_USERNAME = 'Opulent Condo'
TEST_MESSAGE = 'Opulent Condo System production SMS test. No payment is due from this message.'


class ProductionSmsError(RuntimeError):
    pass


def production_config():
    username = os.environ.get('AFRICASTALKING_PRODUCTION_USERNAME', '').strip()
    api_key = os.environ.get('AFRICASTALKING_PRODUCTION_API_KEY', '').strip()
    phone = os.environ.get('AFRICASTALKING_PRODUCTION_TEST_NUMBER', '').replace(' ', '')
    enabled = os.environ.get('OPULENT_PRODUCTION_SMS_TEST_ENABLED', '').strip().lower()
    if enabled != 'true':
        raise ProductionSmsError('Production SMS test is locked. Set OPULENT_PRODUCTION_SMS_TEST_ENABLED=true temporarily.')
    if username != EXPECTED_USERNAME:
        raise ProductionSmsError(f'AFRICASTALKING_PRODUCTION_USERNAME must be exactly {EXPECTED_USERNAME}.')
    if username.lower() == 'sandbox':
        raise ProductionSmsError('Sandbox credentials cannot be used for the production test.')
    if not api_key:
        raise ProductionSmsError('AFRICASTALKING_PRODUCTION_API_KEY is not configured.')
    if not re.fullmatch(r'\+[1-9]\d{7,14}', phone):
        raise ProductionSmsError('AFRICASTALKING_PRODUCTION_TEST_NUMBER must use international format.')
    return username, api_key, phone


def send_test_sms(confirmed=False, sms_service=None):
    """Send one fixed message to the one configured production test number."""
    if not confirmed:
        raise ProductionSmsError('Explicit --confirm-send-one confirmation is required.')
    username, api_key, phone = production_config()
    if sms_service is None:
        import africastalking
        africastalking.initialize(username, api_key)
        sms_service = africastalking.SMS
    response = sms_service.send(TEST_MESSAGE, [phone])
    try:
        recipients = response['SMSMessageData']['Recipients']
        recipient = recipients[0]
        if len(recipients) != 1:
            raise ValueError()
        return {
            'environment': 'production',
            'number': str(recipient.get('number', phone)),
            'status': str(recipient.get('status', 'Unknown')),
            'status_code': int(recipient.get('statusCode', -1)),
            'message_id': str(recipient.get('messageId', '')),
            'cost': str(recipient.get('cost', '')),
        }
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProductionSmsError('Africa\'s Talking returned an unexpected production response.') from exc


def main():
    parser = argparse.ArgumentParser(description='Send one fixed Africa\'s Talking production test SMS.')
    parser.add_argument('--confirm-send-one', action='store_true', help='Confirm one send to the configured test number.')
    args = parser.parse_args()
    try:
        print(json.dumps(send_test_sms(args.confirm_send_one), indent=2))
    except ProductionSmsError as exc:
        raise SystemExit(f'Production SMS not sent: {exc}')


if __name__ == '__main__':
    main()
