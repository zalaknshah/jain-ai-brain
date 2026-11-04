"""Explicit recall namespaces; ownership remains the authorization boundary."""
import re

DEFAULT_SCOPE = 'default'


def validate_memory_scope(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', value, re.ASCII):
        raise ValueError('memory_scope must be 1-64 lowercase ASCII letters/digits, with optional underscores or hyphens after the first character')
    return value
