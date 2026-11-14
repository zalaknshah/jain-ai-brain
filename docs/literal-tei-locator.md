# Literal TEI reference locator

`from scripts.locate_tei_terms import locate`

Call `locate(source_bytes, expected_sha256, query, limit=50)` locally on a rights-cleared TEI source. No filesystem, network, credentials, model, or runtime calls are made. Output is metadata-only: source and query digests, ordinal verse-group locator, parsed-text digest and character offsets. Arbitrary source attributes (including verse labels and language declarations) and the literal query are never echoed. It does not output verse text. The caller must retain provenance and attribution separately; hashes do not certify rights.

The helper searches TEI body `lg` elements, not header bibliography. Each group's exact parsed text is `''.join(element.itertext())`, including original whitespace and descendants. XML predefined/numeric references are interpreted; comments are not text. No case folding, Unicode normalization, morphology, transliteration or tokenization is performed. Offsets refer to Python Unicode characters in that parsed string, not original XML byte spans. One-based document group index is the locator; no `n` label is trusted or emitted. Nested groups can both match overlapping material. A substring hit is not a lexical sense, semantic equivalent, doctrinal claim, or translation. No hit does not establish absence under other spellings.

Input is bounded to 2 MiB UTF-8, depth 128, query 128 characters and 100 returned groups. DTD/entity declarations, null bytes, wrong source digests, invalid limits and non-TEI roots fail closed. Offsets are capped at 64 per returned group and 512 across the response, with explicit per-group truncation flags. After the group-return limit, only a single existence search is performed per group, never offset enumeration. It never promotes training/runtime or translation verification. Hashes and match locations are still derived information, not anonymization: keep outputs private with their source context, and do not treat this as permission to transmit them.

## Checks

Eight synthetic unit tests cover source binding, body scope, overlapping/literal matches, duplicate labels, truncation, numeric entities, DTD rejection, bounds and depth, repeated-character amplification, and source-attribute/query non-disclosure. A local read-only check on the independently acquired licensed Pāiyalacchīnāmamālā reference identified 279 groups and the same previously recorded candidate locators for three search strings. No corpus was added to this public code change and no external model saw it.

Initial aggregate invocation omitted the README-required `PYTHONPATH=src` and failed import-dependent cases; that result is not a product regression pass. See final execution report for corrected aggregate results. This helper is research/reviewer tooling only, not trained Jain reasoning or a robot safety gate.

## Opt-in marked base-text quotes

`locate(source_bytes, expected_sha256, query, scope="marked-base-text-quotes")`
searches only TEI body `quote` elements whose exact `type` attribute is
`base-text`. It returns `jace-literal-tei-marked-quotes-v1`, with `units_examined`,
`matching_units` and per-hit `unit_index` instead of the default group fields.
Default verse-group behavior and response format are unchanged. This gives
reviewers a structural way to exclude commentary and unmarked quotations in
mixed lexicon files. It does not infer language or establish that the publisher's
markup is correct: `source_markup_verified` remains false. Nested marked quotes
count separately and may overlap; counts are not unique lexical entry counts.

All existing literal-match, digest, private-output and resource bounds apply.
A marked quote's entire parsed descendant text is searched, including any inline
notes: this is an explicit XML boundary, not an independently verified root-text
extraction. No marked units or no hit establishes neither corpus completeness nor
absence of a word. This is not translation, definition extraction or training.

Six added synthetic tests cover scope exclusion, default compatibility, nested
unit overlap, fail-closed scope/digest, bounded output and no marked units. Private
reference smoke checks must disclose only structural counts, never source text.

This increment's local verification: 14 locator tests passed; the aggregate
`PYTHONPATH=src python -m unittest discover -s tests -q` ran 875 tests with 54
optional skips (821 executed). Count-only private smoke checks observed 279 verse
groups and no marked quotes in Pāiyalacchīnāmamālā, and 1,425 verse groups and 781
marked quotes in Dēśīnāmamālā. These are XML structure observations only. No
private source passages or derived matches are included in the public tests.
