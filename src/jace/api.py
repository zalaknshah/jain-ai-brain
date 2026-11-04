from __future__ import annotations

import json
import os
import math
import re
import socket
import time
from threading import BoundedSemaphore, Lock, Timer
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from .auth import ApiAuthorization
from .engine import CognitiveEngine
from .limits import PeerRateLimiter, bounded_int
from .memory import MemoryDeletionConsentRequired, MemoryConflictError, validate_memory_revision
from .memory_scope import DEFAULT_SCOPE, validate_memory_scope
from .model_output import strict_json
from .simulator import decide_motion

MAX_BODY_BYTES = 64 * 1024
MAX_REQUEST_TARGET_BYTES = 8192
MAX_HEADER_BYTES = 16 * 1024
DEFAULT_ORIGINS = frozenset({'http://127.0.0.1:8080', 'http://localhost:8080'})


class JaceHTTPServer(ThreadingHTTPServer):
    # Wait for admitted handlers during close, before the shared engine closes.
    daemon_threads = False
    block_on_close = True

    def __init__(self, address, engine, authorization=None, allowed_origins=DEFAULT_ORIGINS, *,
                 request_timeout: float = 10.0, max_connections: int = 16,
                 rate_per_minute: int = 60, rate_burst: int = 30, rate_max_clients: int = 1024):
        if isinstance(request_timeout, bool) or not isinstance(request_timeout, (int, float)) or not math.isfinite(request_timeout) or not 0 < request_timeout <= 120:
            raise ValueError('request_timeout must be finite, positive and at most 120 seconds')
        self.request_timeout = float(request_timeout)
        self._connection_slots = BoundedSemaphore(bounded_int('max_connections', max_connections, 128))
        self.rate_limiter = PeerRateLimiter(rate_per_minute, rate_burst, rate_max_clients)
        self.engine = engine
        self.authorization = authorization or ApiAuthorization()
        self.allowed_origins = frozenset(allowed_origins)
        super().__init__(address, JaceHandler)

    def process_request(self, request, client_address):
        request.settimeout(self.request_timeout)
        if not self._connection_slots.acquire(blocking=False):
            try:
                request.settimeout(min(0.25, self.request_timeout))
                request.sendall(b'HTTP/1.0 503 Service Unavailable\r\nConnection: close\r\nRetry-After: 1\r\nContent-Length: 0\r\n\r\n')
            except OSError:
                pass
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._connection_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connection_slots.release()


