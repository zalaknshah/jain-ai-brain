# Locate a literal hit within source layers

Fresh-source search now returns `match_locations` for only the records on the
requested page. Each entry binds a record ID and up to32 overlapping exact
substring occurrences. `more_locations` signals additional occurrences rather
than silently implying exhaustive coverage. The existing `match_count` remains
a count of matching records, not occurrences.

Each occurrence has half-open `start`/`end` offsets in Unicode code points of the
verified parsed text. These are not UTF-8 bytes, UTF-16 code units, original XML byte spans, grapheme
positions, translations or normalized text. Intersecting parsed parts retain
part index, part-local half-open offsets, XML path, text/tail slot, inherited
language and quotation/note flags. Zero-length parts do not become fragments.
`crosses_part_boundary` identifies matches spanning multiple parts, including
possible commentary/quotation or note boundaries.

This helps a reader locate the exact lexical hit without treating a quotation
as an author's endorsement. `literal_match_not_semantic_support` is explicit.
Inherited language is not verified language identification. Full source records,
notices, opt-in, noncandidate review and all false admission flags are unchanged.
No source corpus, translation, model call or training is added.

The same exact-source checks run before locating hits. The CLI's complete1MiB
output limit still applies; location metadata can make a large page refuse,
with no partial output. Choose a smaller page, not weaker guards.

Initial test invocation used the wrong working directory and ran no tests.
Corrected focused tests found an empty-part intersection bug; it was fixed before
qualification. This does not resolve earlier private-source harness failures.

Full suite passed945tests in72.356seconds with54optional skips. Independent
review passed74focused tests and300additional deterministic range/fragment checks.
No actual corpus, browser, scholarly interpretation or model qualification.
