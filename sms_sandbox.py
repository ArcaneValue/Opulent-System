"""Explicit one-message Africa's Talking Sandbox smoke test.

This module is intentionally separate from reminder processing. It cannot use live
credentials or select customer records from the Opulent database.
"""
import argparse
import json
import os
import re

TEST_MESSAGE = 'Opulent Condo System sandbox test. No payment reminder was sent.'


class SandboxSmsError(RuntimeError):
    pass


def sandbox_credentials():
    username = os.environ.get('AFRICASTALKING_USERNAME', '').strip()
    api_key = os.environ.get('AFRICASTALKING_API_KEY', '').strip()
    if username != 'sandbox':
        raise SandboxSmsError('AFRICASTALKING_USERNAME must be exactly sandbox. Live SMS is disabled.')
    if not api_key:
        raise SandboxSmsError('AFRICASTALKING_API_KEY is not configured.')
    return username, api_key


def validate_phone(phone):
    phone = str(phone).strip()
    if not re.fullmatch(r'\+[1-9]\d{7,14}', phone):
        raise SandboxSmsError('Use an international simulator number, for example +256 followed by digits.')
    return phone


def send_test_sms(phone, sms_service=None):
    """Send one fixed message to the Sandbox simulator and return safe metadata."""
    username, api_key = sandbox_credentials()
    phone = validate_phone(phone)
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
            'environment': 'sandbox',
            'number': str(recipient.get('number', phone)),
            'status': str(recipient.get('status', 'Unknown')),
            'status_code': int(recipient.get('statusCode', -1)),
            'message_id': str(recipient.get('messageId', '')),
            'cost': str(recipient.get('cost', '')),
        }
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise SandboxSmsError('Africa\'s Talking returned an unexpected sandbox response.') from exc


def main():
    parser = argparse.ArgumentParser(description='Send one fixed SMS to the Africa\'s Talking Sandbox simulator.')
    parser.add_argument('phone', help='Simulator phone in international format, such as +256...')
    args = parser.parse_args()
    try:
        print(json.dumps(send_test_sms(args.phone), indent=2))
    except SandboxSmsError as exc:
        raise SystemExit(f'Sandbox SMS not sent: {exc}')


if __name__ == '__main__':
    main()