class JaceHandler(BaseHTTPRequestHandler):
    server: JaceHTTPServer

    def handle_one_request(self) -> None:
        self._read_lock = Lock()
        self._read_complete = False
        self._read_expired = False
        self._read_deadline = time.monotonic() + self.server.request_timeout
        self._read_timer = Timer(self.server.request_timeout, self._expire_read)
        self._read_timer.daemon = True
        self._read_timer.start()
        try:
            super().handle_one_request()
        except (OSError, ConnectionError):
            pass  # Client disconnect or request-read deadline; never retry writes.
        finally:
            self._read_timer.cancel()
            self.close_connection = True

    def _expire_read(self) -> None:
        with self._read_lock:
            if self._read_complete:
                return
            self._read_expired = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _finish_read(self) -> None:
        with self._read_lock:
            if self._read_expired or time.monotonic() >= self._read_deadline:
                raise TimeoutError('request read deadline exceeded')
            self._read_complete = True
            self._read_timer.cancel()

    def parse_request(self) -> bool:
        if not super().parse_request():
            return False
        if len(self.path) > MAX_REQUEST_TARGET_BYTES:
            self._send(414, {'error': 'request target is too long'})
            return False
        if sum(len(key) + len(value) + 4 for key, value in self.headers.items()) > MAX_HEADER_BYTES:
            self._send(431, {'error': 'request headers are too large'})
            return False
        allowed, retry_after = self.server.rate_limiter.allow(self.client_address[0])
        if not allowed:
            self._send(429, {'error': 'request rate limit exceeded'}, retry_after=retry_after)
            return False
        try:
            self._body_length = self._validate_framing()
        except ValueError as exc:
            self._send(400, {'error': str(exc)})
            return False
        return True

    def _validate_framing(self) -> int:
        """Reject ambiguous framing before any method, especially deletion."""
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') is not None:
            raise ValueError('Transfer-Encoding is not supported')
        has_body = self.command in {'POST', 'PATCH'}
        if not lengths and not has_body:
            return 0
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise ValueError('one valid Content-Length is required')
        try:
            length = int(lengths[0])
        except ValueError:
            raise ValueError('one valid Content-Length is required') from None
        if length > MAX_BODY_BYTES:
            raise ValueError('request body is too large or has an invalid length')
        if not has_body and length != 0:
            raise ValueError('this method does not accept a request body')
        return length

    @property
    def engine(self) -> CognitiveEngine:
        return self.server.engine

    def _send(self, status: int, payload: object, *, retry_after: int | None = None) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Connection', 'close')
        self.close_connection = True
        if retry_after is not None:
            self.send_header('Retry-After', str(retry_after))
        origin = self.headers.get('Origin')
        if origin in self.server.allowed_origins:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.end_headers()
        self.wfile.write(data)

    def _authorize(self, requested_user: str | None = None) -> str | None:
        origin = self.headers.get('Origin')
        if origin and origin not in self.server.allowed_origins:
            self._send(403, {'error': 'origin is not allowed'})
            return None
        if not self.server.authorization.enabled:
            self._send(503, {'error': 'API authorization is not configured'})
            return None
        subject = self.server.authorization.authenticate(self.headers.get('Authorization', ''))
        if subject is None:
            self._send(401, {'error': 'valid bearer authorization is required'})
            return None
        if requested_user is not None and requested_user != subject:
            self._send(403, {'error': 'access to this user is not allowed'})
            return None
        return subject

    def _body(self) -> dict:
        if self.headers.get_content_type() != 'application/json':
            raise ValueError('Content-Type must be application/json')
        length = self._body_length
        raw = self.rfile.read(length)
        self._finish_read()
        if len(raw) != length:
            raise ValueError('request body is incomplete')
        try:
            body = strict_json(raw or b'{}')
        except ValueError:
            raise ValueError('request body must be valid JSON') from None
        if not isinstance(body, dict):
            raise ValueError('request body must be a JSON object')
        return body

    @staticmethod
    def _body_keys(body: dict, allowed: set[str]) -> None:
        if set(body) - allowed:
            raise ValueError('unsupported request field; use the documented exact field names')

    @staticmethod
    def _text(body: dict, name: str) -> str:
        value = body.get(name, '')
        if not isinstance(value, str):
            raise ValueError(f'{name} must be text')
        if len(value) > 10_000:
            raise ValueError(f'{name} must be 10,000 characters or fewer')
        return value

    def _memory_item_id(self, parsed) -> int:
        value = parsed.path.removeprefix('/v1/memory-item/')
        if self.path != parsed.path or parsed.params or not re.fullmatch(r'[1-9][0-9]{0,18}', value):
            raise ValueError('a canonical positive memory ID path without query parameters is required')
        memory_id = int(value)
        if memory_id > 2**63 - 1:
            raise ValueError('memory ID exceeds the supported range')
        return memory_id

    def _scope_query(self, parsed, allowed: set[str]) -> dict[str, str]:
        canonical = parsed.path + ('?' + parsed.query if parsed.query else '')
        if parsed.params or parsed.fragment or self.path != canonical:
            raise ValueError('a canonical path/query is required')
        params = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=12)
        if any(key not in allowed or len(values) != 1 for key, values in params.items()):
            raise ValueError('unknown or duplicate query parameter')
        return {key: values[0] for key, values in params.items()}

    def do_OPTIONS(self) -> None:
        self._finish_read()
        origin = self.headers.get('Origin')
        if origin not in self.server.allowed_origins:
            self._send(403, {'error': 'origin is not allowed'})
            return
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', origin)
        self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-JACE-Confirm-Delete, X-JACE-Confirm-Audit-Cleanup, X-JACE-If-Memory-Revision')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS')
        self.send_header('Connection', 'close')
        self.end_headers()

    def do_GET(self) -> None:
        self._finish_read()
        parsed = urlparse(self.path)
        if parsed.path == '/health':
            # Public liveness must not reveal private memory/graph statistics.
            self._send(200, {'status': 'ok', 'service': 'jace', 'authorization_configured': self.server.authorization.enabled, 'memory_scope_protocol': 1, 'memory_management_protocol': 1, 'cleaning_planner_protocol': 1})
            return
        subject = self._authorize()
        if subject is None:
            return
        if parsed.path.startswith('/v1/memory-item/'):
            try:
                memory_id = self._memory_item_id(parsed)
                self._send(200, self.engine.preview_memory_deletion(subject, memory_id))
            except LookupError:
                self._send(404, {'error': 'memory not found'})
            except ValueError as error:
                self._send(400, {'error': str(error)})
            except Exception:
                self._send(500, {'error': 'internal server error'})
            return
        if parsed.path == '/v1/canonical/search':
            try:
                query = parse_qs(parsed.query).get('q', [''])[0]
                self._send(200, {'entries': [item.to_dict() for item in self.engine.canonical.search(query)]})
            except ValueError as error:
                self._send(400, {'error': str(error)})
            return
        if parsed.path == '/v1/memory-scopes':
            try:
                self._scope_query(parsed, set())
                self._send(200, {'memory_scopes': self.engine.list_memory_scopes(subject)})
            except ValueError as error:
                self._send(400, {'error': str(error)})
            return
        if parsed.path == '/v1/graph/search':
            try:
                params = self._scope_query(parsed, {'q', 'user_id', 'memory_scope'})
                query = params.get('q', '')
                if params.get('user_id', subject) != subject:
                    self._send(403, {'error': 'access to this user is not allowed'})
                    return
                if not query:
                    raise ValueError('q is required')
                scope = validate_memory_scope(params.get('memory_scope', DEFAULT_SCOPE))
                hits = self.engine.search_graph(query, subject, memory_scope=scope)
                self._send(200, {'memory_scope': scope, 'hits': [vars(hit) for hit in hits]})
            except ValueError as error:
                self._send(400, {'error': str(error)})
            return
        if parsed.path.startswith('/v1/memory/'):
            user_id = unquote(parsed.path.removeprefix('/v1/memory/'))
            if user_id != subject:
                self._send(403, {'error': 'access to this user is not allowed'})
                return
            try:
                params = self._scope_query(parsed, {'memory_scope', 'before_id', 'limit'})
                scope = validate_memory_scope(params.get('memory_scope', DEFAULT_SCOPE))
                for field in ('before_id', 'limit'):
                    if field in params and re.fullmatch(r'[1-9][0-9]{0,18}', params[field]) is None:
                        raise ValueError(f'{field} must be a canonical positive integer')
                self._send(200, self.engine.memory_page(subject, memory_scope=scope,
                    before_id=int(params['before_id']) if 'before_id' in params else None,
                    limit=int(params['limit']) if 'limit' in params else 20))
            except ValueError as error:
                self._send(400, {'error': str(error)})
            return
        self._send(404, {'error': 'not found'})

    def do_DELETE(self) -> None:
        self._finish_read()
        parsed = urlparse(self.path)
        subject = self._authorize()
        if subject is None:
            return
        if parsed.path.startswith('/v1/memory-item/'):
            try:
                memory_id = self._memory_item_id(parsed)
                if self.headers.get_all('X-JACE-Confirm-Delete', []) != [str(memory_id)]:
                    self._send(409, {'error': 'explicit item deletion confirmation is required',
                                     'required_header': f'X-JACE-Confirm-Delete: {memory_id}'})
                    return
                audit_choices = self.headers.get_all('X-JACE-Confirm-Audit-Cleanup', [])
                if audit_choices and audit_choices != ['all-unattributed-for-owner']:
                    self._send(409, {'error': 'audit cleanup confirmation must be a single explicit choice',
                                     'required_header': 'X-JACE-Confirm-Audit-Cleanup: all-unattributed-for-owner'})
                    return
                revisions = self.headers.get_all('X-JACE-If-Memory-Revision', [])
                if len(revisions) > 1:
                    raise ValueError('exactly one expected memory revision is permitted')
                expected_revision = validate_memory_revision(revisions[0]) if revisions else None
                cleanup = bool(audit_choices)
                deleted = self.engine.forget_memory(subject, memory_id, confirm_delete=True,
                                                    confirm_unattributed_audit_cleanup=cleanup, expected_revision=expected_revision)
                self._send(200, {'deleted': deleted, 'memory_id': memory_id, 'user_id': subject})
            except MemoryConflictError as error:
                self._send(409, {'error': str(error)})
            except MemoryDeletionConsentRequired as error:
                self._send(409, {'error': str(error), 'unattributed_audit_entries': error.unattributed_audit_entries,
                                'required_header': 'X-JACE-Confirm-Audit-Cleanup: all-unattributed-for-owner'})
            except LookupError:
                self._send(404, {'error': 'memory not found'})
            except ValueError as error:
                self._send(400, {'error': str(error)})
            except Exception:
                self._send(500, {'error': 'internal server error'})
            return
        if parsed.path.startswith('/v1/memory/'):
            user_id = unquote(parsed.path.removeprefix('/v1/memory/'))
            if user_id != subject:
                self._send(403, {'error': 'access to this user is not allowed'})
                return
            self._send(200, {'deleted': self.engine.forget_user(subject), 'user_id': subject})
            return
        self._send(404, {'error': 'not found'})

    def do_PATCH(self) -> None:
        subject = self._authorize()
        if subject is None:
            return
        if self.path not in ('/v1/memory', '/v1/memory-expiration', '/v1/cleaning-profiles'):
            self._send(404, {'error': 'not found'})
            return
        try:
            body = self._body()
            if body.get('user_id', subject) != subject:
                self._send(403, {'error': 'access to this user is not allowed'})
                return
            if 'memory_scope' in body:
                raise ValueError('memory_scope cannot be changed by correction or expiration; create a separate memory explicitly')
            expected_revision = validate_memory_revision(body['expected_revision']) if 'expected_revision' in body else None
            if self.path == '/v1/cleaning-profiles':
                self._body_keys(body, {'user_id', 'memory_id', 'profile', 'expected_revision', 'confirm_save'})
                memory, notes = self.engine.update_cleaning_profile(subject, body.get('memory_id'), body.get('profile'),
                    expected_revision=expected_revision, confirm_save=body.get('confirm_save', False))
                self._send(200 if memory else 422, {'memory': memory.to_dict() if memory else None, 'notes': notes})
                return
            if self.path == '/v1/memory-expiration':
                self._body_keys(body, {'user_id', 'memory_id', 'expires_at', 'expected_revision'})
                if 'expires_at' not in body:
                    raise ValueError('expires_at is required; use null only to explicitly remove expiration')
                memory = self.engine.set_memory_expiration(subject, body.get('memory_id'), body['expires_at'], expected_revision=expected_revision)
                self._send(200, {'memory': memory.to_dict()})
                return
            self._body_keys(body, {'user_id', 'memory_id', 'content', 'expected_revision'})
            memory, notes = self.engine.correct_memory(subject, body.get('memory_id'), self._text(body, 'content'), expected_revision=expected_revision)
            self._send(200 if memory else 422, {'accepted': memory is not None, 'memory': memory.to_dict() if memory else None, 'notes': notes})
        except MemoryConflictError as error:
            self._send(409, {'error': str(error)})
        except LookupError:
            self._send(404, {'error': 'memory not found'})
        except (TimeoutError, ConnectionError, OSError):
            self.close_connection = True
        except ValueError as exc:
            self._send(400, {'error': str(exc)})
        except Exception:
            self._send(500, {'error': 'internal server error'})

    def do_POST(self) -> None:
        subject = self._authorize()
        if subject is None:
            return
        try:
            body = self._body()
            user_id = body.get('user_id', subject)
            if user_id != subject:
                self._send(403, {'error': 'access to this user is not allowed'})
                return
            if self.path == '/v1/cleaning-profiles':
                self._body_keys(body, {'user_id', 'profile', 'memory_scope', 'expires_at', 'confirm_save'})
                memory, notes = self.engine.save_cleaning_profile(subject, body.get('profile'),
                    confirm_save=body.get('confirm_save', False), memory_scope=body.get('memory_scope', DEFAULT_SCOPE),
                    expires_at=body.get('expires_at'))
                self._send(201 if memory else 422, {'memory': memory.to_dict() if memory else None, 'notes': notes})
                return
            if self.path == '/v1/plans/cleaning':
                self._body_keys(body, {'user_id', 'memory_scope', 'profile_memory_id', 'expected_profile_revision'})
                if 'expected_profile_revision' in body:
                    validate_memory_revision(body['expected_profile_revision'])
                if 'profile_memory_id' in body and body['profile_memory_id'] is None:
                    raise ValueError('profile_memory_id must be omitted or a positive integer, not null')
                self._send(200, self.engine.plan_cleaning(subject, memory_scope=body.get('memory_scope', DEFAULT_SCOPE),
                    profile_memory_id=body.get('profile_memory_id'), expected_profile_revision=body.get('expected_profile_revision')))
                return
            if self.path == '/v1/think':
                self._body_keys(body, {'user_id', 'input', 'learn', 'memory_scope'})
                if 'learn' in body and type(body['learn']) is not bool:
                    raise ValueError('learn must be a boolean')
                scope = validate_memory_scope(body.get('memory_scope', DEFAULT_SCOPE))
                result = self.engine.think(subject, self._text(body, 'input'), memory_scope=scope)
                payload = result.to_dict()
                if body.get('learn') is True:
                    learned, notes = self.engine.learn_from_conversation(subject, result.input, memory_scope=scope)
                    payload['learned_memory'] = learned.to_dict() if learned else None
                    payload['learning_notes'] = notes
                self._send(200, payload)
                return
            if self.path == '/v1/memory':
                self._body_keys(body, {'user_id', 'content', 'expires_at', 'memory_scope'})
                memory, notes = self.engine.remember(subject, self._text(body, 'content'), expires_at=body.get('expires_at'), memory_scope=body.get('memory_scope', DEFAULT_SCOPE))
                self._send(201 if memory else 422, {'accepted': memory is not None, 'memory': memory.to_dict() if memory else None, 'notes': notes})
                return
            if self.path == '/v1/simulate/motion':
                if not isinstance(body.get('observation'), dict):
                    raise ValueError('observation must be an object')
                self._send(200, {'decision': decide_motion(body['observation']).to_dict()})
                return
            self._send(404, {'error': 'not found'})
        except MemoryConflictError as exc:
            self._send(409, {'error': str(exc)})
        except LookupError:
            self._send(404, {'error': 'eligible profile not found'})
        except (TimeoutError, ConnectionError, OSError):
            self.close_connection = True
        except ValueError as exc:
            self._send(400, {'error': str(exc)})
        except Exception:
            self._send(500, {'error': 'internal server error'})

    def log_message(self, format: str, *args) -> None:
        return


