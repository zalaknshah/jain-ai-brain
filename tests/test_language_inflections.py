"""Bounded whole-word aliases; original application fixtures, no source corpus."""
import unicodedata
import unittest

from jace.ethics import assess
from jace.language_support import PLANS, TEXT
from jace.practical import plan_for
from jace.reasoner import LocalReasoner


CASES = [
    ('gu', 'cleaning', 'ઘરના રૂમની સફાઈ માટે યોજના આપો.'),
    ('gu', 'wardrobe', 'મારા કપડાંને ગોઠવવા માટે રીત જણાવો.'),
    ('gu', 'wardrobe', 'કપડાંને ગોઠવવા માટે માર્ગદર્શન આપો.'),
    ('hi', 'dispute', 'कारोबार के भागीदार से अनबन कैसे सुलझाऊँ?'),
    ('gu', 'dispute', 'વેપારમાં ભાગીદાર સાથે મતભેદ કેવી રીતે ઉકેલું?'),
    ('gu', 'dispute', 'વ્યવસાયના સાથી સાથે મતભેદ દૂર કરવા શું કરવું?'),
]


class NativeInflectionTests(unittest.TestCase):
    def test_explicit_subject_aliases_select_existing_plans(self):
        for language, key, query in CASES:
            for value in (query, unicodedata.normalize('NFD', query)):
                with self.subTest(query=value):
                    plan = plan_for(value)
                    self.assertIsNotNone(plan)
                    self.assertEqual(plan.name, PLANS[language][key][0])
                    self.assertEqual(plan.language, language)
                    reply, action = LocalReasoner().respond(value, assess(value), [], [], [])
                    self.assertTrue(reply.startswith(TEXT[language]['plan']))
                    self.assertIn(TEXT[language]['no_source'], reply)
                    self.assertIsNone(action)

    def test_existing_abstention_guards_cover_aliases(self):
        for language, _, query in CASES:
            suffixes = (' नहीं', ' सॉफ्टवेयर', ' ઘર') if language == 'hi' else (' નહીં', ' સોફ્ટવેર', ' घर')
            for suffix in suffixes:
                with self.subTest(query=query + suffix):
                    self.assertIsNone(plan_for(query + suffix))
            self.assertIsNone(plan_for(query + ' and clean my house and organize my wardrobe'))

    def test_new_words_are_not_substring_or_suffix_rules(self):
        for query in [
            'અકબાટની ગોઠવણ કેવી રીતે કરવી?',
            'કપડાંનેઅ ગોઠવવા માટે માર્ગદર્શન આપો.',
            'અઘરના રૂમની સફાઈ માટે યોજના આપો.',
            'अकारोबार के भागीदार से अनबन कैसे सुलझाऊँ?',
            'कारोबार के अभागीदार से अनबन कैसे सुलझाऊँ?',
            'कारोबार के भागीदार से अनबनअ कैसे सुलझाऊँ?',
            'અવેપારમાં ભાગીદાર સાથે મતભેદ કેવી રીતે ઉકેલું?',
            'વ્યવસાયના અસાથી સાથે મતભેદ કેવી રીતે ઉકેલું?',
        ]:
            with self.subTest(query=query):
                self.assertIsNone(plan_for(query))

    def test_disagreement_needs_all_three_subject_cues(self):
        for query in [
            'भागीदार से अनबन कैसे सुलझाऊँ?',
            'कारोबार में अनबन कैसे सुलझाऊँ?',
            'कारोबार के भागीदार से बातचीत कैसे शुरू करूँ?',
            'વેપારમાં મતભેદ કેવી રીતે ઉકેલું?',
            'સાથી સાથે મતભેદ કેવી રીતે ઉકેલું?',
            'વ્યવસાયના સાથી સાથે વાત કેવી રીતે કરું?',
        ]:
            with self.subTest(query=query):
                self.assertIsNone(plan_for(query))


    def test_reviewed_negations_compounds_and_subject_mismatches_abstain(self):
        for query in [
            'કબાટની ગોઠવણ કરવી નથી.',
            'કપડાંને ગોઠવવા નથી.',
            'कारोबार के भागीदार से अनबन न सुलझाओ।',
            'કબાટની ગોઠવણ અને બગીચાની સંભાળ સમજાવો.',
            'कारोबार के भागीदार से अनबन सुलझाओ और खाना बनाने की विधि बताओ।',
            'રમકડાંના કબાટની ગોઠવણ સમજાવો.',
            'વેપારમાં મંદી છે. મારા જીવનના સાથી સાથે મતભેદ છે, સંબંધમાં વાત કેવી રીતે કરું?',
            'कारोबार बढ़ रहा है। खेल के भागीदार से अनबन सुलझानी है।',
            'ઘરની સફાઈ કરવી નથી.',
            'व्यापार के साझेदार से विवाद न सुलझाओ।',
            'રમકડાંના કબાટ વ્યવસ્થિત કરવા છે.',
            'પુસ્તકોની કબાટની ગોઠવણ સમજાવો.',
            'કારોબાર માટે કામ કરો; કપડાંને ગોઠવવા છે.',
        ]:
            with self.subTest(query=query):
                self.assertIsNone(plan_for(query))

    def test_new_aliases_do_not_guess_cupboard_contents_or_partner_roles(self):
        for query in [
            'કબાટની ગોઠવણ કેવી રીતે કરવી?',
            'રસોડાના વાસણો રાખવાના કબાટની ગોઠવણ સમજાવો.',
            'ઓફિસની ફાઇલો રાખવાના કબાટની ગોઠવણ સમજાવો.',
            'જૂતાં રાખવાના કબાટની ગોઠવણ માટે મદદ કરો.',
            'વેપારમાં કામ કરતા મારા જીવનના સાથી સાથે મતભેદ ઉકેલવા મદદ કરો.',
            'कारोबार करने वाले मेरे खेल के भागीदार से अनबन सुलझाने का तरीका बताएँ।',
            'कारोबार के भागीदार के खेल के साथी से अनबन सुलझाने का तरीका बताएँ।',
            'व्यापार के खेल के भागीदार से अनबन सुलझाने का तरीका बताएँ।',
            'વ્યવસાયના સાથીના જીવનના સાથી સાથે મતભેદ ઉકેલવા મદદ કરો.',
            'કબાટની ગોઠવણ અને ઘરની સફાઈ માટે મદદ કરો.',
        ]:
            for value in (query, unicodedata.normalize('NFD', query)):
                with self.subTest(query=value):
                    self.assertIsNone(plan_for(value))

    def test_new_dispute_subject_phrases_are_normalized_and_word_bounded(self):
        for query in [
            'मेरे कारोबार के साझेदार के साथ मतभेद कैसे सुलझाएँ?',
            'व्यापार के साझेदार से अनबन सुलझाने का तरीका बताइए।',
            'મારા વ્યવસાયના સાથી સાથે મતભેદ કેવી રીતે ઉકેલું?',
        ]:
            for value in (query, unicodedata.normalize('NFD', query)):
                with self.subTest(query=value):
                    plan = plan_for(value)
                    self.assertIsNotNone(plan)
                    self.assertEqual(plan.name, PLANS[plan.language]['dispute'][0])
        for query in [
            'कारोबार के भागीदार से अनबनअ कैसे सुलझाऊँ?',
            'વેપારમાં ભાગીદાર સાથે મતભેદઅ કેવી રીતે ઉકેલું?',
        ]:
            self.assertIsNone(plan_for(query))

    def test_added_aliases_deliberately_abstain_on_multiclause_input(self):
        for separator in ('. ', '। ', ', ', '; ', ': ', '\n', ' and ', ' અને ',
                          ' પરંતુ ', ' પણ ', ' लेकिन ', ' परंतु ', ' but ', ' however '):
            query = 'કપડાંને ગોઠવવા છે' + separator + 'ઘરમાં સમય ઓછો છે'
            with self.subTest(separator=separator):
                self.assertIsNone(plan_for(query))
        self.assertIsNone(plan_for('કારોબાર વિશે કહો also કપડાંને ગોઠવવા છે'))

    def test_broader_original_paraphrases_remain_out_of_scope(self):
        for query in [
            'अलमारी जमाने का आसान तरीका बताइए।',
            'कपड़ों की तह लगाकर उन्हें क्रम से कैसे रखूँ?',
            'अलमारी में कपड़े तरतीब से कैसे रखूँ?',
            'साझेदारी में मतभेद सुलझाने का तरीका बताइए।',
        ]:
            with self.subTest(query=query):
                self.assertIsNone(plan_for(query))


if __name__ == '__main__':
    unittest.main()
