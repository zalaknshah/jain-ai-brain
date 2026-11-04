"""Explicit per-user HTTP authorization without creating or saving credentials."""
from __future__ import annotations

import hmac
import json
from collections.abc import Mapping


class ApiAuthorization:
    def __init__(self, tokens: Mapping[str, str] | None = None) -> None:
        self._tokens = dict(tokens or {})
        for token, user_id in self._tokens.items():
            if (not isinstance(token, str) or len(token) < 32 or not token.isascii()
                    or any(char.isspace() for char in token)
                    or not isinstance(user_id, str) or not user_id.strip()
                    or user_id != user_id.strip() or len(user_id) > 128):
                raise ValueError('Invalid API authorization configuration')

    @classmethod
    def from_json(cls, value: str) -> ApiAuthorization:
        if not value.strip():
            return cls()
        def unique_tokens(pairs):
            tokens = {}
            for token, user_id in pairs:
                if token in tokens:
                    raise ValueError('duplicate token mapping')
                tokens[token] = user_id
            return tokens
        try:
            tokens = json.loads(value, object_pairs_hook=unique_tokens)
            if not isinstance(tokens, dict):
                raise ValueError
            return cls(tokens)
        except (ValueError, TypeError):
            # Never include configuration contents in errors or logs.
            raise ValueError('Invalid API authorization configuration') from None

    @property
    def enabled(self) -> bool:
        return bool(self._tokens)

    def authenticate(self, header: str) -> str | None:
        scheme, separator, provided = header.partition(' ')
        if not separator or scheme.lower() != 'bearer' or not provided.isascii():
            return None
        subject = None
        for token, user_id in self._tokens.items():
            if hmac.compare_digest(token, provided):
                subject = user_id
        return subject
