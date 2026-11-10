# Scoped unary support: final v1 implementation contract

Contract identifier: `scoped_unary_contract_v1`.
Proposed candidate identifier: `scoped_unary_v1`.
Status: reconciled design specification, 2026-11-10. No implementation, oracle, test run, or fresh evaluation is established by this document.

This standalone contract fixes the minimal design for a new offline candidate. It does not amend any frozen evaluator, candidate, historical prediction, dataset, broader prose annotation policy, corpus policy, or runtime. Its output is bounded local contextual support in an exact formal language. It does not establish source accuracy, real-world truth, ordinary-English understanding, or production readiness.

The selected defaults are: component-local conflict handling; completeness of one exact source/version/extent across all frames; stipulated shared object, predicate, and frame identifiers; atomic assertion queries; and proposition-specific truth bridges for both directly reported facts and rules. There are no unresolved semantic options to choose incidentally during implementation.

## 1. Input envelope and request validation

### 1.1 File transport and JSON

The offline input is one UTF-8 JSON file. Preserve the frozen evaluator's input-reading behavior:

- Use nonblocking file inspection; if that platform capability is unavailable, fail the request.
- After opening, require the descriptor to identify a regular file of at most 2,097,152 bytes. Read at most that limit plus one byte and reject an actual read exceeding the limit. A path resolving to a regular file is eligible; this contract adds no new symlink rule.
- Reject invalid UTF-8, invalid JSON, duplicate JSON object keys at any depth, non-finite JSON constants, excessive parser recursion, or a transport/read error. Do not read a pipe/device as ordinary input.
- No input is executable. No network, model, corpus, or external source lookup is part of interpretation.

Malformed transport/envelope input fails the whole invocation before any case is classified. A case is not silently dropped because its envelope is invalid.

### 1.2 Exact envelope shape

The root object has exactly these keys:

```
protocol, dataset_sha256, input_sha256, cases
```

`protocol` is the integer 1, not a Boolean. Each hash is a string of exactly 64 lowercase hexadecimal characters. `cases` is an array of one through 64 case objects. Each case has exactly:

```
id, passages, claim, citations
```

Case IDs are unique throughout the invocation. Each passage has exactly `id,text`; passage IDs are unique within their case. Each citation has exactly `passage_id,quote`.

Envelope limits and validation:

- `passages`: one through five entries per case.
- `citations`: one through five entries per case, not an optional empty list.
- `claim`: at most 2,000 Unicode code points.
- Passage `text`: at most 8,000 Unicode code points.
- Citation `quote`: at most 1,000 Unicode code points.
- Every such text is a string with nonempty content after the frozen validator's Unicode whitespace stripping, and contains no character whose Unicode general category starts with `C`. This rejects controls, surrogates, format/private-use/unassigned characters under that validator's Unicode database, not just ASCII control characters. Grammar imposes further restrictions below.
- Every envelope ID is a nonempty ASCII string of at most 64 characters, using only letters, digits, `-`, `_`, `.`, and `:`. This envelope identifier syntax is separate from the formal-language identifier syntax.
- Every citation references an existing passage ID and is an exact, nonempty substring of that passage text. A `(passage_id,quote)` pair cannot repeat. Citations do not choose which text is parsed or which premises are available.

No gold label, rationale, group, phenomenon, or other extra key is accepted. `dataset_sha256` is a binding supplied by the exporter; it does not require opening the dataset and is not a certificate of author independence or correctness.

Define canonical JSON bytes as the frozen evaluator's `canonical_bytes`: UTF-8 encoding of JSON with non-ASCII escaping disabled, keys sorted, separators `,` and `:`, and non-finite values forbidden. Array order is preserved. `input_sha256` must equal SHA-256 of those bytes for the root object restricted to `protocol,dataset_sha256,cases`. Verify the whole envelope and this binding before semantic parsing. Input case order is retained for outputs; the candidate does not reshuffle cases.

The frozen validator is the compatibility reference for transport, Unicode text validity, and canonicalization. Independent semantic implementations must not import each other's parser or scope logic. This contract does not require changing the frozen validator.

## 2. Exact formal language

The following are grammar templates, not evaluation cases. Metavariables are not literal input.

