# Complete bounded private source browsing

Fresh study now supports source-order `browse` and explicit pagination of
literal `search` results. This removes the previous first-eight-results limit
without an unbounded dump. It does not make the edition or interpretations
scholarly verified and does not admit anything to training or the engine.

Browse JSON has exactly these keys: `operation` (`browse`), `offset` (integer
starting at zero), `limit` (integer 1–8), `pins`, `declaration`. It rejects query,
XML ID and context options. Search keeps its prior exact schema and optionally
accepts an integer `offset`; omission means zero, explicit null is rejected.
Both require the same trusted six pins, source/license declaration and CLI
private-study/local-disclosure flags. Noncandidate review remains separate.

Each page verifies the full bundle and regenerates all source records before
selection. Selection follows source document order, filtered to literal-study
candidates by default; explicit review scope includes all selected units.
The `search_scope` field states that scope even for browse. All source layers,
notices, overlap relationships and false safety flags are retained.

Results contain `records`, `offset`, `total_count`, `limit`, `next_offset`, and
`truncated` (whether records remain after this page). Search also retains its
`match_count` and exact-matching description. Follow `next_offset` until null.
Offset equal to total yields an empty final page; beyond total fails. An empty
search at offset zero is valid. This enumerates prepared units, not unique
verses, sentences or independently authored passages: nested units may overlap.

Keep the same six pins, query, limit and review scope throughout a browsing
session. Offsets are not cross-edition cursors. Intentionally changing pins or
scope defines a different result set; the CLI stores no session or implicit
consent. Repeating a page is read-only and returns the same selection for those
same parameters, subject to per-invocation verification.

The existing 8 KiB request and 1 MiB complete-output bounds remain. No background
fetch, auto-pagination, query history, model request or database write occurs.
A page that exceeds output size is refused rather than partially emitted.
Source rights and terminal retention obligations continue to apply. All tests
use invented data; no corpus or held material is included in this code change.

Validation: full documented unittest suite passed 923 tests in 69.503 seconds,
with 54 optional skips. Independent review passed 52 focused tests including the
10 new browsing checks. These are source-workflow mechanics, not scholarly or
training validation; no actual corpus or native/container qualification ran.
