# Explicit comparative source reading

The local fresh-source-study CLI accepts a `select` request with exactly
`operation`, `xml_ids`, `pins` and `declaration`. `xml_ids` must contain two
through five distinct exact selected XML identifiers. Supply the same six
independently trusted pins and license/purpose declaration used for lookup.
Both private-study confirmation and local-disclosure permission remain required.

This reads all selected units from one fully verified snapshot, in caller order,
without requiring them to be adjacent. Each complete record retains its source
identity, layers, quotation metadata and false admission flags. The output says
`selection_relation: explicit_selection_not_inferred_support`. Selection is not
a judgment that the passages agree, support a claim or form a valid comparison.
It performs no translation, semantic comparison or answer generation.

Missing or ambiguous identifiers refuse the entire request. Any noncandidate
requires separate explicit review opt-in for the entire selection; no partial
results are printed. Extra query/context fields are refused. The existing 1 MiB
complete output bound, exact snapshot checks and source notices remain intact.
No sources are logged, stored, sent to a model or admitted to training/runtime.

This operation is independent of the unresolved private search/context harness
failures. It neither changes the snapshot guard nor retries a failed read.
Validation uses invented fixtures only, not a new private-corpus qualification.

Validation: 937 full-suite tests passed in 70.255 seconds, 54 optional skips.
Independent review passed 66 focused tests and six direct invalid-option/type
refusals. Initial command path error ran zero tests; corrected focused test then
exposed a fixture expecting access to a noncandidate without review. The fixture
was corrected to a candidate; no refusal guard was weakened. These preliminary
failures do not count as passes. No model, native platform or corpus qualification.
