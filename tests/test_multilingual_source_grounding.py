"""Original synthetic source records, not Jain scripture or model outputs."""
import copy
import json
import unicodedata
import unittest

from jace.source_answer_eval import evaluate_source_answers

# Parallel authored examples are only test inputs, not certified translations.
SOURCES = {
    'en': ('Do not proceed without permission.', 'What does the example say?', 'Wait for permission.'),
    'hi': ('बिना अनुमति आगे न बढ़ें।', 'इस उदाहरण में क्या कहा गया है?', 'अनुमति की प्रतीक्षा करें।'),
    'gu': ('મંજૂરી વિના આગળ ન વધો.', 'આ ઉદાહરણમાં શું કહ્યું છે?', 'મંજૂરીની રાહ જુઓ.'),
}


def fixture(language):
    passage, question, answer = SOURCES[language]
    source = {'entry_id': 'synthetic-' + language, 'title': 'Authored test example',
              'principle': passage, 'guidance': 'Synthetic fixture only.',
              'source': 'Original synthetic test', 'work': 'Not scripture',
              'language': language, 'location': 'test line 1', 'license': 'MIT', 'verified': True}
    case = {'id': language, 'question': question, 'require_citation': True, 'evidence': [source]}
    output = json.dumps({'answer': answer, 'citations': [{'entry_id': source['entry_id'], 'quote': passage}]}, ensure_ascii=False)
    return case, output


class MultilingualSourceGroundingTests(unittest.TestCase):
    def evaluate(self, case, output):
        return evaluate_source_answers([case], {case['id']: output})

    def test_all_source_answer_language_pairs_keep_original_quote(self):
        for source_language in SOURCES:
            case, output = fixture(source_language)
            for answer_language in SOURCES:
                payload = json.loads(output)
                payload['answer'] = SOURCES[answer_language][2]
                report = self.evaluate(case, json.dumps(payload, ensure_ascii=False))
                self.assertEqual(report['mechanically_accepted'], 1)
                self.assertEqual(report['citation_requirement_met'], 1)
                self.assertFalse(report['semantic_quality_verified'])
                self.assertFalse(report['runtime_admitted'])

    def test_translation_is_not_an_exact_quote(self):
        for source_language in SOURCES:
            case, output = fixture(source_language)
            for quote_language in SOURCES.keys() - {source_language}:
                payload = json.loads(output)
                payload['citations'][0]['quote'] = SOURCES[quote_language][0]
                self.assertEqual(self.evaluate(case, json.dumps(payload))['mechanically_accepted'], 0)

    def test_dropping_negation_from_full_quote_is_rejected(self):
        for language, needle in [('en', 'not '), ('hi', 'न '), ('gu', 'ન ')]:
            case, output = fixture(language)
            payload = json.loads(output)
            payload['citations'][0]['quote'] = SOURCES[language][0].replace(needle, '')
            self.assertEqual(self.evaluate(case, json.dumps(payload))['mechanically_accepted'], 0)

    def test_true_substring_does_not_establish_context_or_support(self):
        for language, fragment in [('en', 'proceed'), ('hi', 'आगे'), ('gu', 'આગળ')]:
            case, output = fixture(language)
            payload = json.loads(output)
            payload['answer'] = 'Proceed without permission. Synthetic contradiction.'
            payload['citations'][0]['quote'] = fragment
            report = self.evaluate(case, json.dumps(payload))
            self.assertEqual(report['mechanically_accepted'], 1)
            self.assertFalse(report['semantic_quality_verified'])
            self.assertEqual(report['review_count'], 0)

    def test_unicode_equivalence_does_not_rewrite_exact_source(self):
        case, output = fixture('hi')
        # Devanagari QA has a canonically decomposed form; do not normalize away
        # a literal source/output difference to award an exact-text match.
        source = '\u0958लम'
        changed = unicodedata.normalize('NFD', source)
        self.assertNotEqual(source, changed)
        case['evidence'][0]['principle'] = source
        payload = json.loads(output)
        payload['citations'][0]['quote'] = source
        self.assertEqual(self.evaluate(case, json.dumps(payload))['mechanically_accepted'], 1)
        payload['citations'][0]['quote'] = changed
        self.assertEqual(self.evaluate(case, json.dumps(payload))['mechanically_accepted'], 0)

    def test_review_binding_rejects_language_metadata_and_question_changes(self):
        for language in SOURCES:
            case, output = fixture(language)
            binding = self.evaluate(case, output)['cases'][0]['review_binding_sha256']
            review = {language: {'review_binding_sha256': binding, 'verdict': 'uncertain',
                                'reviewer': 'synthetic reviewer', 'rationale': 'Human review still needed.'}}
            for field in ('question', 'language', 'principle'):
                modified = copy.deepcopy(case)
                if field == 'question':
                    modified[field] += ' Changed.'
                else:
                    modified['evidence'][0][field] += ' Changed.'
                with self.assertRaises(ValueError):
                    evaluate_source_answers([modified], {language: output}, review)

    def test_missing_language_output_is_not_dropped_from_denominator(self):
        cases, outputs = [], {}
        for language in SOURCES:
            case, output = fixture(language)
            cases.append(case)
            if language != 'gu':
                outputs[language] = output
        report = evaluate_source_answers(cases, outputs)
        self.assertEqual((report['case_count'], report['output_count'], report['unreviewed_count']), (3, 2, 3))
        self.assertEqual(report['cases'][2]['mechanical'], 'missing')

    def test_summaries_do_not_emit_native_source_or_question_text(self):
        for language in SOURCES:
            case, output = fixture(language)
            summary = json.dumps(self.evaluate(case, output), ensure_ascii=False)
            for value in SOURCES[language]:
                self.assertNotIn(value, summary)


if __name__ == '__main__':
    unittest.main()
