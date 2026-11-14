import copy
import unittest
from audit import audit, sha

def fixture():
    text = 'Invented handbook: ask before moving a shared object. અહિંસા.'
    raw = text.encode()
    sources = {'s1': {'bytes': raw, 'sha256': sha(raw), 'work': 'Synthetic handbook',
        'edition': 'Original test edition', 'language': 'en', 'acquisition_reference': 'original fixture',
        'edition_rights_reference': 'synthetic declaration', 'edition_training_scope_reference': 'synthetic scope'}}
    row = {'id': 'one', 'source_id': 's1', 'source_sha256': sha(raw), 'start': 0, 'end': len(raw),
        'raw_excerpt': text, 'claim': 'Ask permission before moving shared objects.', 'target_language': 'en',
        'origin': 'original', 'rights_review_reference': 'fixture only',
        'scholarly_review_reference': 'fixture only', 'entailment_review_reference': 'fixture only'}
    return sources, row

class AuditTests(unittest.TestCase):
    def test_exact_never_admits(self):
        s,r=fixture(); out=audit(s,[r]); self.assertEqual(out['rows'][0]['alignment'],'exact_span_only')
        self.assertFalse(out['training_admitted']); self.assertFalse(out['rows'][0]['semantic_entailment_verified'])
    def test_unresolved(self):
        s,r=fixture(); r['source_id']='other'; self.assertIn('unresolved_source',audit(s,[r])['rows'][0]['structural_errors'])
    def test_locator_missing(self):
        s,r=fixture(); del r['start']; self.assertIn('invalid_byte_span',audit(s,[r])['rows'][0]['structural_errors'])
    def test_chunk_id_not_locator(self):
        s,r=fixture(); del r['start']; r['chunk_id']='123'; self.assertEqual(audit(s,[r])['rows'][0]['alignment'],'blocked')
    def test_digest(self):
        s,r=fixture(); s['s1']['bytes']+=b'x'; self.assertIn('source_digest_mismatch',audit(s,[r])['rows'][0]['structural_errors'])
    def test_excerpt(self):
        s,r=fixture(); r['raw_excerpt']='edited'; self.assertIn('raw_excerpt_mismatch',audit(s,[r])['rows'][0]['structural_errors'])
    def test_normalization_keeps_raw(self):
        s,r=fixture(); r['normalized_candidate']='corrected'; before=copy.deepcopy(r)
        self.assertIn('normalization_diff_requires_review',audit(s,[r])['rows'][0]['review_flags']); self.assertEqual(r,before)
    def test_utf8(self):
        s,r=fixture(); r['start']=len(s['s1']['bytes'])-3
        self.assertIn('invalid_utf8_boundary',audit(s,[r])['rows'][0]['structural_errors'])
    def test_bool_offsets(self):
        s,r=fixture(); r['start']=False; self.assertIn('invalid_byte_span',audit(s,[r])['rows'][0]['structural_errors'])
    def test_aggregate_license_no_override(self):
        s,r=fixture(); del s['s1']['edition_rights_reference']; r['dataset_license']='CC-BY'; r['extraction_confidence']=1.0
        self.assertIn('missing_edition_rights_reference',audit(s,[r])['rows'][0]['review_flags'])
    def test_translation_missing_review(self):
        s,r=fixture(); r['target_language']='gu'; r['origin']='machine_translation'
        self.assertIn('missing_translation_review_reference',audit(s,[r])['rows'][0]['review_flags'])
    def test_translation_origin(self):
        s,r=fixture(); r['target_language']='hi'; self.assertIn('translation_origin_not_preserved',audit(s,[r])['rows'][0]['structural_errors'])
    def test_duplicate(self):
        s,r=fixture()
        with self.assertRaises(ValueError): audit(s,[r,r])
    def test_no_text_output(self):
        s,r=fixture(); out=str(audit(s,[r])); self.assertNotIn(r['raw_excerpt'],out); self.assertNotIn(r['claim'],out)
    def test_false_claim_not_verified(self):
        s,r=fixture(); r['claim']='The handbook authorizes injuring people.'
        out=audit(s,[r])['rows'][0]; self.assertEqual(out['alignment'],'exact_span_only'); self.assertFalse(out['semantic_entailment_verified'])
    def test_oversize(self):
        s,r=fixture(); s['s1']['bytes']=b'a'*(1024*1024+1)
        self.assertIn('missing_or_oversized_source_bytes',audit(s,[r])['rows'][0]['structural_errors'])

if __name__=='__main__': unittest.main()
