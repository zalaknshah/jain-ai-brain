# Hindi/Gujarati compound cue guards

The local lexical guards now recognize their existing listed negative cues as
components of ASCII hyphen/underscore compounds, e.g. `नहीं-करना` or `ઝેર_આપો`.
Previously the shared retrieval tokenizer preserved those compounds as whole
terms, hiding the listed cue from these exact-term checks.

This change is deliberately asymmetric: harm checks and template exclusions
(negation, technical subjects and poetry) gain component checks; positive
scenario matching and the retrieval tokenizer remain unchanged. It does not
translate text, add model reasoning, interpret negation, or recognize arbitrary
harmful intent. Benign mentions of listed cues can be declined too. Unlisted
forms, semantic paraphrases and arbitrary adversarial spelling remain outside
this limited guard; it is not sufficient for robot safety or release qualification.

The six synthetic regression tests cover both scripts, normalized spellings,
separator repetition, component boundaries, conservative plan abstention,
unchanged positive matching, and engine refusal before invoking a reasoner or
writing learning memories. Fixtures are authored examples, not Agama material.

Run: `PYTHONPATH=src python -m unittest discover -s tests -p 'test_native_compound_guards.py' -v`

Validation on 2026-11-13: all six targeted tests passed. Full standard-library
regression ran 827 tests: 773 passed and 54 optional tests skipped. Independent
review reran the six tests and checked 14 additional ASCII/Unicode separator
cases without a blocking finding. These are synthetic local checks, not native
speaker, real-model or robotic qualification.

Main-baseline integration: the isolated three-file change was applied to
`45bf9c276fa4f501ccbd6657c6caf95d155a7545`, without the feature branch's unrelated
training/evaluation ancestors. The integrated suite ran 806 tests: 752 passed,
54 optional tests skipped. A second independent review passed all six focused
tests and 2,004 authored assertion cases covering listed cues, normalization,
separator variants and unchanged positive matching. Those counts are synthetic
regression coverage, not real-language or trained-model accuracy.