```
fact     := Object E is P
          | Object E is not P

rule     := Every P object is Q
          | Every P object is not Q
          | No P object is Q

body     := fact | rule
key      := source/version/extent
ref      := key#entry

premise  := World frame: body.
          | Report ref frame: body.
          | True ref.
          | Complete key.

claim    := World frame: fact.
          | Asserts key frame: fact.
          | Not-asserts key frame: fact.
          | Account [key-list] frame: fact.

key-list := key | key,key-list
```

Token bounds, using ASCII regular-expression notation:

- Entity `E`: `[A-Z][a-z]{0,31}`.
- Properties `P,Q`: `[a-z]{1,24}`, excluding exactly `object,is,not,every,no`.
- Source, version, extent, entry, and frame: `[a-z][a-z0-9_]{0,15}`.

Identifiers are case-sensitive. There is no Unicode normalization, escape decoding beyond JSON decoding, semantic interpretation of identifier names, or extra synonym. Internal ASCII spaces and punctuation must be exactly as shown. Account lists contain one through four distinct full keys, with no spaces around commas. Too many keys or a duplicate key is unsupported claim grammar, not a later symbol-limit failure. Source-list order has no semantic effect and is normalized by sorting.

Each passage is one or more premises. A claim is exactly one claim statement, with an atomic fact body. A passage cannot contain a claim-only constructor. A claim cannot be a rule, Report, True, Complete, or a sequence of claims. Bare unscoped bodies are unsupported.

Only ASCII spaces outside a complete statement, including before its first character and after its terminating period, are insignificant. Zero spaces between consecutive complete statements are permitted. The period belongs to the statement and must immediately follow its final token; a space immediately before the period is unsupported in both passage premises and claims. Empty statements, extra periods, missing terminal periods, nonempty tails, and other whitespace normalization are unsupported.

### Deterministic passage parsing

Scan each passage left to right. A completed segment consists of the characters after the preceding period, or from the start of the passage, up to and including the next period. Trim only outer ASCII spaces from this period-inclusive segment, then require the resulting entire string to match one complete premise, including its final period. A space immediately before the period is internal and must not be trimmed. The first empty or unrecognized statement fails at its one-based statement index. After the last period, any non-ASCII-space remainder fails as the next statement, including an unterminated otherwise recognizable premise. A passage with no completed statement fails at statement 1. This order ensures an earlier malformed statement is not hidden by a later unterminated tail.

For the claim, first trim only outer ASCII spaces from the entire claim text, retaining the period. The resulting entire string must match exactly one complete claim, including its final period. A space immediately before that period is internal and must not be trimmed. Any failure has the single reason `unsupported_claim_grammar`; no subsidiary claim error precedence is exposed.

Consume all supplied passages, including uncited and ultimately unselected material. No prefix-only interpretation, ignored suffix, or inference from a filename, citation choice, case ID, rationale, or private metadata is allowed.

## 3. Canonical records and identities

### 3.1 Shared identifiers

Entity identifiers name stipulated shared objects across all records; different identifiers denote different objects. Predicate identifiers have shared meanings across sources and frames. A frame identifies one stipulated situation; different frames have no inferred temporal order, duration, persistence, or inclusion. Identical identifiers provide explicit formal identity, not a guessed natural-language link.

Rules apply to every case entity in their selected frame, including an object mentioned only by the claim. There is no source-local object domain or source-local predicate meaning.

A source key is the exact tuple `(source,version,extent)`, canonically written with `/` separators. Every component must match. No token, including `whole`, has special meaning. There is no extent hierarchy, version ordering, source alias, or bridge inheritance. A reference is `(key,entry)`, canonically `key#entry`; frame is not part of the reference identity.

### 3.2 Normalized body tuples

Use these typed tuples, with Boolean polarity:

```
["fact", entity, predicate, positive]
["rule", antecedent, consequent, consequent_positive]
```

`No P object is Q` and `Every P object is not Q` normalize to the same negative rule tuple. This is the only syntax alias. Reference payload equality compares `(frame,normalized body)` exactly.

Do not normalize theorem-equivalent formulas, reorder a negative rule's endpoints, remove a self-rule, or merge predicates for reference identity. Reversing an exclusion's endpoints changes its payload even though its classical constraint can be equivalent. A positive self-rule is a tautology; a negative self-rule can force a negative fact. Both retain their predicate vertex and record identity.

