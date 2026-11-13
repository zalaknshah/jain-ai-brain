# Multilingual source-grounding regression fixtures

These eight automated tests use three original synthetic records in English,
Hindi and Gujarati. They are not Agama texts, certified translations, saved
model results, expert annotations or evidence of general Jain reasoning.

The fixtures exercise the existing offline saved-answer evaluator across all
nine source/answer language pairs. A response can use a different language,
but its citation must preserve the admitted original excerpt. Substituting a
translation, changing a full quotation's negation, or changing a canonically
equivalent Unicode spelling does not establish an exact-text match. The test
also keeps missing Gujarati output in the denominator and rejects review
annotations after source-language, question or passage changes.

Important limitation: a short exact substring can omit the source's negation
and still pass mechanical matching. The fixture deliberately demonstrates this
with contradictory answers. Mechanical acceptance never becomes semantic
verification, reviewed support or runtime admission. A qualified human must
assess whether the source actually supports the answer, including context and
translation accuracy. These fixtures do not train or execute a model.

Run:

```sh
PYTHONPATH=src python -m unittest discover -s tests -p test_multilingual_source_grounding.py -v
```

Local validation, 2026-11-13: eight focused tests passed. Full suite on the
saved-answer-evaluator baseline ran 829 tests, with 775 passed and 54 optional
tests skipped. This is evaluator regression coverage, not model evaluation.
