# Verified pending source-review queue

The fresh source-study request accepts operation `review_queue` with exact pins,
declaration, explicit offset and limit (1–8). Confirmation, local disclosure and
noncandidate-review permission are all required, even though items contain only
metadata. A request cannot include text search, layer filters, selections or
context options. Every invocation uses the existing full pinned-source
re-extraction and descriptor snapshot checks, including known conservative
ancestor-directory refusals. There is no auto-retry or weakened verification.

The queue identifies selected prerequisites previously available only in a
private research helper: incomplete/unrecognized citation identifiers and records
labelled as quotations. Entries retain source record IDs, paths, hashes, containing
IDs and inherited language labels. They request edition/citation review and,
for quotations, language, speaker/source and relation-to-commentary review.
Inherited language and categories are not scholarly determinations. Metadata can
itself be private and must not be treated as automatically publishable.

No parsed source passages or parts are returned. Existing source notices remain
attached and may contain attribution prose. All entries are pending, reviewer and
evidence unset, and all admission flags unchanged. This is NOT a decision-import
format, expert authentication, rights grant, model prompt or training input.

The queue is not an exhaustive review checklist: a record absent from it is not
verified or safe for training. Original-text, translation, doctrinal and rights
review remain necessary independently. Pagination applies only to this flagged
subset; counts are not counts of Agamas, verses or distinct scholarly problems.

Tests use invented fixtures; real-source, browser and model qualification are
not claimed. Earlier snapshot and private-source failures remain unresolved.

Initial focused tests failed because the first implementation accidentally also
entered the browse-output branch, replacing the queue count and including source
records. The branch condition was corrected before publication; the metadata-only
regression assertion now checks that no records or synthetic passages escape.
The failed run is retained, not counted as a pass.

Corrected validation: seven focused tests passed; independent sequential full
suite passed 973 tests in 69.751 seconds with 54 optional skips. Independent review
found no remaining passage leak or consent bypass in the scoped change.
