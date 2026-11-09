"""Source-free preview of explicitly declared Sanskrit-script query fragments.

This is orthographic transliteration, not translation, language detection,
Sanskrit validation, source retrieval, canonical admission or model inference.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata

MAX_INPUT_BYTES = 4096
MAX_TEXT_CHARACTERS = 1024
MAX_QUERY_CHARACTERS = 512
NOTICE = (
    'Orthographic Sanskrit transliteration only, not Hindi/Gujarati translation or language verification. '
    'No source was opened and no search was run. Review the Latin query before separately invoking '
    'source-study with its existing source, records, purpose and licence opt-ins. '
    'Source-study still requires at least two query terms and sufficient source overlap, and can abstain.'
)

# Classical Sanskrit orthography only. Gujarati letters have matching Unicode
# block offsets for this explicit subset. Unsupported letters are not guessed.
_VOWELS = {
    'अ': 'a', 'आ': 'ā', 'इ': 'i', 'ई': 'ī', 'उ': 'u', 'ऊ': 'ū',
    'ऋ': 'ṛ', 'ॠ': 'ṝ', 'ऌ': 'ḷ', 'ॡ': 'ḹ', 'ए': 'e', 'ऐ': 'ai', 'ओ': 'o', 'औ': 'au',
}
_SIGNS = {
    'ा': 'ā', 'ि': 'i', 'ी': 'ī', 'ु': 'u', 'ू': 'ū', 'ृ': 'ṛ', 'ॄ': 'ṝ',
    'ॢ': 'ḷ', 'ॣ': 'ḹ', 'े': 'e', 'ै': 'ai', 'ो': 'o', 'ौ': 'au',
}
_CONSONANTS = dict(zip(
    'कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसह',
    ('k','kh','g','gh','ṅ','c','ch','j','jh','ñ','ṭ','ṭh','ḍ','ḍh','ṇ',
     't','th','d','dh','n','p','ph','b','bh','m','y','r','l','v','ś','ṣ','s','h'),
))
_MARKS = {'ं': 'ṃ', 'ः': 'ḥ'}
_ALLOWED_LANGUAGES = {'sa-Deva': 0, 'sa-Gujr': 0x180}


class QueryPreparationError(ValueError):
    """Unsupported or structurally incomplete input; no partial query is emitted."""


def transliterate_sanskrit(text: str, input_language: str) -> str:
    """Transliterate a small explicit orthographic subset, preserving word breaks.

    Final inherent vowels remain: this does not apply Hindi/Gujarati schwa
    deletion, sandhi analysis, spelling correction or word interpretation.
    """
    if not isinstance(input_language, str) or input_language not in _ALLOWED_LANGUAGES:
        raise QueryPreparationError('Declare Sanskrit as sa-Deva or sa-Gujr; Hindi/Gujarati translation is unavailable')
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARACTERS:
        raise QueryPreparationError('Provide 1 to 1024 characters of Sanskrit-script text')
    text = unicodedata.normalize('NFC', text)
    offset = _ALLOWED_LANGUAGES[input_language]
    vowels = {chr(ord(c) + offset): value for c, value in _VOWELS.items()}
    signs = {chr(ord(c) + offset): value for c, value in _SIGNS.items()}
    consonants = {chr(ord(c) + offset): value for c, value in _CONSONANTS.items()}
    marks = {chr(ord(c) + offset): value for c, value in _MARKS.items()}
    virama, avagraha = chr(ord('्') + offset), chr(ord('ऽ') + offset)
    output = []
    pending_vowel = False
    syllable = False
    mark_used = False
    after_virama = after_avagraha = False
    for char in text:
        boundary = char in ' \t\r\n\u00a0।॥'
        if after_virama and char not in consonants and not boundary:
            raise QueryPreparationError('A virama must end a word or be followed by a consonant')
        if after_avagraha and char not in consonants and char not in vowels:
            raise QueryPreparationError('Avagraha must be followed by Sanskrit letters')
        after_virama = after_avagraha = False
        if char in consonants:
            output.extend((consonants[char], 'a'))
            pending_vowel, syllable, mark_used = True, True, False
        elif char in vowels:
            output.append(vowels[char])
            pending_vowel, syllable, mark_used = False, True, False
        elif char in signs:
            if not pending_vowel:
                raise QueryPreparationError('A vowel sign must immediately follow an unmodified consonant')
            output[-1] = signs[char]
            pending_vowel, syllable, mark_used = False, True, False
        elif char == virama:
            if not pending_vowel:
                raise QueryPreparationError('A virama must immediately follow an unmodified consonant')
            output.pop()
            pending_vowel, syllable, mark_used = False, False, False
            after_virama = True
        elif char in marks:
            if not syllable or mark_used:
                raise QueryPreparationError('Anusvara or visarga requires one preceding syllable')
            output.append(marks[char])
            pending_vowel, mark_used = False, True
        elif char == avagraha:
            if not syllable:
                raise QueryPreparationError('Avagraha requires a preceding syllable')
            output.append("'")
            after_avagraha = True
            pending_vowel, syllable, mark_used = False, False, False
        elif char in ' \t\r\n\u00a0' or char in '।॥':
            # Danda is shared across Indic scripts. It denotes a boundary, not
            # text to invent or join; repeated boundaries collapse below.
            output.append(' ')
            pending_vowel, syllable, mark_used = False, False, False
        else:
            raise QueryPreparationError('Unsupported character for the declared Sanskrit script')
    if after_avagraha:
        raise QueryPreparationError('Avagraha must be followed by Sanskrit letters')
    result = re.sub(r' +', ' ', ''.join(output)).strip()
    if not result or not any(c.isalpha() for c in result):
        raise QueryPreparationError('No supported Sanskrit letters were provided')
    return unicodedata.normalize('NFC', result)


def prepare_query(request: dict) -> dict:
    if not isinstance(request, dict) or set(request) != {'input_language', 'text'}:
        raise QueryPreparationError('Expected exactly input_language and text')
    language = request['input_language']
    if not isinstance(language, str):
        raise QueryPreparationError('input_language must be a string')
    query = transliterate_sanskrit(request['text'], language)
    if len(query) > MAX_QUERY_CHARACTERS:
        raise QueryPreparationError('The prepared query exceeds the unchanged 512-character source-study limit')
    # This enclosing preview intentionally cannot be passed directly to the
    # strict source-study API. The operator must review and select the request.
    return {
        'status': 'preview_only',
        'input_language': language,
        'original_text': request['text'],
        'suggested_request': {'operation': 'search', 'query': query, 'query_language': 'sa-Latn'},
        'notice': NOTICE,
        'source_opened': False,
        'search_performed': False,
    }


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise QueryPreparationError('Duplicate JSON keys are unsupported')
        result[key] = value
    return result


def main() -> None:
    parser = argparse.ArgumentParser(prog='jace-prepare-study-query', description=__doc__)
    parser.add_argument('--stdin', action='store_true', required=True, help='read bounded JSON from stdin; input/output may be retained by your terminal')
    parser.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise QueryPreparationError('JSON input exceeds 4096 bytes')
        request = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                             parse_constant=lambda value: (_ for _ in ()).throw(QueryPreparationError('Non-finite JSON is unsupported')))
        result = prepare_query(request)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        # Do not echo input or emit a partially prepared query on failure.
        print(json.dumps({'status': 'rejected', 'error': 'Unsupported request; provide bounded Sanskrit-script text and sa-Deva or sa-Gujr. No query was prepared.'}))
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
