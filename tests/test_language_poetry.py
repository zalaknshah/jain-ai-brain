"""Original bounded poetry-routing fixtures, not a semantic language benchmark."""
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

from jace.engine import CognitiveEngine
from jace.ethics import assess
from jace.language_support import PLANS, TEXT, native_plan_key, response_language
from jace.practical import plan_for
from jace.reasoner import LocalReasoner


SUBJECTS = (
    ('hi', 'cleaning', 'घर की सफाई'),
    ('hi', 'wardrobe', 'अलमारी व्यवस्थित करना'),
    ('hi', 'dispute', 'व्यापार के साझेदार से मतभेद'),
    ('hi', 'dispute', 'कारोबार के भागीदार से अनबन'),
    ('gu', 'cleaning', 'ઘરની સફાઈ'),
    ('gu', 'cleaning', 'ઘરના રૂમની સફાઈ'),
    ('gu', 'wardrobe', 'કપડાંનું કબાટ ગોઠવવું'),
    ('gu', 'wardrobe', 'કપડાંને ગોઠવવા'),
    ('gu', 'dispute', 'વ્યવસાયના ભાગીદાર સાથે મતભેદ'),
    ('gu', 'dispute', 'વેપારમાં ભાગીદાર સાથે મતભેદ'),
)


class NativePoetryTests(unittest.TestCase):
    def test_reported_poem_request_gets_localized_abstention(self):
        query = 'कारोबार के भागीदार से अनबन के बारे में कविता लिखिए।'
        self.assertIsNone(native_plan_key(query))
        self.assertIsNone(plan_for(query))
        reply, action = LocalReasoner().respond(query, assess(query), [], [], [])
        self.assertTrue(reply.startswith(TEXT['hi']['fallback']))
        self.assertIn(TEXT['hi']['no_source'], reply)
        self.assertIsNone(action)

    def test_poetry_subjects_do_not_select_any_existing_native_plan(self):
        for language, _, subject in SUBJECTS:
            suffix = ' के बारे में कविता लिखिए।' if language == 'hi' else ' વિશે કવિતા લખો.'
            query = subject + suffix
            with self.subTest(query=query):
                self.assertIsNone(native_plan_key(query))
                self.assertIsNone(plan_for(query))
                reply, action = LocalReasoner().respond(query, assess(query), [], [], [])
                self.assertTrue(reply.startswith(TEXT[language]['fallback']))
                self.assertIsNone(action)

    def test_listed_whole_word_forms_normalize_and_ignore_display_joiners(self):
        for language, subject, words in (
            ('hi', 'घर की सफाई', ('कविता', 'कविताएँ', 'कविताएं', 'कविताओं', 'काव्य')),
            ('gu', 'ઘરની સફાઈ', ('કવિતા', 'કવિતાઓ', 'કાવ્ય')),
        ):
            for word in words + ('poem', 'poems', 'POETRY'):
                for value in (word, unicodedata.normalize('NFD', word), word[:1] + '\u200d' + word[1:]):
                    for query in (subject + ' ' + value, value + ' ' + subject):
                        with self.subTest(query=query):
                            self.assertEqual(response_language(query), language)
                            self.assertIsNone(plan_for(query))

    def test_ordinary_subjects_still_select_same_native_plans(self):
        for language, key, subject in SUBJECTS:
            with self.subTest(subject=subject):
                result = plan_for(subject)
                self.assertIsNotNone(result)
                self.assertEqual(result.language, language)
                self.assertEqual(result.name, PLANS[language][key][0])

    def test_incidental_poetry_mentions_are_deliberately_conservative(self):
        for query in (
            'कविता की किताब मेज पर है घर की सफाई कैसे करूँ?',
            'કવિતા લખેલી ચાદર સાથે કપડાંનું કબાટ ગોઠવવું છે.',
        ):
            with self.subTest(query=query):
                self.assertIsNone(plan_for(query))

    def test_no_substring_rule_or_new_english_only_route(self):
        # These are mechanical boundary fixtures, not natural-language quality
        # claims. A word containing a cue does not itself trigger this guard.
        for query, key in (
            ('घर की सफाई कवितामय', 'cleaning'),
            ('ઘરની સફાઈ કવિતાત્મક', 'cleaning'),
            ('घर की सफाई poemshelf', 'cleaning'),
        ):
            with self.subTest(query=query):
                self.assertEqual(native_plan_key(query), key)
        self.assertIsNone(native_plan_key('Write a poem about cleaning my house'))
        self.assertEqual(plan_for('How do I clean my house?').language, 'en')

    def test_engine_abstention_has_no_actions_learning_or_provider_calls(self):
        with tempfile.TemporaryDirectory() as directory, patch('jace.model_transport.BoundedModelOpener.open') as transport:
            engine = CognitiveEngine(db_path=Path(directory) / 'synthetic.db', canonical_path='', reasoner=LocalReasoner())
            try:
                for language, _, subject in SUBJECTS:
                    query = subject + (' कविता' if language == 'hi' else ' કવિતા')
                    with self.subTest(query=query):
                        result = engine.think('synthetic-poetry-user', query)
                        self.assertTrue(result.response.startswith(TEXT[language]['fallback']))
                        self.assertIsNone(result.action)
                self.assertEqual(engine.list_memories('synthetic-poetry-user'), [])
                transport.assert_not_called()
            finally:
                engine.close()


if __name__ == '__main__':
    unittest.main()
