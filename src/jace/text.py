"""Unicode lexical matching only, without translation or semantic analysis."""
from __future__ import annotations

import unicodedata


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", unicodedata.normalize("NFC", text).casefold())


def lexical_terms(text: str) -> set[str]:
    """Keep letters and their combining marks together across writing systems.

    Python's ASCII ranges and ``\\w`` split Indic vowels from their letters.
    Zero-width joiners affect display, not this deliberately lexical index.
    Punctuation separates words; internal hyphens/underscores are preserved.
    """
    result: set[str] = set()
    current: list[str] = []

    def finish() -> None:
        token = "".join(current).strip("-_")
        if any(unicodedata.category(char).startswith("L") for char in token):
            result.add(token)
        current.clear()

    for char in normalize(text):
        category = unicodedata.category(char)
        if category[0] in {"L", "N"}:
            current.append(char)
        elif category[0] == "M" and current:
            current.append(char)
        elif char in {"\u200c", "\u200d"}:
            continue
        elif char in "-_" and current:
            current.append(char)
        else:
            finish()
    finish()
    return result