Retain every raw occurrence, position, and spelling for provenance and limits. Deduplication cannot reduce raw statement counts.

### 3.3 Premise interpretation

- **World:** stipulates its body in its stated world's frame.
- **Report:** stipulates direct source content and makes its body available in that exact source-key/frame account. It does not add the body to the world.
- **True:** a narrator-level guarantee of exactly one referenced Report body's truth at that Report's frame. Both fact and rule bodies can be promoted. The reference must resolve to supplied unambiguous content. No other entry, neighboring proposition, whole source, or different version is guaranteed. No reverse import into an account occurs.
- **Complete:** closes direct assertion membership for exactly one full source key, across all frames, against the union of all its supplied Report records. It does not guarantee content truth, close world/account predicates, or negate an omitted proposition.

A repeated reference is permitted only when every occurrence has identical frame and normalized body. It adds no logical strength, even if the declared rule alias changes raw wording. A different payload for the same reference invalidates the entire case, regardless of query relevance. Distinct references may repeat or disagree in content without a reference-identity error.

True may precede Report in input order. A dangling True reference invalidates the case rather than behaving like an inactive conditional. A report cannot contain True, Complete, another report, or an inferred-conclusion reference because these are not bodies in the grammar.

Complete is evaluated on the assembled case, not sequentially. Adding a Report record to a complete source changes its closed content snapshot; an earlier absence is not stored as an independent negative premise. Do not promise monotonic assertion-absence answers under that edit. A Complete key with no reports has empty closed content, including at a query-only frame. A complete excerpt does not close another extent or version.

## 4. Counts, limits, and primary-reason precedence

After the whole envelope passes, process each case by the following stages. The first failing stage determines the primary reason and no later reason replaces it.

1. Parse the claim. Failure: `unsupported_claim_grammar`.
2. Parse passages in their supplied array order and statements in their left-to-right order. First failure: `unsupported_passage_grammar`, with one-based passage index, passage ID, and statement index. This happens before resource counts, even when a parsed prefix is already large.
3. Count raw passage premise statements. More than 64: `statement_limit`.
4. Count all identifiers from every parsed premise and the parsed claim. More than eight entities, ten properties, four frames, or four full source keys: `symbol_limit`. Report all exceeded dimensions, ordered `entities,properties,frames,source_keys`.
5. Count distinct references in the union of all Report and True occurrences, including dangling True references. More than 32: `reference_limit`.
6. Find every reference with conflicting normalized payloads. If any: `conflicting_report_reference`, listing all such full references in ASCII lexicographic order.
7. Find every True reference with no Report occurrence. If any: `unresolved_truth_reference`, listing all such full references in ASCII lexicographic order.
8. Evaluate the query and perform the mandatory diagnostics in sections 5–6. A target inconsistency may produce `relevant_inconsistent_context`; unrelated inconsistencies do not change the query result.

Distinct entity/property/frame counts include query-only identifiers, all valid parsed body positions, and conflicting payloads even though those conflicts are checked later. Full key counts include keys in Report, True, Complete, Asserts, Not-asserts, and every Account list. References are full `key#entry` strings, not just entry tokens, and not `(key,frame,entry)` triples. Token counts in the envelope, citation quotes, IDs, and raw prose substrings are not semantic symbol counts. The same lexical string in two token namespaces is counted independently in those namespaces. Every duplicate World, Report, True, or Complete occurrence still counts as a raw statement. The claim is excluded from that statement count but included in all relevant symbol counts.

All identifier inventories are sets of canonical strings. No source is fetched to resolve a reference. Whole-case integrity validation before relevance is deliberate: an invalid unselected reference abstains, whereas a valid unselected contradiction merely appears in diagnostics.

Stages 1–7 produce case-level abstention, never an invented semantic label or whole-request envelope error. No diagnostic consistency claim is made for a case rejected at these stages.

## 5. Query semantics

### 5.1 Direct assertion membership

For `Asserts K F: l`, let A mean at least one Report record has exactly key K, frame F, and normalized atomic fact l as its body. Let C mean at least one Complete K premise occurs.

