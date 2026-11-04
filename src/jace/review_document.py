"""Render a bounded, self-contained review-only document, never a runtime corpus.

The caller supplies a snapshot of already checked local source bytes. This layer
validates its shape and bounds but cannot authenticate the original files, rights,
reviewer qualifications, or the meaning of a passage. All source content is data.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.resources
import json
import re

MAX_HTML_BYTES = 12 * 1024 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_SOURCES = 32
MAX_RECORDS = 256
MAX_SOURCE_BYTES = 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 8 * 1024 * 1024
MAX_PASSAGE_CHARS = 20000
MAX_PASSAGE_BYTES = 65536
_DIGEST = re.compile(r'[0-9a-f]{64}\Z')
_CONTROLS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]')
_TEXT_LIMITS = {'entry_id': 128, 'title': 500, 'guidance': 4000, 'source': 1000,
                'work': 1000, 'language': 64, 'location': 1000, 'license': 1000}
_ENTRY_FIELDS = frozenset(_TEXT_LIMITS) | {'principle', 'edition', 'tags', 'verified',
                                         'source_sha256', 'source_byte_start', 'source_byte_end'}


def _object(value, fields: set | frozenset) -> None:
    if type(value) is not dict or value.keys() != fields:
        raise ValueError('invalid review snapshot fields')


def _text(value, maximum: int) -> str:
    if (type(value) is not str or not value.strip() or len(value) > maximum
            or _CONTROLS.search(value) or '\r' in value.replace('\r\n', '')):
        raise ValueError('invalid review snapshot text')
    try:
        value.encode('utf-8', errors='strict')
    except UnicodeError as error:
        raise ValueError('invalid review snapshot Unicode') from error
    return value


def _digest(value) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ValueError('invalid review snapshot digest')
    return value


def _validate_snapshot(snapshot) -> None:
    _object(snapshot, {'protocol', 'kind', 'draft_revision', 'sources', 'records', 'limits'})
    if type(snapshot['protocol']) is not int or snapshot['protocol'] != 1 or snapshot['kind'] != 'review_only':
        raise ValueError('invalid review snapshot protocol')
    _digest(snapshot['draft_revision'])
    sources, records, limits = snapshot['sources'], snapshot['records'], snapshot['limits']
    if type(sources) is not list or not 1 <= len(sources) <= MAX_SOURCES:
        raise ValueError('invalid review source count')
    if type(records) is not list or not 1 <= len(records) <= MAX_RECORDS:
        raise ValueError('invalid review record count')
    if type(limits) is not list or not 1 <= len(limits) <= 32:
        raise ValueError('invalid review limitations')
    for limitation in limits:
        _text(limitation, 4000)
    declared = {}
    for source in sources:
        _object(source, {'sha256', 'byte_length'})
        digest, size = _digest(source['sha256']), source['byte_length']
        if digest in declared or type(size) is not int or not 1 <= size <= MAX_SOURCE_BYTES:
            raise ValueError('invalid review source declaration')
        declared[digest] = size
    if sum(declared.values()) > MAX_TOTAL_SOURCE_BYTES:
        raise ValueError('review source total exceeds limit')
    seen, referenced, metadata = set(), set(), []
    for record in records:
        _object(record, {'entry', 'revision'})
        _digest(record['revision'])
        entry = record['entry']
        _object(entry, _ENTRY_FIELDS)
        for field, maximum in _TEXT_LIMITS.items():
            _text(entry[field], maximum)
        if any(c.isspace() or c in '[]' for c in entry['entry_id']) or entry['entry_id'] in seen:
            raise ValueError('invalid or duplicate review entry ID')
        seen.add(entry['entry_id'])
        if entry['verified'] is not False:
            raise ValueError('review snapshot must be unverified')
        if entry['edition'] is not None:
            _text(entry['edition'], 1000)
        tags = entry['tags']
        if type(tags) is not list or len(tags) > 32:
            raise ValueError('invalid review tags')
        for tag in tags:
            _text(tag, 64)
        if len(set(tags)) != len(tags):
            raise ValueError('duplicate review tags')
        passage = _text(entry['principle'], MAX_PASSAGE_CHARS)
        digest = _digest(entry['source_sha256'])
        start, end = entry['source_byte_start'], entry['source_byte_end']
        if (digest not in declared or type(start) is not int or type(end) is not int
                or not 0 <= start < end <= declared[digest]
                or end - start > MAX_PASSAGE_BYTES
                or len(passage.encode('utf-8')) != end - start):
            raise ValueError('invalid review passage byte span')
        referenced.add(digest)
        metadata.append({key: value for key, value in entry.items() if key != 'principle'})
    if referenced != set(declared):
        raise ValueError('unreferenced review source')
    if len(json.dumps(metadata, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) > MAX_METADATA_BYTES:
        raise ValueError('review metadata exceeds limit')


_STYLE = '''
:root { color-scheme: light dark; font-family: system-ui, sans-serif; line-height: 1.5; }
body { margin: 0 auto; max-width: 72rem; padding: 1.25rem; }
h1, h2, h3 { line-height: 1.2; }
.warning { border: .25rem solid #b25400; padding: 1rem; background: #fff0d5; color: #291900; }
.warning strong { font-size: 1.15rem; }
section { margin-block: 1.5rem; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; padding: 1rem; border: 1px solid #888; tab-size: 4; }
#passage { font: 1.05rem/1.7 ui-monospace, monospace; }
label { display: block; margin-block: .75rem; }
input[type="text"], textarea { box-sizing: border-box; width: 100%; max-width: 55rem; font: inherit; }
textarea { min-height: 8rem; }
button, select { font: inherit; padding: .5rem .75rem; margin: .25rem .5rem .25rem 0; }
button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible { outline: 3px solid #2874dc; outline-offset: 3px; }
#status { min-height: 1.5rem; font-weight: 600; }
code { overflow-wrap: anywhere; }
'''.strip()

_BODY = '''
<h1>JACE private source review</h1>
<aside class="warning" aria-label="Whole-source file warning">
<strong>Whole original backing source FILES are copied in a future runtime export.</strong>
<p>Only approved RECORDS are included, but each approved record brings its WHOLE original backing source FILE.
That file may contain unapproved text outside the selected spans. File contents are not filtered.</p>
<p>This process does not independently verify rights, authenticity, reviewer qualifications, or the meaning of a passage.
It does not authorize sharing or training and creates no rights grant.</p>
</aside>
<p>This is a private, review-only document, not a runtime corpus. All entries start pending and unverified.
An approval is your explicit record decision, not an independent scholarly, legal, or licensing certification.</p>
<p>Everything here runs offline. No network requests, browser storage, model calls, uploads, or automatic downloads are used.
Reviewer details and decisions exist only in memory until you explicitly save a report. Keep this document private: it contains source passages.</p>
<noscript>JavaScript is required for the local review controls. No review decisions can be saved while it is disabled.</noscript>
<p id="status" role="status" aria-live="polite">Checking the review document. Controls remain unavailable if validation fails.</p>
<main id="review" hidden>
<section aria-label="Draft identity and source files">
<h2>Draft identity</h2><pre id="draft-metadata"></pre>
<h3>Backing source files (digest and original byte length)</h3><pre id="sources"></pre>
<h3>Limits and declarations</h3><ul id="limits"></ul>
</section>
<section aria-label="Current passage">
<h2 id="record-heading">Passage review</h2><p id="progress" aria-live="polite"></p>
<div><button id="previous" type="button">Previous passage</button><button id="next" type="button">Next passage</button></div>
<h3>Exact passage</h3><p>Full text below, with source whitespace preserved. Source byte ranges are UTF-8, zero-based and end-exclusive.</p>
<pre id="passage" dir="auto"></pre>
<h3>Complete entry metadata</h3><p>Exact JSON values for every entry field except the passage shown above. All declarations remain unverified.</p>
<pre id="metadata"></pre><pre id="record-revision"></pre>
<label for="decision">Your decision for this passage</label>
<select id="decision"><option value="pending" selected>Pending</option><option value="approve">Approve</option><option value="reject">Reject</option></select>
<label for="note">Review note (at most 2,000 characters; a nonblank note is required for approve or reject)</label>
<textarea id="note" autocomplete="off" spellcheck="false"></textarea>
</section>
<section aria-label="Save decisions">
<h2>Save a review report</h2>
<p>The report contains every record ID and revision, your name, decisions, and notes. It contains no source passages unless you put them in a note.
Names and notes may be private. A save requests a JSON download on this device, not a runtime corpus or an activation.
Browser-managed download completion and file permissions are not guaranteed by this page.
An all-pending report is allowed. Runtime export separately requires at least one approval.
The complete report must fit within 2 MiB of UTF-8 JSON, including metadata and formatting. Shorten notes if it exceeds this limit; some Unicode characters use multiple bytes.</p>
<label for="reviewer">Reviewer name (required, 1–128 characters; not a qualification claim)</label>
<input id="reviewer" type="text" autocomplete="off" spellcheck="false">
<label><input id="confirm-save" type="checkbox"> I explicitly confirm saving this current review report on this device, including my name and notes.</label>
<button id="save" type="button" disabled>Save review report</button>
<button id="clear" type="button">Clear reviewer, notes and all decisions</button>
<p>Confirmation starts unchecked, is invalidated by any edit and is consumed before one download attempt.
If saving fails, confirm again yourself; there is no automatic retry. Leaving or restoring this page clears unsaved reviewer details and decisions.</p>
<h3>Separate runtime export</h3>
<p>After independently checking reviewer qualifications and rights for local retrieval, a separate CLI command can export approved records and their WHOLE backing source FILES.
The command requires explicit qualified-review and rights-for-local-retrieval declarations and <code>--confirm-export</code>.
Consult <code>python scripts/review_sources.py export --help</code> for the exact arguments. Nothing here runs commands, activates a corpus, uploads files, or authorizes sharing or training.</p>
<pre>python scripts/review_sources.py export --manifest DRAFT/bundle.json --decisions REPORT.json --output NEW_DIR --declare-qualified-review --declare-rights-for-local-retrieval --confirm-export</pre>
</section>
</main>
'''.strip()


def _csp_hash(value: str) -> str:
    return base64.b64encode(hashlib.sha256(value.encode('utf-8')).digest()).decode('ascii')


def render_review_html(snapshot: dict) -> bytes:
    """Return offline HTML bytes after fail-closed validation and a 12 MiB cap.

    The file embeds the exact passage as JSON data, then displays it using
    textContent. Escaping HTML metacharacters and all non-ASCII code points stops
    script termination, HTML parsing and Unicode line separators from crossing
    the data boundary. The fixed executable script and style are CSP hash-pinned.
    """
    _validate_snapshot(snapshot)
    payload = json.dumps(snapshot, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
    payload = payload.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    script = importlib.resources.files('jace').joinpath('data/source_review.js').read_text(encoding='utf-8')
    if '</script' in script.lower():
        raise ValueError('unsafe review script asset')
    csp = ("default-src 'none'; connect-src 'none'; img-src 'none'; object-src 'none'; "
           "base-uri 'none'; form-action 'none'; "
           f"script-src 'sha256-{_csp_hash(script)}'; style-src 'sha256-{_csp_hash(_STYLE)}'")
    html = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta http-equiv="Content-Security-Policy" content="{csp}">'
            '<meta name="referrer" content="no-referrer">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>JACE private source review</title>'
            f'<style>{_STYLE}</style></head><body>{_BODY}'
            f'<script id="review-snapshot" type="application/json">{payload}</script>'
            f'<script>{script}</script></body></html>')
    result = html.encode('utf-8')
    if len(result) > MAX_HTML_BYTES:
        raise ValueError('review HTML exceeds its byte limit')
    return result
