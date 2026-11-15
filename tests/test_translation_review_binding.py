"""Synthetic translation-review challenges, not translations of Jain literature."""
import copy
import json
import unittest
from jace.source_answer_eval import evaluate_source_answers


class TranslationReviewBindingTests(unittest.TestCase):
    def fixture(self, language):
        # These authored strings exercise text handling, not scholarly correctness.
        answers = {'gu': 'મંજૂરીની રાહ જુઓ.', 'hi': 'अनुमति की प्रतीक्षा करें।',
                   'en': 'Wait for permission.'}
        case = {'id': 'synthetic', 'question': 'Explain this invented instruction.',
                'require_citation': True, 'evidence': [{
                    'entry_id': 'original', 'title': 'Synthetic source',
                    'principle': 'Do not proceed without permission.',
                    'guidance': 'Authored test only.', 'source': 'Original fixture',
                    'work': 'Not scripture', 'language': 'en', 'verified': True}]}
        output = json.dumps({'answer': answers[language], 'citations': [{
            'entry_id': 'original', 'quote': case['evidence'][0]['principle']}]}, ensure_ascii=False)
        binding = evaluate_source_answers([case], {'synthetic': output})['cases'][0]['review_binding_sha256']
        review = {'synthetic': {'review_binding_sha256': binding, 'verdict': 'supported',
                               'reviewer': 'synthetic label', 'rationale': 'Test assertion only.'}}
        return case, output, review

    def test_review_cannot_be_reused_after_any_translation_change(self):
        for language in ('gu', 'hi', 'en'):
            case, output, review = self.fixture(language)
            payload = json.loads(output)
            payload['answer'] += ' Changed.'
            with self.assertRaises(ValueError):
                evaluate_source_answers([case], {'synthetic': json.dumps(payload)}, review)

    def test_supported_annotation_never_grants_runtime_or_semantic_authority(self):
        for language in ('gu', 'hi', 'en'):
            case, output, review = self.fixture(language)
            report = evaluate_source_answers([case], {'synthetic': output}, review)
            self.assertEqual(report['human_verdict_counts']['supported'], 1)
            self.assertTrue(report['complete_review_coverage'])
            self.assertFalse(report['semantic_quality_verified'])
            self.assertFalse(report['runtime_admitted'])

    def test_source_metadata_changes_invalidate_translation_review(self):
        for field in ('source', 'work', 'language', 'verified'):
            case, output, review = self.fixture('gu')
            changed = copy.deepcopy(case)
            changed['evidence'][0][field] = False if field == 'verified' else 'Changed'
            with self.assertRaises(ValueError):
                evaluate_source_answers([changed], {'synthetic': output}, review)

    def test_review_summary_does_not_repeat_translation_or_review_identity(self):
        for language in ('gu', 'hi', 'en'):
            case, output, review = self.fixture(language)
            report = json.dumps(evaluate_source_answers([case], {'synthetic': output}, review), ensure_ascii=False)
            for text in (json.loads(output)['answer'], case['evidence'][0]['principle'],
                         review['synthetic']['reviewer'], review['synthetic']['rationale']):
                self.assertNotIn(text, report)


if __name__ == '__main__':
    unittest.main()