def serve(host: str | None = None, port: int | None = None) -> None:
    authorization = ApiAuthorization.from_json(os.getenv('JACE_AUTH_TOKENS', ''))
    origins = {origin.strip() for origin in os.getenv('JACE_ALLOWED_ORIGINS', ','.join(sorted(DEFAULT_ORIGINS))).split(',') if origin.strip()}
    if '*' in origins:
        raise ValueError('Explicit allowed origins are required; wildcard origins are not supported')
    engine = CognitiveEngine()
    try:
        server = JaceHTTPServer((host or os.getenv('JACE_HOST', '127.0.0.1'), port if port is not None else int(os.getenv('JACE_PORT', '8787'))), engine, authorization, origins,
                                request_timeout=float(os.getenv('JACE_REQUEST_TIMEOUT_SECONDS', '10')),
                                max_connections=int(os.getenv('JACE_MAX_CONNECTIONS', '16')),
                                rate_per_minute=int(os.getenv('JACE_RATE_PER_MINUTE', '60')),
                                rate_burst=int(os.getenv('JACE_RATE_BURST', '30')),
                                rate_max_clients=int(os.getenv('JACE_RATE_MAX_CLIENTS', '1024')))
        try:
            print(f'JACE listening on http://{server.server_address[0]}:{server.server_address[1]}')
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    finally:
        engine.close()
