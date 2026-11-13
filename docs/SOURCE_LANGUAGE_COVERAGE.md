# Declared source-language coverage

`evaluate_source_language_coverage` aggregates the offline saved-answer evaluator by declared source language. Missing outputs remain in each denominator. English, Gujarati, Hindi and Prakrit have stable buckets, alongside other, mixed, none and undeclared. Missing language declarations are not claimed as English. Arbitrary language labels and source/answer/reviewer text are not echoed.

All evaluator validation and review binding checks run first. Supported annotations remain unverified assertions. No language detection, translation-quality judgment, trained model, private corpus, scholarly validation or runtime/training admission is performed. Invented test fixtures only.

Six focused tests passed on Dot Linux. Full regression and independent review of this new increment remain outstanding. Feature checkpoint only, not a main merge or deployment.

Run: `PYTHONPATH=src python -m unittest discover -s tests -p test_source_language_coverage.py -v`
