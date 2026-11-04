"""Bounded local subprocess boundary for an explicitly configured model request.

This is not a security sandbox or a real-time guarantee. The parent bounds its
communication wait, terminates a timed-out worker, and never retries the POST.
Already accepted provider work or transmitted context cannot be recalled.
"""
from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

from .model_transport_worker import (MAX_JOB_BYTES, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES,
                                     MAX_WAIT_SECONDS, bounded_timeout,
                                     model_authorization, model_endpoint)


class ModelTransportError(RuntimeError):
    """A deliberately content-free transport failure."""


def _worker_environment() -> dict:
    # Isolated startup ignores Python environment and site hooks. Only Windows
    # system locations survive; no keys, proxies, PATH or TLS override variables.
    return {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR') if key in os.environ}


class _BoundedResponse(io.BytesIO):
    # The worker has already checked these properties before emitting bytes.
    status = 200
    headers = {'Content-Encoding': 'identity'}


class BoundedModelOpener:
    """The reasoner's default opener; only its fixed JSON POST shape is allowed.

    A new worker handles exactly one request. subprocess.run kills and reaps it
    after a communication timeout; process creation/termination still depends on
    the OS. stdout contains at most one bounded body, and stderr is discarded.
    """

    def open(self, request, *, timeout=MAX_WAIT_SECONDS):
        timeout = bounded_timeout(timeout)
        if not isinstance(request, urllib.request.Request) or request.get_method() != 'POST':
            raise ValueError('only a model JSON POST is supported')
        url = model_endpoint(request.full_url)
        payload = request.data
        if type(payload) is not bytes or not 0 < len(payload) <= MAX_REQUEST_BYTES:
            raise ValueError('invalid model request byte count')
        headers = {name.lower(): value for name, value in request.header_items()}
        required = {'content-type': 'application/json', 'accept': 'application/json', 'accept-encoding': 'identity'}
        if any(headers.get(name) != value for name, value in required.items()) or set(headers) - (set(required) | {'authorization'}):
            raise ValueError('unsupported model request headers')
        authorization = headers.get('authorization', '')
        if not isinstance(authorization, str) or (authorization and not authorization.startswith('Bearer ')):
            raise ValueError('invalid model authorization header')
        key = model_authorization(authorization[7:] if authorization else '')
        job = {'url': url, 'api_key': key, 'payload_base64': base64.b64encode(payload).decode('ascii'),
               'timeout_seconds': timeout}
        wire = json.dumps(job, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
        if len(wire) > MAX_JOB_BYTES:
            raise ValueError('model transport job exceeds byte limit')
        try:
            result = subprocess.run([str(Path(sys.executable).resolve()), '-I', '-S',
                str(Path(__file__).with_name('model_transport_worker.py').resolve())],
                input=wire, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout,
                env=_worker_environment(), cwd=str(Path(__file__).resolve().parent),
                shell=False, close_fds=True, check=False)
        except subprocess.TimeoutExpired:
            raise ModelTransportError('Model request timed out. No automatic retry; provider outcome may be uncertain.') from None
        except (OSError, ValueError):
            raise ModelTransportError('Model transport could not complete. No automatic retry.') from None
        if result.returncode != 0 or type(result.stdout) is not bytes or len(result.stdout) > MAX_RESPONSE_BYTES:
            raise ModelTransportError('Model transport rejected the response. No automatic retry.')
        return _BoundedResponse(result.stdout)
