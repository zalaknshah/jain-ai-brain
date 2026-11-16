import contextlib
import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from jace.canonical import CanonicalStore
from jace.models import CanonicalEntry
from jace.text import lexical_terms
from jace import cli


def entry(identifier, passage, **fields):
    values = dict(entry_id=identifier,title='neutral',principle=passage,guidance='neutral',source='fixture',tags=[])
    values.update(fields)
    return CanonicalEntry(**values)


def store(*entries):
    value = CanonicalStore.__new__(CanonicalStore)
    value._entries = tuple(entries)
    value.source_bound = False
    return value


class PassageSearchTests(unittest.TestCase):
    def test_filter_before_top_k_not_after(self):
        s = store(entry('a','unrelated',title='alpha beta gamma'), entry('z','alpha'))
        self.assertEqual(s.search('alpha beta gamma',1)[0].entry_id, 'a')
        self.assertEqual(s.search('alpha beta gamma',1,passages_only=True)[0].entry_id, 'z')

    def test_passage_only_score_excludes_metadata_terms(self):
        original = entry('a','alpha',title='beta gamma',tags=['alpha','beta'])
        hit = store(original).search_explained('alpha beta gamma',passages_only=True)[0]
        self.assertIs(hit.entry, original)
        self.assertEqual(hit.matched_terms, ('alpha',))
        self.assertEqual(hit.score, 1)
        self.assertEqual(hit.field_matches, (('principle',('alpha',)),))
        self.assertFalse(original.verified)

    def test_unicode_normalization_and_stable_tie_break(self):
        s = store(entry('z','करुणा કરુણા'),entry('a','Cafe\u0301 કરુણા'))
        self.assertEqual([e.entry_id for e in s.search('café करुणा કરુણા',passages_only=True)], ['a','z'])
        self.assertEqual(s.search('ru',passages_only=True), [])

    def test_default_rankings_match_prior_algorithm(self):
        entries = [entry(str(i), ['alpha','beta','करुणा','કરુણા'][i%4],
                         title=['gamma','alpha','delta'][i%3],tags=['tag'+str(i%3)]) for i in range(40)]
        s = store(*entries)
        for query in ('alpha','beta gamma','करुणा કરુણા','delta alpha beta','missing','','tag1'):
            terms = lexical_terms(query)
            rows=[]
            for e in entries:
                fields = list(filter(None,[e.title,e.principle,e.guidance,e.source,e.work,e.edition,e.location,*e.tags]))
                score=len(terms & lexical_terms(' '.join(fields)))
                if score: rows.append((score,e.entry_id,e))
            expected=[row[2] for row in sorted(rows,key=lambda row:(-row[0],row[1]))]
            for limit in (1,5,100):
                self.assertEqual(s.search(query,limit),expected[:limit])
                self.assertEqual(s.search(query,limit,passages_only=False),expected[:limit])

    def test_invalid_modes_queries_and_limits_still_rejected(self):
        s=store(entry('a','alpha'))
        for value in (None,1,'true',[]):
            with self.assertRaises(ValueError): s.search('',passages_only=value)
            with self.assertRaises(ValueError): s.search_explained('',passages_only=value)
        for query in (None,'x'*10001):
            with self.assertRaises(ValueError): s.search(query,passages_only=True)
        for limit in (True,0,101):
            with self.assertRaises(ValueError): s.search('',limit,passages_only=True)

    def test_full_record_budget_and_late_failures_remain(self):
        s=store(entry('a','alpha'),entry('z','other',title='x'*32769))
        with self.assertRaises(ValueError): s.search_explained('alpha',1,passages_only=True)
        s=store(entry('a','alpha'),entry('z','other'))
        with patch('jace.retrieval_limits.MAX_SCAN_ROWS',1):
            with self.assertRaises(ValueError): s.search_explained('alpha',1,passages_only=True)
        with patch('jace.retrieval_limits.MAX_SCAN_BYTES',1):
            with self.assertRaises(ValueError): s.search_explained('alpha',1,passages_only=True)

    def test_cli_mode_and_default_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.json'
            records=[]
            for e in (entry('a','unrelated',title='alpha beta'),entry('z','alpha')):
                record=e.to_dict()
                for k in ('source_sha256','source_byte_start','source_byte_end'): record.pop(k,None)
                record.update(work='Fixture',language='en',location='test',license='Synthetic',verified=True)
                records.append(record)
            path.write_text(json.dumps(records))
            for mode,expected in [(False,'a'),(True,'z')]:
                output=io.StringIO()
                args=['jace','explain-search','alpha beta','--limit','1','--corpus',str(path),'--allow-local-disclosure']
                if mode: args.append('--passages-only')
                with patch('sys.argv',args), contextlib.redirect_stdout(output), \
                     patch('jace.cli.CognitiveEngine',side_effect=AssertionError('no engine')):
                    cli.main()
                report=json.loads(output.getvalue())
                self.assertEqual(report['hits'][0]['entry_id'],expected)
                self.assertFalse(report['semantic_support_verified'])
                if mode: self.assertEqual(report['search_fields'],['principle'])
                else: self.assertNotIn('search_fields',report)

if __name__ == '__main__': unittest.main()