- If A: `supported`.
- Else if C: `contradicted`.
- Else: `not_established`.

`Not-asserts` exchanges supported and contradicted, preserving not-established. Its outer negation concerns the reporting relation, not the literal inside the report.

Rules, derived consequences, the opposite signed fact, and content in another version/extent/frame do not establish direct membership. Both P and not-P can be directly asserted. Completeness never overrides a present report. An account can entail a proposition absent as a direct assertion; if its content is complete, the assertion query is then contradicted while the account query can be supported.

Membership queries do not abstain because an account or world theory is inconsistent. They still run the mandatory diagnostic inventory after successful integrity validation. There is no general paraphrase recognition or rule-assertion query in v1.

### 5.2 Effective logical theories

For World at F, select all World bodies at F plus the bodies at F of all Report entries individually referenced by True. For Account at F and source-key set S, select all Report bodies at F whose key is in S, and nothing else. Account selection imports no World fact, True marker, completeness-based negative, or unselected source.

The Account query classifies the signed atomic proposition under the selected account premises. It is not a Boolean meta-claim that “P is provable.” Lack of entailment alone is not contradiction; entailment of the opposite signed proposition is.

Facts assign Boolean properties to objects. Positive rules are material implications P → Q; negative rules are P → not-Q. Contraposition and vacuity apply. There is no converse, existential import, common-sense premise, or closed-world default.

### 5.3 Dependency graph and target component

For an effective theory, construct an undirected graph with the predicates mentioned in its selected bodies plus the query predicate. Each selected rule connects its antecedent and consequent; retain reflexive vertices and the rule itself. Facts add predicate vertices but no edges. A predicate not mentioned in the theory remains an isolated query vertex.

Let C be the component containing the query predicate and e the query object. T contains every selected rule whose endpoints are in C, grounded for e, and every selected fact about e whose predicate is in C. All such constraints participate; no inconvenient premise or conflict is selectively discarded. Repeated identical normalized body tuples may be stored once with complete provenance. Distinct tuples are retained even when their Boolean constraints are equivalent.

- If T has no Boolean valuation, return `abstain` with `relevant_inconsistent_context`.
- Otherwise return `supported` if every T valuation satisfies the signed query.
- Return `contradicted` if every T valuation falsifies it.
- Return `not_established` if both satisfying polarities occur.

Positive and negative queries use the same T. The sign affects satisfaction of the query, not graph construction or source selection.

This is classical checking within a **non-classical claim-local inconsistency policy**. It is not classical entailment from a globally inconsistent conjunction. A disconnected conflict cannot cause explosion or suppress the local answer. A connecting rule can make a previously disconnected conflict relevant and cause abstention even when that rule is logically redundant given another fact. This syntactic relevance policy is intentional; general logical-equivalence invariance is not promised. No repair, maximal-consistent-subset search, trust ranking, or finer semantic relevance mechanism is authorized.

### 5.4 Witness scope and deterministic witness selection

Every logical witness is only for `(selected scope, frame, query object, target component)`. A witness is a Boolean array in ASCII-sorted component-predicate order. For each query polarity that is possible, return the lexicographically smallest satisfying Boolean vector, with false less than true. The first predicate is the first comparison coordinate. Impossible polarities have null witnesses.

`true_possible` means some T valuation satisfies the signed query; `false_possible` means some T valuation falsifies it. For inconsistent T, both are false and both witnesses are null. For unknown, both are true and both witnesses are required.

A favorable witness does not prove entailment. Support/contradiction requires complete absence of the opposite kind of model. Independent exhaustive checking of T is sufficient for v1; no bespoke proof-certificate language is required. No model-count field is required.

Do not call these witnesses countermodels/models of the entire supplied context. Even when the selected theory is consistent, the returned arrays cover only the target component, not the other components or objects. A whole-selected-theory model claim would require constructing and checking that larger model separately; this trace does not return one.

## 6. Mandatory diagnostic inventory and exact coverage

After stages 1–7 pass, every query family must perform a complete bounded consistency scan. It cannot be optional, truncated, or limited to the query object.

Build this set of scope descriptors:

