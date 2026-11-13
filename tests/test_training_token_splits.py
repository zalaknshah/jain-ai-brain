"""Exact model-input split integrity, no ML dependencies or training."""
import unittest
from jace.training_worker import encode_training_splits


class Tokenizer:
    def __init__(self, tokens): self.tokens = tokens
    def encode(self, text, *, add_special_tokens):
        assert add_special_tokens is False
        return self.tokens[text]


def prompt(text): return 'Instruction:\n' + text + '\nResponse:\n'


class TokenSplitTests(unittest.TestCase):
    def setUp(self):
        self.plan = {'data': {'train': [{'instruction': 'first', 'response': 'one'}],
                              'evaluation': [{'instruction': 'second', 'response': 'two'}]},
                     'sequence_length': 8}
        self.tokens = {prompt('first'): [1, 2], prompt('second'): [1, 3], 'one': [4], 'two': [5]}

    def encode(self): return encode_training_splits(self.plan, Tokenizer(self.tokens), 7, 8)

    def test_distinct_prompts_and_response_only_labels(self):
        self.assertEqual(self.encode(), ([([1, 2, 4, 7], [-100, -100, 4, 7])],
                                        [([1, 3, 5, 7], [-100, -100, 5, 7])]))

    def test_unknown_or_normalized_prompt_collision_rejected_despite_different_answers(self):
        for sequence in ([0], [1, 2]):
            self.tokens[prompt('first')] = list(sequence)
            self.tokens[prompt('second')] = list(sequence)
            with self.assertRaisesRegex(ValueError, 'duplicate tokenized prompt'): self.encode()

    def test_duplicate_within_training_or_evaluation_rejected(self):
        for split in ('train', 'evaluation'):
            with self.subTest(split=split):
                row = self.plan['data'][split][0]
                self.plan['data'][split].append(dict(row))
                with self.assertRaisesRegex(ValueError, 'duplicate tokenized prompt'): self.encode()
                self.plan['data'][split].pop()

    def test_identical_answers_are_not_prompt_leakage(self):
        self.tokens['two'] = [4]
        self.encode()

    def test_prefix_is_not_exact_collision(self):
        self.tokens[prompt('second')] = [1, 2, 3]
        self.encode()

    def test_encoded_ids_checked_even_if_vocab_map_would_be_valid(self):
        for key in (prompt('first'), 'one', prompt('second'), 'two'):
            original = self.tokens[key]
            for bad in (-1, 8, True, 1.0, '1', None):
                with self.subTest(key=key, bad=bad):
                    self.tokens[key] = [bad]
                    with self.assertRaisesRegex(ValueError, 'token IDs'): self.encode()
            self.tokens[key] = original

    def test_empty_and_nonlist_encodings_rejected(self):
        for key in (prompt('first'), 'one'):
            original = self.tokens[key]
            for bad in ([], None, (1,), 'x'):
                self.tokens[key] = bad
                with self.assertRaises(ValueError): self.encode()
            self.tokens[key] = original

    def test_budget_boundary_includes_eos(self):
        self.plan['sequence_length'] = 4
        self.encode()
        self.plan['sequence_length'] = 3
        with self.assertRaisesRegex(ValueError, 'token budget'): self.encode()

    def test_tokenizer_failure_propagates_without_partial_result(self):
        del self.tokens[prompt('second')]
        with self.assertRaises(KeyError): self.encode()


if __name__ == '__main__': unittest.main()
