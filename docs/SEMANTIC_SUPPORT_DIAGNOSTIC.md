# Citation matching is not semantic support

Run `python scripts/evaluate_semantic_support.py` to inspect the current citation
validator against fourteen original fictional English cases. It prints actual
answers, matched citations, rendered qualifications and aggregate observations.
It never calls a model or loads a religious/runtime corpus. Exit zero means the
diagnostic executed, not that semantic reasoning passed.

Fixture-author labels use the complete supplied passages:

- **Supported:** the supplied fictional facts support the answer.
- **Contradicted:** an explicit fictional fact is incompatible with the answer.
- **Not-established:** neither the answer nor its negation is established.

The cases cover an exact substring with its negation omitted, changed counts,
some versus all, time and location, conditional rules, speaker attribution, and
an unsupported link between separate sources. Five supported controls retain
correct negation, quantity, conditional consequence, attribution or conjunction.
The conditions are stipulated fictional rules, not real-world causal advice.

On initial execution, all fourteen outputs were mechanically accepted: five
supported, six contradicted and three not-established. This is the existing
validator's documented boundary, not a newly detected failure to match quotes.
An exact quoted substring can still be misleading when its surrounding sentence
denies it. Two exact quotes do not establish an invented relationship between
their subjects. Unknown facts must not be converted into negative facts.

The semantic labels come from the fixture authors and review, not from JACE.
This hand-authored set is not representative, an unseen holdout, or a model
accuracy benchmark. Tests verify observation/reporting integrity and allow future
validator rejections; they do not require unsupported answers to remain accepted.
The separate source-first local response route abstains from deriving a doctrinal
answer. It does not add semantic validation to an external model's generated text.

No corpus admission, model training, source rights clearance, scholarly review or
doctrinal qualification follows from either the fixtures or this diagnostic.

For a separate, broader original-fiction evaluation surface, see
[contrastive claim-support evaluation](CLAIM_SUPPORT_EVALUATION.md). It keeps
passages and citations fixed within 48 matched claims, separates supplied class
predictions from abstention and citation validity, and reports full confusion
counts and complete-triple success. It does not add a semantic classifier or
convert this diagnostic's exposed examples into unseen holdouts.
