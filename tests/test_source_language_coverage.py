"""Original synthetic inputs only, no Jain literature or model outputs."""
import copy
import json
import unittest
from jace.source_language_coverage import evaluate_source_language_coverage


def fixture(language, ident='case'):
    case = {'id': ident, 'question': 'Explain this synthetic source.', 'require_citation': True,
            'evidence': [{'entry_id': 'source', 'title': 'Synthetic', 'principle': 'Wait.',
                          'guidance': 'Invented fixture.', 'source': 'Original test',
                          'language': language, 'verified': True}]}
    output = json.dumps({'answer': 'Wait.', 'citations': [{'entry_id': 'source', 'quote': 'Wait.'}]})
    return case, output


class LanguageCoverageTests(unittest.TestCase):
    def test_missing_gujarati_is_visible_not_removed(self):
        cases, outputs = [], {}
        for language in ('gu', 'hi', 'en'):
            case, output = fixture(language, language)
            cases.append(case)
            if language != 'gu': outputs[language] = output
        result = evaluate_source_language_coverage(cases, outputs)
        self.assertEqual(result['case_count'], 3)
        self.assertEqual(result['source_language_groups']['gu']['case_count'], 1)
        self.assertEqual(result['source_language_groups']['gu']['output_count'], 0)
        self.assertFalse(result['translation_quality_verified'])
        self.assertFalse(result['runtime_admitted'])

    def test_prakrit_script_declarations_aggregate_without_detection_claim(self):
        cases = [fixture(language, str(index))[0] for index, language in enumerate(('pra','pra-Deva','pra-Latn'))]
        result = evaluate_source_language_coverage(cases, {})
        self.assertEqual(result['source_language_groups']['pra']['case_count'], 3)
        self.assertFalse(result['source_languages_verified'])

    def test_mixed_unknown_and_empty_sources_have_separate_buckets(self):
        mixed, _ = fixture('gu', 'mixed')
        extra = copy.deepcopy(mixed['evidence'][0]); extra['entry_id'] = 'second'; extra['language'] = 'hi'
        mixed['evidence'].append(extra)
        other, _ = fixture('private-language-marker', 'other')
        none, _ = fixture('en', 'none'); none['evidence'] = []
        result = evaluate_source_language_coverage([mixed, other, none], {})
        for name in ('mixed','other','none'):
            self.assertEqual(result['source_language_groups'][name]['case_count'], 1)
        self.assertNotIn('private-language-marker', json.dumps(result))

    def test_invalid_and_stale_inputs_are_not_aggregated(self):
        case, output = fixture('hi')
        with self.assertRaises(ValueError):
            evaluate_source_language_coverage([case], {'unknown': output})
        with self.assertRaises(ValueError):
            evaluate_source_language_coverage([case], {'case': output}, {'case': {
                'review_binding_sha256': '0'*64, 'verdict': 'supported',
                'reviewer': 'test', 'rationale': 'test'}})

    def test_mixed_prakrit_scripts_share_language_bucket(self):
        case, _ = fixture('pra-Deva')
        extra = copy.deepcopy(case['evidence'][0])
        extra['entry_id'] = 'second'
        extra['language'] = 'pra-Latn'
        case['evidence'].append(extra)
        result = evaluate_source_language_coverage([case], {})
        self.assertEqual(result['source_language_groups']['pra']['case_count'], 1)
        self.assertEqual(result['source_language_groups']['mixed']['case_count'], 0)

    def test_omitted_language_is_not_claimed_as_declared_english(self):
        case, output = fixture('en')
        del case['evidence'][0]['language']
        result = evaluate_source_language_coverage([case], {'case': output})
        self.assertEqual(result['source_language_groups']['undeclared']['case_count'], 1)
        self.assertEqual(result['source_language_groups']['en']['case_count'], 0)

    def test_rejected_output_is_counted_but_not_accepted(self):
        case, _ = fixture('en')
        group = evaluate_source_language_coverage([case], {'case': 'invalid'})['source_language_groups']['en']
        self.assertEqual((group['output_count'],group['mechanically_accepted'],group['review_count']), (1,0,0))


if __name__ == '__main__': unittest.main()
