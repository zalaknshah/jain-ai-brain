# Bounded literal search of fresh source-study units

The fresh API and fresh-source-study CLI now support `search`. This helps a
reader find units without knowing their XML IDs. It is case-sensitive Unicode
substring matching, not semantic retrieval, translation, transliteration,
normalization, a complete canon search or an attributed doctrinal answer.
Canonical-equivalent spellings can differ; no fuzzy or diacritic folding occurs.

The API adds `query` (1–128 characters, nonblank, no C0/C1/surrogate characters)
and integer `limit` (1–8) for this operation only. Context and XML ID arguments
are rejected. Pins, fresh source/license declaration, full re-extraction and
snapshot checks remain required on every invocation.

CLI JSON requires exactly `operation`, `query`, `limit`, `pins`, `declaration`.
Use the same independently trusted pins and exact declaration documented in
fresh-source-study-cli.md. For example, the operation-specific fields are:

    "operation": "search", "query": "literal search text", "limit": 3

Omit `xml_id`. `--confirm-private-study` and `--allow-local-disclosure` are both
required. Do not disclose source results to a shared/logged terminal or external
service without separate permission. Output remains whole ASCII-escaped JSON
bounded to 1 MiB, retaining source layers, notices and false admission flags.

Default search considers only literal-study candidates. Notes, quoted parents,
editorial units and other noncandidates are excluded, not silently declared
irrelevant or safe. `search_scope` states this limitation. Explicit
`--review-noncandidates` changes scope to all selected units for private review
only. Parent/nested matches can overlap; all original record boundaries remain.

Results are in source document order with at most `limit` complete records,
`match_count` within the permitted scope, and an explicit `truncated` boolean.
No ranking, context expansion, concatenation, query logging, persistence,
learning, model call, training admission or scholarship is performed. A match
only identifies matching characters in the pinned parsed text.

Development/tests use invented fixtures only. Source rights and expert review
still apply to real use. Existing held uploads are not included or bypassed.

Validation: full documented unittest suite ran 913 tests in 68.682 seconds,
OK with 54 optional skips. Independent review passed 42 focused tests including
12 new search checks. Frozen preparation and legacy study code are unchanged.
No actual private corpus, model, Windows or Docker-runtime test was performed.

The subsequent pagination extension (fresh-source-browsing.md) adds an optional
explicit offset and total/next-page metadata, so later matches are reachable.
The first-page behavior and match semantics described above are unchanged.
