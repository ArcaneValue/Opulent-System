"""Guarded one-message EgoSMS production smoke test.

This command is deliberately separate from reminder processing. It has no
recipient argument and can only use the single number configured in Railway. It
requires both a temporary enable switch and an explicit confirmation flag.
"""
import argparse
import json
import os

import egosms

TEST_MESSAGE = 'Opulent Condo System production SMS test. No payment is due from this message.'
ENDPOINT = egosms.LIVE_ENDPOINT


class ProductionSmsError(RuntimeError):
    pass


def production_config():
    username = os.environ.get('EGOSMS_USERNAME', '').strip()
    api_key = os.environ.get('EGOSMS_API_KEY', '').strip()
    number = os.environ.get('EGOSMS_PRODUCTION_TEST_NUMBER', '').replace(' ', '')
    enabled = os.environ.get('OPULENT_PRODUCTION_SMS_TEST_ENABLED', '').strip().lower()
    if enabled != 'true':
        raise ProductionSmsError('Production SMS test is locked. Set OPULENT_PRODUCTION_SMS_TEST_ENABLED=true temporarily.')
    if not username:
        raise ProductionSmsError('EGOSMS_USERNAME is not configured.')
    if not api_key:
        raise ProductionSmsError('EGOSMS_API_KEY is not configured.')
    try:
        number = egosms.normalize_number(number)
    except egosms.EgoSmsError as exc:
        raise ProductionSmsError('EGOSMS_PRODUCTION_TEST_NUMBER must use international format, for example 256 followed by digits.') from exc
    return username, api_key, number


def send_test_sms(confirmed=False, transport=None):
    """Send one fixed message to the one configured production test number."""
    if not confirmed:
        raise ProductionSmsError('Explicit --confirm-send-one confirmation is required.')
    username, api_key, number = production_config()
    try:
        result = egosms.send_one(
            number, TEST_MESSAGE,
            username=username, api_key=api_key,
            sender_id=os.environ.get('EGOSMS_SENDER_ID', egosms.DEFAULT_SENDER_ID),
            endpoint=ENDPOINT, transport=transport,
        )
    except egosms.EgoSmsError as exc:
        raise ProductionSmsError(str(exc)) from exc
    return {'environment': 'production', 'number': number, 'status': result['status'],
            'cost': result['cost'], 'follow_up_code': result['follow_up_code']}


def main():
    parser = argparse.ArgumentParser(description='Send one fixed EgoSMS production test SMS.')
    parser.add_argument('--confirm-send-one', action='store_true', help='Confirm one send to the configured test number.')
    args = parser.parse_args()
    try:
        print(json.dumps(send_test_sms(args.confirm_send_one), indent=2))
    except ProductionSmsError as exc:
        raise SystemExit(f'Production SMS not sent: {exc}')


if __name__ == '__main__':
    main()
