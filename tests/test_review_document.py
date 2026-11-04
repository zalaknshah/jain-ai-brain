"""Synthetic-only renderer and DOM-script tests; no real browser is launched."""
import base64
import copy
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jace.review_document import MAX_HTML_BYTES, render_review_html


def fixture(passage='Synthetic first passage.\r\n\tWhitespace stays exact.\n'):
    second = 'Synthetic second passage; not a religious source.'
    raw = (passage + '\nGAP\n' + second).encode('utf-8')
    digest = hashlib.sha256(raw).hexdigest()
    entry = {'entry_id': '__proto__', 'title': 'Synthetic title', 'principle': passage,
             'guidance': 'A synthetic guidance declaration.', 'source': 'Synthetic source label',
             'tags': ['synthetic', 'test'], 'work': 'Synthetic work', 'language': 'en',
             'edition': None, 'location': 'Synthetic location', 'license': 'Synthetic fixture only',
             'verified': False, 'source_sha256': digest, 'source_byte_start': 0,
             'source_byte_end': len(passage.encode('utf-8'))}
    start = len((passage + '\nGAP\n').encode('utf-8'))
    other = {**entry, 'entry_id': 'toString', 'principle': second, 'edition': 'Synthetic edition',
             'source_byte_start': start, 'source_byte_end': len(raw)}
    return {'protocol': 1, 'kind': 'review_only', 'draft_revision': 'a' * 64,
            'sources': [{'sha256': digest, 'byte_length': len(raw)}],
            'records': [{'entry': entry, 'revision': 'b' * 64}, {'entry': other, 'revision': 'c' * 64}],
            'limits': ['Synthetic data. No independent review or rights verification.']}