1. `["world",F]` for every frame occurring in a World record, a Report record, or the claim. Report frames are included even when their effective world theory is empty.
2. `["account",[K],F]` for every exact source-key/frame pair occurring in Report, and for each query key at the query frame in Asserts, Not-asserts, or Account.
3. `["account",sorted-query-keys,F]` for the Account query itself. A singleton is the same descriptor as item 2 and is scanned once.

Complete-only keys cause no extra frame scan unless their key/frame is selected by the query or occurs in Report. True contributes its resolved Report frame already covered above. No Cartesian product of all keys and all frames is implicitly scanned. No unqueried multi-source union is scanned.

For each descriptor, materialize the effective theory by section 5.2. Build its graph from its selected-body predicates plus the case's query predicate, using section 5.3. This makes a query-only predicate an explicit isolated component even in an empty inventory theory. For **every case entity identifier**, including claim-only entities and entities from other scopes, test consistency of every graph component with all applicable rules and that entity's local facts.

Report all components, their predicate sets, and exactly which entities are inconsistent in each. An empty inconsistent-entity list means that component was checked and found consistent for every case entity, not skipped. A theory's `consistent` flag is true exactly when all those lists are empty. `scan_complete:true` means every declared inventory/entity/component combination was checked. It does not certify an unlisted union or any outside source.

Diagnostics never replace the selected query's result. In particular, membership can be supported while its account is inconsistent, and a world/component query can be supported while another inventory theory or disconnected selected component is inconsistent.

Inventory order is deterministic: world descriptors first by frame; then account descriptors by their sorted key-list tuple, breaking ties by frame. Each component's predicates are sorted; components are ordered by their smallest predicate. Entity lists are sorted. With four frames and four keys there are at most four world descriptors, sixteen individual account descriptors, and one extra queried union. All graphs have at most ten predicates and there are at most eight entities. This is a finite diagnostic inventory, not an open-ended search for every contradictory source combination.

## 7. Output and trace contract

### 7.1 Predictions

Preserve the frozen prediction schema exactly:

```
{
  "protocol": 1,
  "input_sha256": <input binding>,
  "predictions": [
    {"case_id": <ID>, "label": <label>}
  ]
}
```

There is exactly one row per input case, in input order. Labels are `supported`, `contradicted`, `not_established`, or `abstain` only. Reasons and diagnostics belong in the separate trace, not new prediction keys.

### 7.2 Trace top level

The trace is a JSON object with exactly:

```
trace_protocol, candidate, contract, bindings, cases
```

Values: `trace_protocol` is 1; `candidate` is `scoped_unary_v1`; `contract` is `scoped_unary_contract_v1`. `bindings` has exactly:

```
candidate_source_sha256, evaluator_source_sha256, contract_sha256,
input_sha256, dataset_sha256, prediction_sha256
```

The source hashes bind the new single-file candidate and unchanged evaluator file actually used. The contract hash is SHA-256 of this complete contract file's exact UTF-8 bytes; it is computed externally, not embedded into this file. The prediction hash is SHA-256 of canonical prediction JSON bytes. Input/dataset hashes are copied from the validated input. If a future implementation adds semantic helper files, that requires a revised binding schema before freezing; the single-file binding must not conceal unbound semantic dependencies.

All trace ordering below is normative. No timestamps, host paths, timings, random IDs, free-form prose, optional diagnostic extras, or implementation-specific proof objects are included. Exact source hashes naturally differ between independent implementations; semantic comparisons must not mistake that binding difference for a label disagreement.

### 7.3 Case rows and presemantic failures

Each trace case has exactly:

```
case_id, label, reason, details, query, counts, symbols,
records, references, diagnostics, evaluation
```

For stages 1–7 failures: label is `abstain`; reason is the specified code; `query,counts,symbols,records,references,diagnostics,evaluation` are null. `details` is exactly:

- Claim grammar: `{}`.
- Passage grammar: `{"passage_index":i,"passage_id":id,"statement_index":j}`.
- Statement limit: `{"statement_count":n,"maximum":64}`.
- Symbol limit: `{"counts":{"entities":n,"properties":n,"frames":n,"source_keys":n},"exceeded":[dimension names]}`. Include all four counts, with exceeded dimensions in section 4 order.
- Reference limit: `{"reference_count":n,"maximum":32}`.
- Conflicting reference: `{"references":[sorted conflicting refs]}`.
- Unresolved truth reference: `{"references":[sorted dangling refs]}`.

