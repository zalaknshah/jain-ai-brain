"""One bounded model POST. No source files, engine, memory or credential storage."""
from __future__ import annotations

import base64
import sys
import ipaddress
import json
import math
import urllib.parse
import urllib.request

# Keep this executable worker standard-library-only: -I -S intentionally avoids
# importing package startup, application state, site hooks or third-party code.
MAX_REQUEST_BYTES = 128 * 1024
MAX_RESPONSE_BYTES = 64 * 1024
MAX_JOB_BYTES = 224 * 1024
MAX_WAIT_SECONDS = 30


def model_endpoint(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2048 or url.strip() != url or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise ValueError('invalid model endpoint')
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.username is not None or parsed.password is not None or parsed.fragment or not parsed.hostname or parsed.port == 0:
            raise ValueError('model endpoint cannot contain credentials, fragments or an invalid authority')
        if parsed.scheme == 'https':
            return url
        if parsed.scheme == 'http' and '%' not in parsed.hostname and ipaddress.ip_address(parsed.hostname).is_loopback:
            return url
    except ValueError as error:
        raise ValueError('model endpoint must use HTTPS, or HTTP with a literal loopback address') from error
    raise ValueError('model endpoint must use HTTPS, or HTTP with a literal loopback address')


def model_authorization(api_key: str) -> str:
    if not isinstance(api_key, str) or len(api_key) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in api_key):
        raise ValueError('invalid model authorization value')
    return api_key


def bounded_timeout(value) -> float:
    if type(value) not in (int, float) or not 0 < value <= MAX_WAIT_SECONDS or not math.isfinite(value):
        raise ValueError('model wait must be finite, positive and at most 30 seconds')
    return float(value)


def _strict_json(raw: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate job key')
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError('nonfinite job value')

    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


class _NoModelRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_job(raw: bytes) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_JOB_BYTES:
        raise ValueError('invalid model transport job size')
    job = _strict_json(raw)
    fields = {'url', 'api_key', 'payload_base64', 'timeout_seconds'}
    if type(job) is not dict or set(job) != fields:
        raise ValueError('invalid model transport job schema')
    url = model_endpoint(job['url'])
    key = model_authorization(job['api_key'])
    timeout = bounded_timeout(job['timeout_seconds'])
    encoded = job['payload_base64']
    if type(encoded) is not str or not encoded.isascii() or len(encoded) > 4 * ((MAX_REQUEST_BYTES + 2) // 3):
        raise ValueError('invalid model payload encoding')
    payload = base64.b64decode(encoded, validate=True)
    if not 0 < len(payload) <= MAX_REQUEST_BYTES:
        raise ValueError('invalid model payload size')
    # Preserve request bytes exactly; the reasoner owns the JSON/context schema.
    payload.decode('utf-8', errors='strict')
    return {'url': url, 'api_key': key, 'payload': payload, 'timeout_seconds': timeout}


def request_once(job: dict) -> bytes:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoModelRedirect())
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json', 'Accept-Encoding': 'identity'}
    if job['api_key']:
        headers['Authorization'] = 'Bearer ' + job['api_key']
    request = urllib.request.Request(job['url'], data=job['payload'], headers=headers, method='POST')
    with opener.open(request, timeout=job['timeout_seconds']) as response:
        encodings = response.headers.get_all('Content-Encoding', [])
        if response.status != 200 or len(encodings) > 1 or (encodings and encodings[0].lower() != 'identity'):
            raise ValueError('unexpected model response status or encoding')
        lengths = response.headers.get_all('Content-Length', [])
        transfers = response.headers.get_all('Transfer-Encoding', [])
        if len(lengths) > 1 or len(transfers) > 1 or (lengths and transfers):
            raise ValueError('ambiguous model response framing')
        if transfers and transfers[0].lower() != 'chunked':
            raise ValueError('unsupported model response transfer encoding')
        expected = None
        if lengths:
            if not lengths[0].isascii() or not lengths[0].isdigit() or len(lengths[0]) > 10:
                raise ValueError('invalid model response content length')
            expected = int(lengths[0])
            if expected > MAX_RESPONSE_BYTES:
                raise ValueError('model response exceeds byte limit')
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES or (expected is not None and len(raw) != expected):
        raise ValueError('model response size is invalid or incomplete')
    return raw


def main() -> None:
    try:
        raw = sys.stdin.buffer.read(MAX_JOB_BYTES + 1)
        job = validate_job(raw)
        body = request_once(job)
        # Emit only after successful validation, never partial provider data or diagnostics.
        sys.stdout.buffer.write(body)
        sys.stdout.buffer.flush()
    except Exception:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