class ReviewDocumentTests(unittest.TestCase):
    def assert_invalid(self, mutate):
        data = fixture()
        mutate(data)
        with self.assertRaises(ValueError):
            render_review_html(data)

    def test_safe_embedded_data_preserves_exact_source_and_unicode(self):
        payload = '</script><script>alert("synthetic")</script>&<img src=x onerror=alert(1)>\r\n\t\u2028\u2029 \U0001f31f'
        data = fixture(payload)
        data['records'][0]['entry']['title'] = payload
        data['limits'] = [payload]
        html = render_review_html(data).decode('utf-8')
        raw = re.search(r'<script id="review-snapshot" type="application/json">(.*?)</script>', html, re.S)[1]
        self.assertEqual(json.loads(raw), data)
        self.assertNotIn('<', raw)
        self.assertNotIn('>', raw)
        self.assertNotIn('&', raw)
        self.assertTrue(raw.isascii())
        self.assertEqual(html.count('</script>'), 2)
        self.assertNotIn(payload, html)
        self.assertIn('textContent', html)

    def test_csp_pins_assets_and_blocks_remote_activity(self):
        html = render_review_html(fixture()).decode('utf-8')
        scripts = re.findall(r'<script(?: [^>]*)?>(.*?)</script>', html, re.S)
        style = re.search(r'<style>(.*?)</style>', html, re.S)[1]
        for raw in (scripts[-1], style):
            digest = base64.b64encode(hashlib.sha256(raw.encode()).digest()).decode()
            self.assertIn("'sha256-" + digest + "'", html)
        for directive in ("default-src 'none'", "connect-src 'none'", "form-action 'none'", "base-uri 'none'", "object-src 'none'"):
            self.assertIn(directive, html)
        self.assertNotRegex(html, r'<(?:script|link|img|iframe|form)\b[^>]*(?:src|href|action)=')
        self.assertNotIn('unsafe-inline', html)
        self.assertNotRegex(scripts[-1], r'\b(?:fetch|XMLHttpRequest|WebSocket|localStorage|sessionStorage|indexedDB|eval|Function)\b')
        self.assertNotIn('innerHTML', scripts[-1])
        self.assertNotIn('document.write', scripts[-1])
        self.assertNotIn('sendBeacon', scripts[-1])

    def test_whole_file_warning_precedes_save_and_export_controls(self):
        html = render_review_html(fixture()).decode()
        warning = html.index('Whole original backing source FILES')
        self.assertLess(warning, html.index('id="save"'))
        self.assertLess(warning, html.index('Save a review report'))
        for required in ('unapproved text outside', 'File contents are not filtered', 'no rights grant',
                         '--declare-qualified-review', '--declare-rights-for-local-retrieval', '--confirm-export',
                         'Browser-managed download completion and file permissions', 'contains source passages'):
            self.assertIn(required, html)

    def test_invalid_snapshot_shapes_and_scalar_types(self):
        for value in (None, [], '', {}, {'protocol': 1}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                render_review_html(value)
        mutators = [lambda d: d.update(extra=True), lambda d: d.update(protocol=True),
                    lambda d: d.update(kind='runtime'), lambda d: d.update(draft_revision='a' * 63),
                    lambda d: d.update(records=[]), lambda d: d.update(sources=[]),
                    lambda d: d.update(limits=[]), lambda d: d.update(limits=['x'] * 33),
                    lambda d: d['records'][0].update(extra=True),
                    lambda d: d['records'][0].update(revision='G' * 64),
                    lambda d: d['records'][0]['entry'].update(extra='not allowed'),
                    lambda d: d['records'][0]['entry'].pop('edition'),
                    lambda d: d['records'][0]['entry'].update(verified=True),
                    lambda d: d['records'][0]['entry'].update(verified=0),
                    lambda d: d['sources'][0].update(byte_length=True),
                    lambda d: d['sources'][0].update(byte_length=1048577),
                    lambda d: d['records'][0]['entry'].update(source_byte_start=False),
                    lambda d: d['records'][0]['entry'].update(source_byte_end=1000000),
                    lambda d: d['records'][0]['entry'].update(source_byte_end=1),
                    lambda d: d['records'][0]['entry'].update(source_sha256='d' * 64)]
        for i, mutate in enumerate(mutators):
            with self.subTest(case=i): self.assert_invalid(mutate)

    def test_metadata_and_passage_bounds_fail_closed(self):
        entries = [('title', 'x' * 501), ('guidance', 'x' * 4001), ('entry_id', 'bad id'),
                   ('entry_id', 'bad[id]'), ('entry_id', ''), ('edition', ''), ('tags', ['x'] * 33),
                   ('tags', ['dup', 'dup']), ('tags', [None]), ('tags', ['x' * 65]),
                   ('principle', 'x' * 20001), ('principle', 'a\rb'), ('principle', 'a\x00b'),
                   ('principle', '\ud800'), ('title', '\u202eunsafe'), ('license', None)]
        for field, value in entries:
            with self.subTest(field=field, value=str(value)[:30]):
                self.assert_invalid(lambda d: d['records'][0]['entry'].update({field: value}))
        with self.assertRaises(ValueError): render_review_html(fixture('\U0001f31f' * 17000))

    def test_duplicates_and_count_limits(self):
        mutators = [lambda d: d['sources'].append(copy.deepcopy(d['sources'][0])),
                    lambda d: d['records'].append(copy.deepcopy(d['records'][0])),
                    lambda d: d.update(records=d['records'] * 129),
                    lambda d: d.update(sources=d['sources'] * 33),
                    lambda d: d['sources'].append({'sha256': 'd' * 64, 'byte_length': 1})]
        for i, mutate in enumerate(mutators):
            with self.subTest(case=i): self.assert_invalid(mutate)

    def test_strict_final_output_cap_includes_escaping_and_assets(self):
        data = fixture('<' * 20000)
        first = data['records'][0]
        data['records'] = [{**first, 'entry': {**first['entry'], 'entry_id': 'synthetic-' + str(i)}} for i in range(110)]
        # Input text is modest; required script-safe escaping expands beyond 12MiB.
        with self.assertRaisesRegex(ValueError, 'HTML exceeds'):
            render_review_html(data)
        with patch('jace.review_document.MAX_HTML_BYTES', 10):
            with self.assertRaisesRegex(ValueError, 'HTML exceeds'):
                render_review_html(fixture())
        self.assertLess(len(render_review_html(fixture())), MAX_HTML_BYTES)

    def test_metadata_total_limit(self):
        data = fixture()
        first = data['records'][0]
        first['entry'].update(guidance='g' * 4000, source='s' * 1000, work='w' * 1000,
                              location='l' * 1000, license='r' * 1000, edition='e' * 1000,
                              tags=[str(i) + 't' * 60 for i in range(32)])
        data['records'] = [{**first, 'entry': {**first['entry'], 'entry_id': 'synthetic-' + str(i)}} for i in range(256)]
        with self.assertRaisesRegex(ValueError, 'metadata exceeds'):
            render_review_html(data)


@unittest.skipUnless(shutil.which('node'), 'Node.js required for offline DOM-script fixtures')
class ReviewDocumentScriptTests(unittest.TestCase):
    def scenario(self, name, data=None):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'review.html'
            path.write_bytes(render_review_html(data or fixture()))
            result = subprocess.run(['node', str(Path(__file__).with_name('source_review_harness.js')), name, str(path)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_defaults_pending_and_navigation_in_memory(self): self.scenario('defaults_navigation')
    def test_required_reviewer_and_notes_with_text_bounds(self): self.scenario('required_fields')
    def test_invalid_decisions_fail_closed(self): self.scenario('invalid_decisions')
    def test_report_binding_no_sources_and_all_pending_allowed(self): self.scenario('report_binding')
    def test_edits_invalidate_confirmation_and_silent_edits_fail_closed(self): self.scenario('confirmation_binding')
    def test_consumption_no_retries_on_failures_or_repeated_clicks(self): self.scenario('download_failures')
    def test_page_lifecycle_and_clear_reset_private_state(self): self.scenario('lifecycle_clear')
    def test_malformed_embedded_snapshots_fail_closed(self): self.scenario('invalid_snapshots')
    def test_total_report_utf8_byte_cap_and_astral_boundaries(self):
        data = fixture()
        first = data['records'][0]
        data['records'] = [{**first, 'entry': {**first['entry'], 'entry_id': 'synthetic-report-' + str(i)}} for i in range(256)]
        self.scenario('report_byte_limit', data)
    def test_resume_valid_exact_report_without_save_consent(self): self.scenario('resume_roundtrip')
    def test_resume_reads_only_after_bound_explicit_load(self): self.scenario('resume_no_implicit_read')
    def test_resume_rejects_stale_malformed_duplicate_and_unknown_fields(self): self.scenario('resume_invalid_reports')
    def test_resume_size_bounds_read_failures_and_no_retry(self): self.scenario('resume_bounds_and_failures')
    def test_resume_stale_async_reads_cannot_replace_newer_work(self): self.scenario('resume_stale_async')

    def test_long_passage_exact_metadata_and_safe_literals(self):
        value = 'Synthetic </script><img src=x onerror=alert(1)>\r\n\t\u2028\u2029\U0001f31f' + 'x' * 19500
        data = fixture(value)
        data['records'][0]['entry']['title'] = '<svg onload=alert(1)>Synthetic title'
        data['records'][0]['entry']['guidance'] = '<script>synthetic</script>' + 'g' * 3900
        data['limits'] = ['<img src=x onerror=alert(1)>Literal limitation']
        self.scenario('literal_long_content', data)


if __name__ == '__main__':
    unittest.main()
