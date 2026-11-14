# Focus study on an explicit source layer

Fresh search and browse requests may include optional `category`, an exact
markup-derived label. Allowed values: root_text_label, commentary_label,
quotation_markup, note_markup, heading_markup, verse_group_markup,
trailer_markup, unclassified_paragraph, list_item_markup. Omit it for the existing
unfiltered behavior. Explicit null, unknown names and other types are refused.
Lookup, selection and inventory do not accept it.

Root/commentary filters still include only literal candidates by default. Any
other category requires explicit `--review-noncandidates`; without that consent
the request refuses rather than showing an empty result that might imply the
source has no quotations or notes. With review permission, noncandidate records
may be inspected but do not become validated, admitted or safe for training.

Filtering precedes matching and pagination. Counts and offsets refer to the
filtered scope; use the same pins, category, query and review permission for
successive pages. Search locations describe only those page records. Changing
scope does not make an old offset a valid cross-scope cursor. Results disclose
the effective category and label semantics explicitly.

Categories are extraction labels, not proof of authorship, doctrinal authority,
quotation identity or scholarly interpretation. Source text, notices and all
false admission flags remain unchanged. The full exact-source verifier, consent
and complete-output limits remain in force. No new corpus, model or provider
is included. A large page may still exceed output limits and refuse as a whole.

Validation uses invented fixtures only. Initial invocation from the wrong
working directory found no test directory; the corrected focused run passed
seven tests. Prior private-source intermittent failures remain unresolved and
were not retried by this feature.

During concurrent validation, the81-test independent focused run failed with six
snapshot-mutation errors. The simultaneous952-test full run also failed with six
snapshot-mutation errors (54optional skips), in existing source-study tests.
Those failures are retained, not counted as passes. A controlled sequential
synthetic diagnostic showed that creating an unrelated sibling directory causes
the existing ancestor-snapshot guard to refuse while bundle bytes remain
unchanged; its no-mutation control passed. This demonstrates a mechanism, not a
definitive diagnosis of those concurrent errors or prior private-source failures.
No guard was relaxed and no automatic retry was added.

One separately authorized independent non-concurrent full run then passed952tests
in69.731seconds with54skips. This is one successful sequential qualification,
not a clean first pass, concurrent reliability, scholarly validation or model
quality claim. The independent reviewer found no category-gate/scope bypass.
