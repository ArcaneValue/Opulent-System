"""Explicit one-message EgoSMS sandbox smoke test.

This module is intentionally separate from reminder processing. It always uses
the EgoSMS sandbox endpoint, cannot use live credentials, and cannot select
customer records from the Opulent database.
"""
import argparse
import json
import os

import egosms

TEST_MESSAGE = 'Opulent Condo System sandbox test. No payment reminder was sent.'
ENDPOINT = egosms.SANDBOX_ENDPOINT


class SandboxSmsError(RuntimeError):
    pass


def sandbox_credentials():
    username = os.environ.get('EGOSMS_SANDBOX_USERNAME', '').strip()
    api_key = os.environ.get('EGOSMS_SANDBOX_API_KEY', '').strip()
    if not username or not api_key:
        raise SandboxSmsError('EGOSMS_SANDBOX_USERNAME and EGOSMS_SANDBOX_API_KEY must both be configured.')
    return username, api_key


def validate_phone(phone):
    try:
        return egosms.normalize_number(phone)
    except egosms.EgoSmsError as exc:
        raise SandboxSmsError('Use an international simulator number without + or 00, for example 256 followed by digits.') from exc


def send_test_sms(phone, transport=None):
    """Send one fixed message to the EgoSMS sandbox and return safe metadata."""
    username, api_key = sandbox_credentials()
    number = validate_phone(phone)
    try:
        result = egosms.send_one(
            number, TEST_MESSAGE,
            username=username, api_key=api_key,
            sender_id=os.environ.get('EGOSMS_SENDER_ID', egosms.DEFAULT_SENDER_ID),
            endpoint=ENDPOINT, transport=transport,
        )
    except egosms.EgoSmsError as exc:
        raise SandboxSmsError(str(exc)) from exc
    return {'environment': 'sandbox', 'number': number, 'status': result['status'],
            'cost': result['cost'], 'follow_up_code': result['follow_up_code']}


def main():
    parser = argparse.ArgumentParser(description='Send one fixed SMS to the EgoSMS sandbox endpoint.')
    parser.add_argument('phone', help='Simulator phone without + or 00, such as 256...')
    args = parser.parse_args()
    try:
        print(json.dumps(send_test_sms(args.phone), indent=2))
    except SandboxSmsError as exc:
        raise SystemExit(f'Sandbox SMS not sent: {exc}')


if __name__ == '__main__':
    main()
