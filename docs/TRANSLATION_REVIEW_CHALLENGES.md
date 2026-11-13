# Translation review regression challenges

Four source-only synthetic tests exercise Gujarati, Hindi and English authored strings. No Jain corpus, trained model or certified translation is included. They verify translated answer changes invalidate reviews, source metadata is bound, supported labels grant no runtime/semantic authority, and reports omit private text/reviewer labels.

Run: `PYTHONPATH=src python -m unittest discover -s tests -p test_translation_review_binding.py -v`

The evaluator and challenge have been integrated onto main baseline aba465e in this candidate only. They do not admit a corpus, execute a model or establish scholarly correctness.
