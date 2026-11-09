"""Original orthographic fixtures, not copied source text or translation claims."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import unicodedata

from jace_study_query import (MAX_INPUT_BYTES, NOTICE, QueryPreparationError,
                               prepare_query, transliterate_sanskrit, main)


class SanskritQueryPreparationTests(unittest.TestCase):
    def test_core_equivalent_script_fragments(self):
        pairs = [('जीव अजीव', 'જીવ અજીવ', 'jīva ajīva'),
                 ('धर्म कर्म', 'ધર્મ કર્મ', 'dharma karma'),
                 ('अहिंसा सत्य', 'અહિંસા સત્ય', 'ahiṃsā satya'),
                 ('ज्ञान दर्शन', 'જ્ઞાન દર્શન', 'jñāna darśana'),
                 ('कमल वाक्', 'કમલ વાક્', 'kamala vāk'),
                 ('सोऽहम् देवः', 'સોઽહમ્ દેવઃ', "so'ham devaḥ")]
        for deva, gujr, expected in pairs:
            for lang, text in [('sa-Deva', deva), ('sa-Gujr', gujr)]:
                with self.subTest(text=text):
                    self.assertEqual(transliterate_sanskrit(text, lang), expected)
                    self.assertEqual(transliterate_sanskrit(unicodedata.normalize('NFD', text), lang), expected)

    def test_classical_independent_vowels(self):
        self.assertEqual(transliterate_sanskrit('अ आ इ ई उ ऊ ऋ ॠ ऌ ॡ ए ऐ ओ औ', 'sa-Deva'),
                         'a ā i ī u ū ṛ ṝ ḷ ḹ e ai o au')
        self.assertEqual(transliterate_sanskrit('અ આ ઇ ઈ ઉ ઊ ઋ ૠ ઌ ૡ એ ઐ ઓ ઔ', 'sa-Gujr'),
                         'a ā i ī u ū ṛ ṝ ḷ ḹ e ai o au')

    def test_vowel_signs_and_conjuncts(self):
        self.assertEqual(transliterate_sanskrit('क का कि की कु कू कृ कॄ कॢ कॣ के कै को कौ', 'sa-Deva'),
                         'ka kā ki kī ku kū kṛ kṝ kḷ kḹ ke kai ko kau')
        self.assertEqual(transliterate_sanskrit('ક કા કિ કી કુ કૂ કૃ કૄ કૢ કૣ કે કૈ કો કૌ', 'sa-Gujr'),
                         'ka kā ki kī ku kū kṛ kṝ kḷ kḹ ke kai ko kau')
        self.assertEqual(transliterate_sanskrit('क्ष त्र ज्ञ श्र', 'sa-Deva'), 'kṣa tra jña śra')
        self.assertEqual(transliterate_sanskrit('ક્ષ ત્ર જ્ઞ શ્ર', 'sa-Gujr'), 'kṣa tra jña śra')

    def test_whitespace_and_danda_preserve_word_boundaries(self):
        for lang, text in [('sa-Deva','  जीव\tअजीव।\nकर्म॥  धर्म\u00a0'), ('sa-Gujr','  જીવ\tઅજીવ।\nકર્મ॥  ધર્મ\u00a0')]:
            self.assertEqual(transliterate_sanskrit(text, lang), 'jīva ajīva karma dharma')

    def test_preview_is_not_automatic_source_study_input(self):
        request = {'input_language':'sa-Deva','text':'जीव अजीव'}
        with patch('builtins.open', side_effect=AssertionError('no file reads')):
            result = prepare_query(request)
        self.assertEqual(result['original_text'], request['text'])
        self.assertEqual(result['status'], 'preview_only')
        self.assertEqual(result['suggested_request'], {'operation':'search','query':'jīva ajīva','query_language':'sa-Latn'})
        self.assertFalse(result['source_opened'])
        self.assertFalse(result['search_performed'])
        self.assertEqual(result['notice'], NOTICE)
        self.assertNotIn('operation',result)

    def test_prepared_query_obeys_existing_study_request_limit(self):
        from jace.private_study import parse_request, StudyError
        preview = prepare_query({'input_language':'sa-Deva','text':'क'*256})
        request = preview['suggested_request']
        self.assertEqual(len(request['query']),512)
        self.assertEqual(parse_request(json.dumps(request,ensure_ascii=False).encode()),request)
        with self.assertRaises(StudyError):
            parse_request(json.dumps(preview,ensure_ascii=False).encode())
        for text in ['क'*257,'ख'*171,'क'*1024]:
            with self.subTest(length=len(text)), self.assertRaises(QueryPreparationError):
                prepare_query({'input_language':'sa-Deva','text':text})

    def test_docker_context_explicitly_includes_only_the_helper_file(self):
        root = Path(__file__).resolve().parents[1]
        lines = (root/'.dockerignore').read_text().splitlines()
        self.assertIn('!src/jace_study_query.py',lines)
        self.assertNotIn('!src/*',lines)
        self.assertNotIn('!src/**',lines)

    def test_no_hindi_or_gujarati_language_claim(self):
        for language in ['hi','gu','hi-IN','gu-IN','sa','sa-Latn','sa-Deva ']:
            with self.subTest(language=language), self.assertRaises(QueryPreparationError):
                transliterate_sanskrit('जीव अजीव', language)

    def test_unsupported_and_malformed_orthography_is_rejected(self):
        for text, language in [
            ('जीव જીવ','sa-Deva'), ('જીવ जीव','sa-Gujr'), ('jīva जीव','sa-Deva'),
            ('क़र्म','sa-Deva'), ('क़र्म','sa-Deva'), ('ક઼ર્મ','sa-Gujr'), ('ઍક','sa-Gujr'),
            ('जीँव','sa-Deva'), ('જીવઁ','sa-Gujr'), ('स्व॑र','sa-Deva'), ('ॐ','sa-Deva'),
            ('क्ष\u200d','sa-Deva'), ('ક્\u200cષ','sa-Gujr'), ('जीव १','sa-Deva'), ('જીવ ૧','sa-Gujr'),
            ('ाक','sa-Deva'), ('િક','sa-Gujr'), ('काा','sa-Deva'), ('કીિ','sa-Gujr'),
            ('्क','sa-Deva'), ('ક્્','sa-Gujr'), ('क्अ','sa-Deva'), ('ક્ૐ','sa-Gujr'),
            ('ंक','sa-Deva'), ('કંઃ','sa-Gujr'), ('कंा','sa-Deva'), ('ક્ં','sa-Gujr'),
            ('ऽक','sa-Deva'), ('કઽ','sa-Gujr'), ('कऽ क','sa-Deva'), ('જીવ.','sa-Gujr'),
        ]:
            with self.subTest(text=text), self.assertRaises(QueryPreparationError):
                transliterate_sanskrit(text, language)

    def test_bounded_schema(self):
        for request in [None, [], {}, {'input_language':'sa-Deva','text':'जीव','run':True},
                        {'input_language':None,'text':'जीव'}, {'input_language':'sa-Deva','text':None},
                        {'input_language':'sa-Deva','text':''}, {'input_language':'sa-Deva','text':'क'*1025}]:
            with self.subTest(request=request), self.assertRaises(QueryPreparationError):
                prepare_query(request)

    def call_cli(self, raw):
        class Input:
            buffer=io.BytesIO(raw)
        output=io.StringIO()
        code=0
        with patch('sys.argv',['jace-prepare-study-query','--stdin']), patch('sys.stdin',Input()), contextlib.redirect_stdout(output):
            try:
                main()
            except SystemExit as error:
                code=error.code
        return code,json.loads(output.getvalue())

    def test_cli_utf8_preview_and_failures_without_partial_query(self):
        code,result=self.call_cli(json.dumps({'input_language':'sa-Gujr','text':'જીવ અજીવ'},ensure_ascii=False).encode())
        self.assertEqual(code,0)
        self.assertEqual(result['suggested_request']['query'],'jīva ajīva')
        for raw in [b'bad', b'\xff', b' '* (MAX_INPUT_BYTES+1), b'{"input_language":"sa-Deva","text":"x","text":"y"}',
                    b'{"input_language":"sa-Deva","text":NaN}', b'['*2000]:
            code,result=self.call_cli(raw)
            self.assertEqual(code,2)
            self.assertEqual(result['status'],'rejected')
            self.assertNotIn('suggested_request',result)

    def test_module_has_no_engine_provider_or_source_imports(self):
        code = "import sys; from jace_study_query import prepare_query; prepare_query({'input_language':'sa-Deva','text':'जीव अजीव'}); print([x for x in ('jace.engine','jace.private_study','jace.api','sqlite3','urllib.request') if x in sys.modules])"
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'[]')


if __name__ == '__main__':
    unittest.main()
