"""Structural checks for exposed annotation-scope development material.

Standard library only: no evaluator/candidate imports, inference, or network.
These checks bind recorded reviews to retained inputs and enforce the stated
editing controls. They do not infer semantic labels, prove that all necessary
premises are present, validate reviewer independence, or measure performance.
"""
from collections import Counter, defaultdict
import copy
import hashlib
import json
import math
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT = 'evals/support_scope_development.json'
REVIEW = 'evals/support_scope_development_review.json'
UNRESOLVED = 'evals/support_scope_review_cases.json'
CONTRACT = 'docs/CLAIM_SUPPORT_SCOPE.md'
LABELS = {'supported', 'contradicted', 'not_established'}
PAIR_IDS = [f'P{i:02}' for i in range(1, 16)]
CASE_IDS = [pair + side for pair in PAIR_IDS for side in 'AB']
REVIEW_IDS = ['R01', 'R02', 'R03', 'R04']
INVENTORY_IDS = ['P07A', 'P07B', 'P08A', 'P08B', 'P14A', 'P14B']

# Read-only bytes independently compared to the pre-proposal checkout at
# 5879931b5de8cf39c52273db2a6a5f1a6b05a6ec. No git or model is needed to test.
HISTORICAL_SHA256 = {
    'scripts/evaluate_claim_support.py':
        'f24f017ad344d572e61979519730c5fc8dbd1be162fb24d648ab66deae04ae13',
    'scripts/predict_pretrained_support.py':
        '11217322391b15ff6dacb37947f6bafc31b30f9c0abae8d032cec9cf43532e2e',
    'scripts/predict_deberta_support.py':
        'ff0597ba1abbe56c1cdbd238b05c42fd239d220f50e669656a921eab7e208078',
    'scripts/predict_controlled_support.py':
        '2ad4fd5c50d681f62dcc94fc3ba2f994e23fbd0bd7ebf31409703bdf18fb0262',
    'evals/claim_support_cases.json':
        '56791ccb519cd90fa8b615c40bb3b3aa17094b4fb702c37f594328c5742c4a31',
    'evals/controlled_support_cases.json':
        '36138ef46eef332f663491844b03753e58e499d7f89bde5563fe85400ba12baa',
    'evals/controlled_support_controls.json':
        '6b1b65b00c7c5002afa912dcad0b9ddee01b602001c3991af33b78dcf909edaf',
    'evals/controlled_support_large_observed.json':
        'c66750e8f4d3afaf502490ca8a9933278ae4e8876fd131142662ddf1fd0825f0',
    'evals/controlled_support_observed.json':
        '0d5a4b7a4d3fc34eea06176f6b445d0c29a7323a5cf401709f488545d5392f23',
    'evals/paired_support_cases.json':
        '5efaa7095d8aa8403a2399ec4ce8818cde37f314beca833959b8ffe2d3995686',
    'evals/paired_support_deberta_frozen.json':
        '5fa17874f1ba72d511d1544cf3fb4dbe5827be473a8bfb50d136663a339436b6',
    'evals/paired_support_label_review.json':
        '33b7f55ff8d43844db5b45e65650b5825d77d1be179565eeca90b49a85e77a08',
    'evals/paired_support_minilm_frozen.json':
        '2db18a68e8aeb2e2d5a80747e3d49cdc9a0a5ceffad55f5fae2e9b4c763e9860',
    'evals/paired_support_observed.json':
        'ffddda493024d86c528f2149ccb75016f18865b8a6bd4ad659f18c118fe5cb11',
    'evals/pretrained_support_cases.json':
        'beb7d4c46bd2f72143030044348094ddd382549ee95bc3d90f663d014ee06334',
    'evals/pretrained_support_frozen.json':
        '75b55e42d59532f14341a09358a3b73c01e25a891956ce814403f3a0cf84d3d0',
    'evals/pretrained_support_label_review.json':
        'ba8bf90e46e1448a8debfe47f9abdda3f9f4c3bba24a8a02f63a031177933907',
    'evals/pretrained_support_model_manifest.json':
        '984c1c0662991eeb529d98645d41989a6e8e635182b48dad984f7e87cd9e9c74',
    'evals/pretrained_support_observed.json':
        'fa1a795092d80b5aac079b3b5477a04aae459eca74f1d8e1817b4047e6e0fe36',
    'evals/pretrained_support_requirements.lock':
        'b38cf78afe06f8ccb09d7a10df3c22a0cc45f5ae954ab359d4c87a7073d4a16f',
    'evals/pretrained_support_wheels.json':
        'dbdf9bc2ef9b389611a1443acd78228a294cd40f188e5106943e0ac39acaf52b',
    'evals/semantic_support_cases.json':
        '66e76296a8e9f969a51d94c3759177fab8e8087d225b53e4bcf8b4ef3d7c050f',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def input_sha(case):
    """The review digest covers exactly the complete context and exact claim."""
    value = {key: case[key] for key in ('context', 'claim')}
    return sha(json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8'))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError('nonfinite JSON value: ' + value)


def finite_tree(value):
    # parse_constant alone does not reject JSON numbers such as 1e999.
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('nonfinite JSON number')
    if isinstance(value, dict):
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)


def decode(raw):
    value = json.loads(raw, object_pairs_hook=unique_object,
                       parse_constant=invalid_constant)
    finite_tree(value)
    return value


def read(path):
    return decode((ROOT / path).read_text(encoding='utf-8'))


class SupportScopeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.development = read(DEVELOPMENT)
        cls.review = read(REVIEW)
        cls.unresolved = read(UNRESOLVED)
        cls.cases = cls.development['cases']
        cls.by_id = {case['case_id']: case for case in cls.cases}
        cls.doc = (ROOT / CONTRACT).read_text(encoding='utf-8')

    def fields(self, value, schema):
        self.assertIs(type(value), dict)
        self.assertEqual(set(value), set(schema))
        for key, kind in schema.items():
            self.assertIs(type(value[key]), kind, key)
            if kind is str:
                self.assertTrue(value[key].strip(), key)

    def strings(self, value, *, nonempty=True):
        self.assertIs(type(value), list)
        if nonempty:
            self.assertTrue(value)
        for item in value:
            self.assertIs(type(item), str)
            self.assertTrue(item.strip())
        self.assertEqual(len(value), len(set(value)))

    def binding(self, reviewed, case):
        self.assertEqual(reviewed['case_id'], case['case_id'])
        self.assertRegex(reviewed['context_claim_sha256'], r'\A[0-9a-f]{64}\Z')
        self.assertEqual(reviewed['context_claim_sha256'], input_sha(case))

    def test_strict_decoder_rejects_duplicate_keys_and_nonfinite_values(self):
        for raw in ('{"a": 1, "a": 2}', '{"x": {"a": 1, "a": 1}}',
                    '{"a": 1, "\\u0061": 2}', '[NaN]', '[Infinity]',
                    '[-Infinity]', '{"nested": [1e999]}', '[-1e999]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                decode(raw)
        self.assertEqual(decode('{"x": [null, false, 1, 1.25]}'),
                         {'x': [None, False, 1, 1.25]})

    def test_exact_type_checks_do_not_accept_booleans_as_counts(self):
        for value in ({'count': True}, {'count': 1.0},
                      {'count': '1'}, {'count': 1, 'extra': None}):
            with self.subTest(value=value), self.assertRaises(AssertionError):
                self.fields(value, {'count': int})

    def test_development_schema_and_proposal_only_metadata(self):
        self.fields(self.development, {
            'artifact_kind': str, 'status': str, 'contract': str,
            'created_date': str, 'purpose': str, 'provenance': str,
            'usage_limits': list, 'pair_count': int, 'case_count': int,
            'pairs': list, 'cases': list, 'unique_context_claim_inputs': int,
            'revision': str, 'revision_summary': dict,
        })
        self.assertEqual(self.development['artifact_kind'],
                         'original_exposed_annotation_development_fixture')
        self.assertEqual(self.development['status'],
                         'independently_reviewed_development_proposal')
        self.assertEqual(self.development['contract'], CONTRACT)
        self.assertEqual(self.development['created_date'], '2026-11-10')
        self.assertEqual(self.development['revision'], 'scope_development_v1')
        self.strings(self.development['usage_limits'])
        for case in self.cases:
            with self.subTest(case=case['case_id']):
                self.fields(case, {
                    'case_id': str, 'pair_id': str, 'context': str, 'claim': str,
                    'draft_label': str, 'target_scope': str,
                    'evidence_spans': list, 'rationale': str,
                })
                self.assertIn(case['draft_label'], LABELS)

    def test_pair_membership_counts_and_only_disclosed_duplicate(self):
        self.assertEqual(self.development['pair_count'], 15)
        self.assertEqual(self.development['case_count'], 30)
        self.assertEqual(self.development['unique_context_claim_inputs'], 29)
        self.assertEqual([case['case_id'] for case in self.cases], CASE_IDS)
        self.assertEqual([p['pair_id'] for p in self.development['pairs']], PAIR_IDS)
        memberships = []
        for pair in self.development['pairs']:
            self.fields(pair, {'pair_id': str, 'topic': str,
                               'controlled_change': str, 'case_ids': list})
            self.strings(pair['case_ids'])
            self.assertEqual(pair['case_ids'], [pair['pair_id'] + s for s in 'AB'])
            for cid in pair['case_ids']:
                self.assertEqual(self.by_id[cid]['pair_id'], pair['pair_id'])
            memberships.extend(pair['case_ids'])
        self.assertEqual(memberships, CASE_IDS)
        inputs = defaultdict(list)
        for case in self.cases:
            inputs[(case['context'], case['claim'])].append(case['case_id'])
        self.assertEqual(len(inputs), 29)
        self.assertEqual([ids for ids in inputs.values() if len(ids) > 1],
                         [['P01B', 'P02A']])
        self.assertEqual(self.by_id['P01B']['draft_label'],
                         self.by_id['P02A']['draft_label'])

    def test_exactly_three_draft_classes_and_recorded_pair_transitions(self):
        # These are reviewed teaching-example expectations, not inferred labels.
        self.assertEqual(Counter(c['draft_label'] for c in self.cases),
                         Counter(supported=12, contradicted=3, not_established=15))
        for pair in PAIR_IDS:
            labels = tuple(self.by_id[pair + s]['draft_label'] for s in 'AB')
            expected = ('not_established', 'supported')
            if pair == 'P01':
                expected = ('supported', 'not_established')
            elif pair in {'P05', 'P10', 'P11'}:
                expected = ('not_established', 'contradicted')
            self.assertEqual(labels, expected, pair)
        special = {'P02B': 'wall_notice_content', 'P14B': 'joint_source_account',
                   'P15A': 'memo_b_content', 'P15B': 'memo_a_content_about_memo_b'}
        for case in self.cases:
            self.assertEqual(case['target_scope'],
                             special.get(case['case_id'], 'world'))

    def test_pair_descriptions_match_the_declared_edit_controls(self):
        expected = {
            'P01': 'Replace the direct assertion with an attributed report.',
            'P02': 'Keep the context identical and change only the claim target.',
            'P03': 'Add an explicit guarantee about the quoted proposition.',
            'P04': 'Add an explicit guarantee about the reported lever state.',
            'P05': 'Remove only the report wrapper around the negative proposition.',
            'P06': 'Change the exact proposition guaranteed true and explicitly leave the other time assertion unaddressed.',
            'P07': 'Add a truth bridge for the report of two pen-removal events.',
            'P08': 'Change only the starting quantity from report to narration.',
            'P09': "Add the marker's membership at the required time.",
            'P10': "Change only K's location relative to the rule domain.",
            'P11': "Keep the context identical and narrow only the claim's time interval.",
            'P12': 'Add an explicit unchanged-location premise.',
            'P13': 'Add that the same person held the role throughout the interval.',
            'P14': 'Keep the context identical and change only the target to a consequence of both accounts.',
            'P15': 'Keep the context identical and change only the target attribution level.',
        }
        self.assertEqual({p['pair_id']: p['controlled_change']
                          for p in self.development['pairs']}, expected)

    def test_context_only_pairs_preserve_claim_and_exact_controlled_change(self):
        additions = {
            'P03': ' Narrator fact: The quoted statement about the east gate is true in this scenario.',
            'P04': " Narrator fact: The notice's statement about the silver lever at 11:00 is true.",
            'P07': " Narrator fact: The note's exact assertion about the two pen removals during the whole accounting interval is true in this scenario.",
            'P09': ' Marker K is in the courtyard at noon.',
            'P12': " The token's location did not change from 13:00 through 18:00.",
            'P13': ' The same person continuously held the sole oven technician role from 09:00 through 15:00.',
        }
        replacements = {
            'P01': ('The violet lamp is lit at noon.',
                    'The wall notice says, "The violet lamp is lit at noon."'),
            'P05': ('The receipt note says, "Ivo did not receive the red envelope on Tuesday."',
                    'Ivo did not receive the red envelope on Tuesday.'),
            'P06': ("The proposition 'The cistern held six liters at 08:00' is true in this scenario. This stipulation does not address the 10:00 assertion.",
                    "The proposition 'The cistern held nine liters at 10:00' is true in this scenario. This stipulation does not address the 08:00 assertion."),
            'P08': ('A label says, "There are exactly eight beads in the jar at 14:00." The quoted label ends here.',
                    'Narrator fact: There are exactly eight beads in the jar at 14:00.'),
            'P10': ('Marker K is outside the courtyard at noon.',
                    'Marker K is in the courtyard at noon.'),
        }
        self.assertEqual(set(additions) | set(replacements),
                         set(PAIR_IDS) - {'P02', 'P11', 'P14', 'P15'})
        for pair in sorted(set(additions) | set(replacements)):
            a, b = (self.by_id[pair + s] for s in 'AB')
            with self.subTest(pair=pair):
                self.assertEqual(a['claim'], b['claim'])
                if pair in additions:
                    expected = a['context'] + additions[pair]
                else:
                    old, new = replacements[pair]
                    self.assertEqual(a['context'].count(old), 1)
                    expected = a['context'].replace(old, new)
                self.assertEqual(b['context'], expected)

    def test_claim_only_pairs_preserve_complete_context(self):
        changes = {
            'P02': ('The violet lamp is lit at noon.',
                    'The wall notice says that the violet lamp is lit at noon.'),
            'P11': ('Dena moved the token from the drawer to the desk at some time on Wednesday.',
                    'Dena moved the token from the drawer to the desk after 14:00 on Wednesday.'),
            'P14': ('The bowl contained exactly eight buttons at 11:00.',
                    'Taken together, the accounts in Sheet A and Sheet B imply that the bowl contained exactly eight buttons at 11:00.'),
            'P15': ('Memo B says that the purple dial points left at 16:00.',
                    'Memo A says that Memo B says the purple dial points left at 16:00.'),
        }
        for pair, claims in changes.items():
            a, b = (self.by_id[pair + s] for s in 'AB')
            with self.subTest(pair=pair):
                self.assertEqual(a['context'], b['context'])
                self.assertEqual((a['claim'], b['claim']), claims)

    def test_every_row_has_own_context_and_exact_local_evidence_spans(self):
        for case in self.cases:
            with self.subTest(case=case['case_id']):
                self.assertTrue(case['context'].startswith('Fictional scenario. '))
                self.strings(case['evidence_spans'])
                for span in case['evidence_spans']:
                    self.assertIn(span, case['context'])
        # Important shared premises must be repeated in *both* rows, never
        # supplied by pair metadata or by looking up the neighboring row.
        premises = {
            'P06': 'The meter sheet says, "The cistern held six liters at 08:00 and nine liters at 10:00."',
            'P09': 'Every marker in the courtyard at noon is blue at noon. Marker K exists.',
            'P10': 'Every marker in the courtyard at noon is blue at noon.',
            'P11': 'Dena did not move the token at any time after 14:00 through the end of Wednesday.',
            'P12': 'At 13:00 Mara placed the token in the cupboard. Mara did not move the token again between 13:00 and 18:00.',
            'P13': 'At 09:00 Reni was the sole oven technician. At 15:00 the sole oven technician reset the timer.',
            'P14': 'Narrator fact: Sheet A and Sheet B refer to the same bowl on the same day.',
            'P15': 'Memo A says, "Memo B says the purple dial points left at 16:00."',
        }
        for pair, premise in premises.items():
            for side in 'AB':
                self.assertIn(premise, self.by_id[pair + side]['context'])

    def test_repaired_inventory_intervals_events_and_scopes_are_local(self):
        specs = {'P07': ('12:00', '13:00', 'pens', 'pen', 'desk'),
                 'P08': ('14:00', '15:00', 'beads', 'bead', 'jar'),
                 'P14': ('10:00', '11:00', 'buttons', 'button', 'bowl')}
        for pair, (start, end, items, item, container) in specs.items():
            interval = (
                f'The accounting interval covers every inventory change after the initial count at {start} '
                f'up to and including the final count at {end}. The final count at {end} is taken after all '
                f'inventory changes occurring at {end}, and all of those changes are included in the accounting interval.'
            )
            persistence = (
                f'Throughout the whole accounting interval, counted {items} retain their identities and remain {items}, '
                f"and the {container}'s {item} count changes only through additions or removals."
            )
            for side in 'AB':
                case = self.by_id[pair + side]
                with self.subTest(case=case['case_id']):
                    context = case['context']
                    if pair == 'P14':
                        # All arithmetic restrictions belong to Sheet B, not
                        # the narrator or an unquoted annotation rationale.
                        before, separator, account = context.partition('Sheet B says, "')
                        self.assertEqual(separator, 'Sheet B says, "')
                        self.assertTrue(account.endswith('"'))
                        self.assertEqual(account.count('"'), 1)
                        self.assertNotIn('Narrator fact:', account)
                        self.assertNotIn('accounting interval', before)
                        context = account[:-1]
                        self.assertIn(f'In this account, the count at {end} means that final count.', context)
                    else:
                        self.assertIn('Narrator fact: ' + interval, context)
                        self.assertIn('Narrator fact: ' + persistence, context)
                        self.assertIn(f'In this scenario, the count at {end} means that final count.', context)
                    self.assertIn(interval, context)
                    self.assertIn(persistence, context)
                    self.assertIn(f'No {items} were added to the {container} at any time during the whole accounting interval, including no return of any', context)
                    if pair == 'P07':
                        self.assertIn('Narrator fact: At 12:00 the desk held exactly nine pens.', context)
                        self.assertIn('A note says, "During the whole accounting interval defined above, exactly two distinct pens were removed from the desk, each exactly once." The quoted note ends here.', context)
                        self.assertIn('At most two pen-removal events occurred during that whole interval, each removing one pen.', context)
                    else:
                        count = 'three' if pair == 'P08' else 'four'
                        self.assertIn(f'During the whole accounting interval, exactly {count} distinct {items} were removed from the {container}, each in a single one-{item} removal event.', context)
                        self.assertIn(f'No {item}-removal events occurred anywhere in that whole interval besides these {count} events.', context)

    def test_review_record_schema_and_recomputed_counts(self):
        self.fields(self.review, {
            'protocol': int, 'artifact_kind': str, 'status': str,
            'created_date': str, 'artifact_sha256': dict, 'counts': dict,
            'limits': list, 'revision_history': list, 'cases': list,
            'review_cases': list,
        })
        self.assertEqual(self.review['protocol'], 1)
        self.assertEqual(self.review['artifact_kind'], 'exposed_development_annotation_review')
        self.assertEqual(self.review['status'], 'development_review_only')
        self.assertEqual(self.review['created_date'], self.development['created_date'])
        self.strings(self.review['limits'])
        counts = self.review['counts']
        self.fields(counts, {
            'development_rows': int, 'unique_development_inputs': int,
            'pedagogical_pairs': int, 'current_adjudicable_rows': int,
            'current_label_counts': dict, 'unresolved_review_examples': int,
        })
        self.fields(counts['current_label_counts'], {label: int for label in LABELS})
        self.assertEqual(counts, {
            'development_rows': len(self.cases),
            'unique_development_inputs': len({input_sha(c) for c in self.cases}),
            'pedagogical_pairs': len(self.development['pairs']),
            'current_adjudicable_rows': sum(r['annotation_disposition'] == 'adjudicable'
                                            for r in self.review['cases']),
            'current_label_counts': dict(Counter(r['semantic_label'] for r in self.review['cases'])),
            'unresolved_review_examples': len(self.unresolved['cases']),
        })

    def test_current_review_binds_every_input_label_and_review_round(self):
        self.assertEqual([r['case_id'] for r in self.review['cases']], CASE_IDS)
        for reviewed in self.review['cases']:
            cid = reviewed['case_id']
            with self.subTest(case=cid):
                self.fields(reviewed, {
                    'case_id': str, 'context_claim_sha256': str,
                    'annotation_disposition': str, 'semantic_label': str,
                    'review_round': str, 'reason': str,
                })
                self.binding(reviewed, self.by_id[cid])
                self.assertEqual(reviewed['annotation_disposition'], 'adjudicable')
                self.assertIn(reviewed['semantic_label'], LABELS)
                self.assertEqual(reviewed['semantic_label'], self.by_id[cid]['draft_label'])
                stage = 'initial_label_free_review'
                if cid in {'P06A', 'P06B'}:
                    stage = 'revision_1_targeted_recheck'
                elif cid in INVENTORY_IDS:
                    stage = 'revision_2_targeted_recheck'
                self.assertEqual(reviewed['review_round'], stage)

    def test_review_binding_detects_changed_input_without_using_author_notes(self):
        case = self.cases[0]
        reviewed = self.review['cases'][0]
        for key in ('context', 'claim'):
            changed = copy.deepcopy(case)
            changed[key] += ' Changed.'
            with self.subTest(key=key), self.assertRaises(AssertionError):
                self.binding(reviewed, changed)
        notes = copy.deepcopy(case)
        notes.update(rationale='Different annotation note.', draft_label='contradicted',
                     target_scope='different_note', evidence_spans=['Another note.'])
        self.assertEqual(input_sha(notes), input_sha(case))

    def test_unresolved_originals_are_unlabeled_and_repairs_are_conditional(self):
        self.fields(self.unresolved, {
            'artifact_kind': str, 'status': str, 'contract': str,
            'purpose': str, 'cases': list, 'revision': str,
        })
        self.assertEqual(self.unresolved['artifact_kind'], 'unlabeled_annotation_review_examples')
        self.assertEqual(self.unresolved['status'], 'review_needed')
        self.assertEqual(self.unresolved['contract'], CONTRACT)
        self.assertEqual(self.unresolved['revision'], self.development['revision'])
        self.assertEqual([c['case_id'] for c in self.unresolved['cases']], REVIEW_IDS)
        expected_outcomes = {
            'R01': ['not_established', 'supported'], 'R02': ['not_established'],
            'R03': ['not_established', 'supported'],
            'R04': ['supported', 'not_established', 'contradicted'],
        }
        for case in self.unresolved['cases']:
            with self.subTest(case=case['case_id']):
                self.fields(case, {
                    'case_id': str, 'context': str, 'claim': str,
                    'review_issue': str, 'repair_options': list,
                    'review_disposition': str, 'conditional_repair_outcomes': list,
                    'semantic_label': type(None),
                })
                self.assertTrue(case['context'].startswith('Fictional scenario. '))
                self.assertEqual(case['review_disposition'], 'review_needed')
                self.assertIsNone(case['semantic_label'])
                self.strings(case['repair_options'])
                outcomes = case['conditional_repair_outcomes']
                self.assertEqual([o['semantic_label'] for o in outcomes],
                                 expected_outcomes[case['case_id']])
                for outcome in outcomes:
                    self.fields(outcome, {'repair': str, 'semantic_label': str, 'reason': str})
                    self.assertIn(outcome['semantic_label'], LABELS)
                    self.assertNotEqual(outcome['repair'], case['context'])
        self.assertTrue(set(REVIEW_IDS).isdisjoint(self.by_id))
        self.assertEqual(len({input_sha(c) for c in self.unresolved['cases']}), 4)
        self.assertTrue({input_sha(c) for c in self.cases}.isdisjoint(
            input_sha(c) for c in self.unresolved['cases']))

    def test_unresolved_review_bindings_retain_null_labels_and_hint_disclosure(self):
        self.assertEqual([r['case_id'] for r in self.review['review_cases']], REVIEW_IDS)
        for reviewed, case in zip(self.review['review_cases'], self.unresolved['cases']):
            self.fields(reviewed, {
                'case_id': str, 'context_claim_sha256': str,
                'annotation_disposition': str, 'semantic_label': type(None),
                'reason': str, 'conditional_repair_outcomes_reviewed': bool,
                'review_hints_visible': bool,
            })
            self.binding(reviewed, case)
            self.assertEqual(reviewed['annotation_disposition'], 'review_needed')
            self.assertIsNone(reviewed['semantic_label'])
            self.assertIs(reviewed['conditional_repair_outcomes_reviewed'], True)
            self.assertIs(reviewed['review_hints_visible'], True)

    def test_revision_history_preserves_initial_holds_and_targeted_rechecks(self):
        summary = self.development['revision_summary']
        self.fields(summary, {
            'truth_guarantee_repairs': list, 'inventory_identity_interval_and_event_repairs': list,
            'claims_changed': list, 'draft_semantic_label_changes': list,
            'review_record': str, 'P14_scope': str,
        })
        self.assertEqual(summary['truth_guarantee_repairs'], ['P06A', 'P06B'])
        self.assertEqual(summary['inventory_identity_interval_and_event_repairs'], INVENTORY_IDS)
        self.assertEqual(summary['claims_changed'], [])
        self.assertEqual(summary['draft_semantic_label_changes'], [])
        self.assertEqual(summary['review_record'], REVIEW)
        history = self.review['revision_history']
        self.assertEqual(len(history), 3)
        initial = history[0]
        self.fields(initial, {'stage': str, 'rows_reviewed': int, 'adjudicable_rows': int,
                              'held_case_ids': list, 'finding': str})
        self.assertEqual(initial['stage'], 'initial_review')
        self.assertEqual((initial['rows_reviewed'], initial['adjudicable_rows']), (30, 29))
        self.assertEqual(initial['held_case_ids'], ['P06A'])
        for round_number, changed, held in (
            (1, ['P06A', 'P06B'] + INVENTORY_IDS, ['P07B', 'P08B', 'P14B']),
            (2, INVENTORY_IDS, []),
        ):
            record = history[round_number]
            self.fields(record, {'stage': str, 'changed_context_ids': list,
                                 'adjudicable_changed_rows': int, 'held_case_ids': list,
                                 'finding': str})
            self.assertEqual(record['stage'], f'revision_{round_number}_targeted_recheck')
            self.assertEqual(record['changed_context_ids'], changed)
            self.assertEqual(record['held_case_ids'], held)
            self.assertEqual(record['adjudicable_changed_rows'], len(changed) - len(held))

    def test_review_manifest_binds_document_and_both_data_files(self):
        manifest = self.review['artifact_sha256']
        self.fields(manifest, {path: str for path in (CONTRACT, DEVELOPMENT, UNRESOLVED)})
        for path, expected in manifest.items():
            with self.subTest(path=path):
                self.assertFalse(Path(path).is_absolute())
                self.assertNotIn('..', Path(path).parts)
                self.assertRegex(expected, r'\A[0-9a-f]{64}\Z')
                self.assertEqual(sha((ROOT / path).read_bytes()), expected)

    def test_contract_discloses_development_limits_and_links_matching_artifacts(self):
        for text in (
            '30 case rows in 15 pedagogical pairs', '29 unique original context-claim inputs',
            'P01B and P02A intentionally reuse one anchor',
            'Each case repeats all necessary context.',
            'not a fourth semantic class', 'leave the semantic label unset',
            'not labels for the unresolved originals',
            'The same reviewer performed the initial review and both targeted rechecks',
            'that portion was not blinded',
            'Structural validation checks formatting and internal references, not semantic correctness.',
            'does not qualify either pretrained candidate or authorize corpus admission',
        ):
            self.assertIn(text, self.doc)
        for path in (DEVELOPMENT, UNRESOLVED, REVIEW):
            self.assertIn('(../' + path + ')', self.doc)

    def test_frozen_evaluator_candidates_inputs_predictions_and_scores_untouched(self):
        for path, expected in HISTORICAL_SHA256.items():
            with self.subTest(path=path):
                self.assertEqual(sha((ROOT / path).read_bytes()), expected)
        # An appended pointer is permitted, but the historical results text,
        # score tables, qualification conclusion, and caveats remain byte exact.
        results = (ROOT / 'docs/PAIRED_SUPPORT_RESULTS.md').read_bytes()
        self.assertGreaterEqual(len(results), 10037)
        self.assertEqual(sha(results[:10037]),
                         'f2f523cb332870152811bac0a01c56b2a6d45a37acb7b123ce893edb292c5679')


if __name__ == '__main__':
    unittest.main()
