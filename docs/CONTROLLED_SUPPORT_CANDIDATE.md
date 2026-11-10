# Controlled-English unary-logic candidate

This repository-only candidate performs genuine but narrow model-theoretic
support checking over an explicitly limited language. It is not a trained model,
general natural-language entailment, religious reasoning or a runtime admission
gate. It uses no provider, paid service, source corpus or personal data.

## Exact fragment

A passage contains one or more of these forms, each ending with a period:

- `Object Aster is amber.`
- `Object Aster is not amber.`
- `Every amber object is warm.`
- `Every amber object is not warm.`
- `No amber object is warm.`

The claim must be exactly one positive or negative `Object` fact. Object names
are one ASCII uppercase letter followed by zero to 31 lowercase letters.
Properties are one to 24 ASCII lowercase letters, excluding `object`, `is`,
`not`, `every` and `no`. Tokens are case-sensitive. Property names are
uninterpreted: `red` does not exclude `blue` unless a supplied rule says so.
Different object names denote separate named objects. No synonyms, implicit
antonyms, pronouns, equality, numbers, times, locations, quotations, existential
statements or unstated common-sense relations are inferred.

A period separates sentences; zero or more ASCII spaces may follow it, so
adjacent sentences are accepted. Only ASCII spaces outside each sentence are
insignificant. Internal token spacing is exact. Every sentence needs its terminal period; empty sentences,
ignored suffixes and extra claim sentences are rejected as unsupported grammar.
Every full supplied passage is parsed, including uncited text. An exact short
citation never hides surrounding text. Malformed JSON, controls/surrogates,
invalid schemas or hashes fail the request rather than producing a score.

A well-formed case with unsupported grammar receives `abstain`, not
`not_established`. This distinction matters: unknown under a fully parsed theory
is different from inability to interpret the theory.

## Semantics and calculation

Facts assign unary Boolean properties to named objects. `Every P object is Q`
is the material implication P → Q; the negative form and `No P object is Q`
mean P → not-Q. This includes contraposition and vacuous truth. A rule does not
assert that any P object exists, and its converse is not assumed.

The candidate enumerates all property assignments separately for every named
object, including symbols mentioned only by the claim. This factorization is
sound only because the fragment has no cross-object relations, equality or
existential requirements. It checks all supplied facts and rules. If **any**
object has no satisfying assignment, the whole case abstains for inconsistent
context. It does not use logical explosion to support arbitrary claims.

For a consistent theory:

- `supported`: every satisfying assignment for the claim's object makes the
  claim true.
- `contradicted`: every such assignment makes the claim false.
- `not_established`: both a true-making and a false-making assignment exist.

Absent facts remain open-world unknown. The claim is never added as evidence.
The trace reports parsed statements with source positions, stable property
ordering, model counts and satisfying witnesses. A single witness is not a proof
of entailment; complete enumeration and zero countermodels provide that result
within this bounded fragment. All named objects must be consistent before a non-abstained result is returned.
An inconsistent trace identifies the first inconsistent object, whether the
consistency scan reached the final object, and which counts were computed; it
does not imply unchecked objects are consistent.

Limits: 64 cases per invocation, 48 passage statements per case before any
deduplication, eight objects and ten properties including query-only symbols.
Each object needs at most 1,024 assignments, never a joint 2^80 search. Limit
excess produces reason-coded abstention; malformed batch input fails closed.
Traces are capped at 2 MiB. There is no confidence score.

## Offline invocation

First obtain a label-free export from the separate
[claim-support evaluator](CLAIM_SUPPORT_EVALUATION.md), then run:

```sh
python scripts/predict_controlled_support.py predict --inputs candidate-inputs.json > predictions.json
python scripts/predict_controlled_support.py inspect --inputs candidate-inputs.json > trace.json
python scripts/evaluate_claim_support.py score --cases reviewed-cases.json --predictions predictions.json
```

Redirect only to local files you intend to create or replace. The scripts print
stdout/stderr and do not write files themselves. The scoring prediction format
is unchanged. Traces separately bind the exact input hash, candidate and evaluator file hashes
and canonical prediction hash. These hashes are data bindings, not proof of
trusted source facts, model identity, consent, independence or source rights.
The input-file inspection prerequisite is the evaluator's existing POSIX-style
nonblocking support. Linux is the tested environment; Windows is unqualified.

This candidate is deliberately not called from JACE's API, model-output checker,
local responses or evidence-only display. Success on freshly authored controlled
examples must not be presented as broad English, multilingual, Jain doctrinal
or learned-model capability. Published cases become disclosed regressions.

## Validation design and limits

A separate global truth-table oracle uses symbolic theories, not the candidate's
parser or factorized solver. It exhaustively checks all single- and two-statement
theories drawn from 30 possible facts/rules over two objects and three properties,
plus 128 seeded larger theories. The 593 primary theories produce 7,116 atomic
query comparisons. Targeted edge and invariance checks bring the total to 7,208,
with 154,768 full joint valuations examined and no discrepancies. Parsed nodes,
per-object model counts and all witnesses are checked as well as labels.

These are exact finite checks, not an exhaustive proof over all allowed input
sizes. Larger bounds and malformed syntax have targeted regression controls.
Renaming, statement order, duplicate facts and valid citation changes should not
change logical outcomes. Contradictions in another object or an uncited passage
must still trigger abstention.

The initial candidate was frozen before fresh challenge contents were reviewed.
A diagnostic-only revision then added complete entity lists, explicit context
consistency, accurate scan-completion flags and the evaluator dependency hash.
The final candidate was frozen again before generating and sealing predictions
on 48 independently authored in-fragment claims and 12 separate controls. No
fresh outcome was used to alter classification or grammar. The challenge author
received the exact grammar/semantics, but not candidate code or existing cases.
An additional review checks gold labels from label-free inputs without candidate
predictions. Any reported label-review agreement is separate from candidate
performance.

On the older, already disclosed 48-case broader-English challenge, this candidate
abstains on all 48: zero coverage and null accuracy among predictions. It does
not solve those ordinary-language examples. Exact-fragment results must be read
alongside that limitation, not generalized to broad semantic support.

## Recorded first evaluation

The [recorded output](../evals/controlled_support_observed.json) binds the frozen
candidate, evaluator and fixture hashes and preserves each candidate label.

- Fresh in-fragment challenge: 48/48 correct, full coverage, 16/16 complete
  matched triples, no unsupported-as-supported errors among 32 unsupported
  claims. The fixture deliberately stays within the disclosed grammar.
- Separate controls: six unsupported-grammar cases and six inconsistent-context
  cases all abstained, including contradictions outside the quoted text or
  concerning another object.
- Separate no-gold label review: agreement on all 48 challenge cases and all
  12 controls, with no remaining ambiguity flags. This validates fixture labels;
  it is not an additional set of candidate performance trials.
- Broader disclosed English challenge: 0/48 predictions, 48 abstentions. No
  broader-language accuracy is established.

These first fresh predictions were frozen before comparison with author labels;
no failed case was revised or used to tune the candidate. The now-public fixtures
are regression data for later changes. These results support a narrow logical
calculation capability only. They do not qualify ordinary user-facing reasoning,
Jain doctrine, source truth, multilingual interpretation or production deployment.
