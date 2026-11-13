# Synthetic translation-review challenges

Four regression tests exercise Gujarati, Hindi and English authored strings. No Jain texts or certified translations are included. They verify stale output and source metadata invalidate review bindings, supported annotations do not establish semantic truth or runtime authority, and summaries omit source/answer/reviewer text.

Run: `PYTHONPATH=src python -m unittest discover -s tests -p test_translation_review_binding.py -v`

Observed 2026-11-13: four tests passed against the exact evaluator source at e4398ee7696210985fafbed1272a5ad11bff36a8. No full-suite run for this checkpoint, model evaluation, training, native qualification or deployment. The evaluator is not present on main aba465e, so integration remains separate. Review assertions are synthetic and do not authenticate reviewers or scholarly correctness.
