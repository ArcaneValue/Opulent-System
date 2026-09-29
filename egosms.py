"""EgoSMS (Pahappa Comms) provider client.

Nothing is transmitted unless a caller explicitly invokes it. Callers read
credentials from the process environment; this module never logs or returns
secrets. Failures are split into transport failures (no response, outcome
unknown) and API-level rejections (a response arrived and said "Failed"), because
only the former may be retried.

Reference: https://developers.pahappa.com
"""
import json
import re
import urllib.error
import urllib.request

LIVE_ENDPOINT = 'https://comms.egosms.co/api/v1/json/'
SANDBOX_ENDPOINT = 'https://comms-test.pahappa.net/api/v1/json/'
DEFAULT_SENDER_ID = 'EgoSMS'
MAX_BATCH = 1000
MAX_SENDER_ID = 11


class EgoSmsError(RuntimeError):
    """An API-level rejection or an invalid request. Retrying unchanged will fail again."""


class EgoSmsTransportError(EgoSmsError):
    """No response was received, so the send outcome is unknown. Reconcile before resending."""


def normalize_number(phone):
    """Return an international number without a leading + or 00, as EgoSMS requires."""
    digits = re.sub(r'[\s()\-]', '', str(phone))
    if digits.startswith('+'):
        digits = digits[1:]
    elif digits.startswith('00'):
        digits = digits[2:]
    if not re.fullmatch(r'[1-9]\d{7,14}', digits):
        raise EgoSmsError('Use an international number without + or 00, for example 256 followed by digits.')
    return digits


def _http_post(endpoint, payload, timeout):
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8', 'replace')
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise EgoSmsTransportError('EgoSMS did not respond; the send outcome is unknown.') from exc
    try:
        body = json.loads(raw)
    except ValueError as exc:
        raise EgoSmsError('EgoSMS returned an unexpected response.') from exc
    if not isinstance(body, dict):
        raise EgoSmsError('EgoSMS returned an unexpected response.')
    return body


def _parse(message):
    cost = message.get('Cost')
    code = message.get('MsgFollowUpUniqueCode')
    return {
        'status': 'accepted',
        'cost': cost,
        'follow_up_code': str(code) if code is not None else '',
    }


def send_messages(messages, *, username, api_key, sender_id=DEFAULT_SENDER_ID,
                  endpoint=LIVE_ENDPOINT, priority=1, timeout=20, transport=None):
    """Send one or more messages through EgoSMS.

    messages: iterable of {'number': str, 'message': str}. Returns a small dict of
    non-secret metadata on acceptance, or raises EgoSmsError.
    """
    if not username or not api_key:
        raise EgoSmsError('EgoSMS credentials are not configured.')
    messages = list(messages)
    if not messages:
        raise EgoSmsError('No messages to send.')
    if len(messages) > MAX_BATCH:
        raise EgoSmsError('EgoSMS accepts at most 1000 messages per request.')
    sender_id = (sender_id or DEFAULT_SENDER_ID).strip()
    if not 1 <= len(sender_id) <= MAX_SENDER_ID:
        raise EgoSmsError('EgoSMS sender ID must be 1 to 11 characters.')
    if priority not in (0, 1, 2, 3, 4):
        raise EgoSmsError('EgoSMS priority must be between 0 and 4.')
    msgdata = []
    for item in messages:
        body = str(item['message'])
        if not body:
            raise EgoSmsError('EgoSMS message text cannot be empty.')
        msgdata.append({'number': normalize_number(item['number']), 'message': body,
                        'senderid': sender_id, 'priority': priority})
    payload = {'method': 'SendSms', 'userdata': {'username': username, 'password': api_key},
               'msgdata': msgdata}
    response = (transport or _http_post)(endpoint, payload, timeout)
    if str(response.get('Status', '')).strip().lower() == 'ok':
        return _parse(response)
    raise EgoSmsError('EgoSMS rejected the request: ' + str(response.get('Message', 'unknown error')))


def send_one(number, message, **kwargs):
    """Send a single message and return its acceptance metadata."""
    return send_messages([{'number': number, 'message': message}], **kwargs)


def balance(*, username, api_key, endpoint=LIVE_ENDPOINT, timeout=20, transport=None):
    """Return the account credit balance as an integer, or raise EgoSmsError."""
    if not username or not api_key:
        raise EgoSmsError('EgoSMS credentials are not configured.')
    payload = {'method': 'Balance', 'userdata': {'username': username, 'password': api_key}}
    response = (transport or _http_post)(endpoint, payload, timeout)
    if str(response.get('Status', '')).strip().lower() == 'ok':
        return response.get('Balance')
    raise EgoSmsError('EgoSMS rejected the request: ' + str(response.get('Message', 'unknown error')))
