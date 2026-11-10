# Offline scoped unary support candidate

`scripts/predict_scoped_support.py` is the standalone `scoped_unary_v1`
candidate. Its normative specification is
[SCOPED_SUPPORT_CONTRACT.md](SCOPED_SUPPORT_CONTRACT.md), contract identifier
`scoped_unary_contract_v1`. It is not integrated into the JACE runtime, corpus
admission, UI, or deployment.

## Exact scope

The formal input language has `World`, `Report`, `True`, and `Complete`
premises. Claims are atomic `World`, `Account`, `Asserts`, or `Not-asserts`
queries. Bodies are signed unary facts or the specified unary implications.
Only `No P object is Q` and `Every P object is not Q` are syntax aliases.
Identifier spelling, shared identity, punctuation, source/version/extent keys,
frames, and reference resolution have exactly the meanings in the contract.

Every passage is parsed, including uncited or unselected material. Only ASCII
spaces outside complete statements are ignored. The final period must
immediately follow the final token. This period-inclusive whitespace rule was
clarified before the implementation freeze; it is a grammar decision, not a
performance result. No natural-language translation, general paraphrase
matching, implicit bridge, source verification, external knowledge, temporal
inference, equality, binary relation, or source-local identifier mapping is
implemented.

`Report` content remains in its exact account unless that individual entry is
promoted by `True`. `Complete` closes only direct assertion membership for one
exact key across frames. It never supplies negative world/account facts.
Assertion queries inspect direct signed fact membership, not derivability.

World and account queries use classical material implication within the
query object's syntactically connected predicate component. A contradiction
there yields `abstain`; a disconnected contradiction does not. A connecting
rule can change relevance even if logically redundant. All selected local
constraints are retained, with duplicate meanings deduplicated only for
solving and every occurrence retained in provenance.

The single candidate file contains a separately written complete 2-SAT solver
using iterative strongly connected components. Each possible signed query
polarity receives the lexicographically smallest local Boolean witness,
false before true in sorted predicate order. These are target-component
witnesses, not models of the entire supplied context. Support and
contradiction require absence of the opposing polarity, not one favorable
witness.

Every semantically admitted case also scans the entire mandated inventory of
world frames, individual account/frame pairs, and the selected account union.
Every case entity is checked in every component of every listed scope.
Membership answers retain these diagnostics even if an account is
inconsistent. No other account union is implicitly certified.

## Bounds and failures

- One regular UTF-8 JSON input file, at most 2,097,152 bytes; nonblocking
  inspection is required. Pipes and devices are rejected.
- One through 64 cases, each with one through five passages and citations.
  Envelope text, identifier, citation, and binding checks match the contract.
- Per case: at most 64 raw premises, eight entities, ten properties, four
  frames, four source keys, and 32 distinct Report/True references.
- Grammar, statement, symbol, reference-count, conflicting-reference, and
  unresolved-reference failures produce case abstention in that exact order.
  Presemantic failure rows have no partial semantic trace.
- The complete invocation's canonical trace is capped at 2,097,152 bytes,
  excluding its terminal newline. Both operations build both artifacts before
  publishing. Overflow fails the whole invocation, including `predict`, with
  no truncation, silently dropped diagnostics, or automatic rebatching.

Successful output is canonical JSON and one LF, exit status 0. Request
failures have empty stdout, status 2, and exactly one canonical stderr object:
`{"error":"invalid_input"}`, `{"error":"trace_overflow"}`, or
`{"error":"execution_failure"}`, followed by one LF. No candidate output
files are written internally.

## Reproduction

Use Python 3.10 or later and the standard library. No installation, model,
network, private source, or corpus lookup is required. Run from the repository
root:

```sh
python -B scripts/predict_scoped_support.py predict --inputs /path/to/inputs.json
python -B scripts/predict_scoped_support.py inspect --inputs /path/to/inputs.json
python -B -m unittest discover -s tests -p 'test_scoped_support_candidate.py' -v
```

`--input` is an alias for `--inputs`. Input must have exactly
`protocol,dataset_sha256,input_sha256,cases`; each case has exactly
`id,passages,claim,citations`. Gold labels and metadata are forbidden. The
frozen evaluator can export an appropriately sized existing dataset:

```sh
python -B scripts/evaluate_claim_support.py export --cases /path/to/dataset.json > /path/to/inputs.json
```

The candidate accepts at most 64 exported cases and does not split a larger
export. A caller preparing another valid batch must recompute its exact input
binding. A supplied dataset hash binds bytes identified by the exporter, not
the accuracy or independence of that dataset.

Inspection binds the actual single candidate source, verified frozen
evaluator bytes, exact copied contract bytes, validated input and dataset
hashes, and canonical prediction bytes. Required fixed bindings are:

- Evaluator SHA-256:
  `f24f017ad344d572e61979519730c5fc8dbd1be162fb24d648ab66deae04ae13`
- Contract SHA-256:
  `0facb37c40a72b34dd93420453acc60def3292ee8a27fd6cef9f080a6a655e46`

The evaluator is loaded from its verified source bytes, without importing a
cached bytecode version. No old candidate parser or solver is imported. A
missing or changed required artifact fails the request rather than emitting
an unbound answer. Determinism assumes the same bindings and compatible
Python/Unicode validator behavior.

The focused test file is disclosed development material, including small
exhaustive solver checks and a real-size overflow fixture. It is not a
held-out benchmark or an independent input oracle. No fresh evaluation,
ordinary-English competence, source truth, Jain scholarship, neural
improvement, or production readiness is claimed by this candidate.
