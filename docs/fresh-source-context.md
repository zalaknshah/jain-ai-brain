# Contextual reading without conflating source layers

An exact fresh-source lookup may now include optional JSON integers `before`
and `after`, each from zero through eight. The CLI sends these explicit values
to the existing verified consumer. Omitting either means zero; null, booleans,
strings and out-of-range counts are refused. Other operations reject these fields.

For example, extend a fully pinned/declared lookup request with:

    "operation": "lookup", "xml_id": "<exact selected ID>", "before": 1, "after": 2

The existing source/license consent and `--allow-local-disclosure` are still
required. If any selected neighbor is a noncandidate, the entire request is
refused unless `--review-noncandidates` is also explicit. Missing or ambiguous
IDs and windows exceeding either end are refused rather than shortened.

Counts refer to adjacent extracted units in source order, not verses or unique
passages. A note may be both within a parent and its own neighboring record.
Output keeps each complete record separate, with original IDs/paths/part layers,
containment links, unchanged false admission flags, attribution and notices.
`target_record_id` distinguishes the requested unit; `context_units_before`,
`context_units_after` and `context_relation` describe the requested window.

Adjacency does not establish that a passage is a commentary on the target,
that a quotation has the same author, or that it supports a modern claim.
The relation label explicitly states that no support relation was inferred.
Use the original edition and qualified review to resolve those questions.

This enables contextual source reading instead of isolated matching, not
translation, answer generation, a training dataset or a robot policy. The
complete-output 1 MiB bound remains: oversized context is refused with no
partial output. Choose a smaller window if necessary. No source text is logged,
persisted, sent to a model or admitted by this command. Terminals may retain
explicitly disclosed output. Source rights and all pending holds remain intact.

Validation: full documented unittest suite passed 931 tests in 69.992 seconds,
with 54 optional skips. Independent review passed 60 focused checks including
eight new context tests. Fixtures are invented; real-corpus, Windows, Docker
runtime, scholarship and model quality were not qualified by these tests.