These nulls mean semantic evaluation/diagnostic coverage is unavailable. A partial parsed prefix must not masquerade as a fully parsed case.

For cases reaching stage 8: `details` is `{}`; all other fields are populated as below. Reason is `direct_assertion_membership` for either assertion-query family, `complete_component_check` for a non-abstained World/Account result, and `relevant_inconsistent_context` for an inconsistent target. Diagnostics are still complete for the latter.

### 7.4 Normalized query, symbols, records, and references

Normalized query tuples:

```
["world", frame, fact-tuple]
["asserts", key, frame, fact-tuple]
["not_asserts", key, frame, fact-tuple]
["account", sorted-distinct-key-list, frame, fact-tuple]
```

`counts` has exactly `statements,entities,properties,frames,source_keys,references`, all integer counts defined in section 4. `symbols` has exactly `entities,properties,frames,source_keys,references`, each the corresponding ASCII-sorted distinct string list.

`records` preserves every passage premise occurrence in passage/statement order. Each record has exactly:

```
ordinal, passage_index, passage_id, statement_index, text, node
```

Indices and `ordinal` are one-based; ordinal runs continuously across passages. `text` is obtained from an accepted period-inclusive completed segment by first trimming only outer ASCII spaces and then removing exactly its final period. Do not trim again after removing the period. Preserve every remaining character, including the raw alias spelling. `node` is one of:

```
["world", frame, body-tuple]
["report", ref, frame, body-tuple]
["true", ref]
["complete", key]
```

`references` is an array in full-reference lexicographic order. Each element has exactly `ref,frame,body,report_ordinals,true_ordinals`. `body` is normalized; each ordinal list contains all corresponding raw occurrences in ascending order. Every reference in this array has at least one Report occurrence because resolution already succeeded. Aliased repeated payloads remain multiple report ordinals for the same resolved entry.

### 7.5 Diagnostic trace and admitted-premise provenance

`diagnostics` has exactly `entity_universe,query_predicate,scan_complete,inventory`. Entity universe is the sorted complete case entity set; scan_complete is true. Inventory ordering is fixed by section 6.

Each inventory entry has exactly `scope,admissions,components,consistent`:

- `scope`: its exact descriptor from section 6.
- `admissions`: every admitted raw premise contribution, not just one convenient derivation. World admissions are `["world",world-record-ordinal]` and `["bridge",true-record-ordinal,ref]`. The latter resolves through the reference table to its exact body/frame and all original Report positions. Account admissions are `["report",report-record-ordinal]`. Every applicable raw World, True, or Report occurrence appears once as appropriate, sorted by its ordinal. No Complete record is a logical admission. Repeated body meanings do not lose their provenance.
- `components`: the complete ordered component list. Each entry has exactly `predicates,inconsistent_entities`, both sorted lists under section 6. Every entity was checked even when absent from inconsistent_entities.
- `consistent`: Boolean, true precisely when all component inconsistent-entity lists are empty.

Admissions plus the record/reference tables reconstruct every selected constraint without repeating an entire parsed theory for each entity. A bridge's True position and original Report positions are separately recoverable; a source rule is not justified by a nearby world fact or another entry's bridge.

### 7.6 Query evaluation trace

For either assertion family, `evaluation` has exactly:

```
kind, key, frame, fact, outer_negated,
matching_report_ordinals, complete_ordinals, present, complete
```

`kind` is `assertion`; `fact` is its normalized fact tuple; outer_negated is true only for Not-asserts. Matching report ordinals are all direct exact atomic matches, sorted. Complete ordinals are all Complete occurrences for this exact key, sorted. `present` and `complete` are their respective nonempty-list flags. No solver witness is substituted for membership.

For World or Account, `evaluation` has exactly:

```
kind, scope, entity, component, target_constraints,
satisfiable, true_possible, false_possible, true_witness, false_witness
```

`kind` is `logic`. `scope` matches one diagnostic inventory descriptor. `component` is the sorted target predicate list. `target_constraints` contains every distinct normalized body selected into T by section 5.3, in lexicographic order of each body's canonical JSON byte encoding; rules remain rule tuples to be grounded for the listed entity. Admissions provide all provenance, including duplicates. The flags and witness arrays obey section 5.4. An inconsistent target has satisfiable false, both possibility flags false, and both witnesses null. No unrelated inconsistency may be silently removed from diagnostic coverage.

## 8. Serialization, size limits, and operational failures

The trace cap is exactly 2,097,152 bytes of canonical trace JSON, excluding its terminal output newline. It is an invocation-wide cap, not a per-case budget. The schema fixes what must be serialized; no truncation, omitted conflicts, dropped provenance, reduced diagnostics, witness suppression, or changed label is permitted to fit it.

Both operations conceptually produce the complete predictions and trace before publishing either. If canonical trace bytes exceed the cap, fail the **whole request** with `trace_overflow`. This applies even to prediction-only output; do not return predictions whose required inspection artifact cannot be produced. Valid bounded mathematical input is therefore not a promise that every maximum-size batch can be packaged under the trace cap. This explicit operational failure is the selected alternative to an unverified worst-case-fit claim.

On success, `predict` writes canonical prediction JSON followed by one LF; `inspect` writes canonical trace JSON followed by one LF. Success exit status is 0. Neither operation writes other files or changes input. Canonical output is deterministic for fixed inputs, source/contract bindings, and the evaluator-compatible runtime, including its Unicode database. Do not stream partial result rows before validation and size checks complete.

On request failure, stdout is empty, exit status is 2, and stderr is one canonical JSON object followed by one LF:

```
{"error":"invalid_input"}
{"error":"trace_overflow"}
{"error":"execution_failure"}
```

These are alternative single objects, not three simultaneous lines. `invalid_input` covers file/JSON/envelope/hash failures. `trace_overflow` is used only after valid input and construction of the required trace show it exceeds the cap. `execution_failure` covers an inability to complete computation or bind required source/contract artifacts; it must not be disguised as a semantic abstention. A host-level forced termination may prevent this diagnostic and must not be represented as a successful request.

All request-level input validation precedes case semantics and trace overflow checking. The primary case reason does not replace a whole-request transport/packaging failure. No partially accepted invocation is implied. A caller may explicitly prepare smaller valid batches with their own correct input hashes; the candidate does not silently repartition the request or retain an old hash for altered input.

## 9. Independent oracle and validation obligations

A separately written oracle must implement this contract independently: parser, normalization, symbol/reference counting, error stages, resolution, membership, scope selection, dependency components, diagnostics, and witness selection. It must not reuse candidate semantic helpers or the frozen candidate's solver while claiming independence.

The candidate may use 2-SAT. The oracle may enumerate every valuation in each at-most-ten-predicate local component, at most 1,024 per check. It must compare primary reasons, admitted constraints/provenance, all declared diagnostic scope, and witnesses as well as final labels. A complete per-input oracle is distinct from exhaustive testing of every possible input string or bounded theory.

Support and contradiction require an independent absence-of-countervaluation check, not acceptance of one favorable witness. Unknown requires both verified target-component witnesses. A full selected-theory inconsistency does not invalidate a local witness; it invalidates any claim that that local witness is a model of the whole selected theory.

Before authoring hidden cases, freeze implementation, oracle, contract/output schema, and packaging behavior; validate them, then arrange an author-blind fresh test with a clean standalone specification. This document contains no authored cases, no executed test result, and no promise that the future implementation will pass. Published review sketches are development material, never held-out evidence.

## 10. Exclusions and claim limits

No natural-language translation, arbitrary quotation interpretation, rule-assertion queries, conjunction/disjunction claims, nested reports/beliefs, aliases, equality, binary relations, source-local meanings, trust ranking, probabilities, defeasible reasoning, chronology, intervals, persistence, physical geography, inventory arithmetic, counts, source verification, licensing/admission inference, or outside factual knowledge is included. Unsupported material abstains under the exact grammar, even if a human could understand it.

The capability under study is composition of explicit provenance and scope with bounded unary deduction and local countervaluation checking. Assertion lookup alone is not evidence of expanded reasoning. Even perfect finite results would not establish ordinary-English support, true sources, Jain scholarship, corpus admission, neural improvement, or a safe production gate.
