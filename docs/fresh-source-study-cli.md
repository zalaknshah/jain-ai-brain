# Explicit fresh source-study CLI

`python -m jace.cli fresh-source-study --stdin --bundle-directory /absolute/private/bundle --confirm-private-study`

Reads at most 8 KiB JSON on stdin. Inventory requires exactly these keys. Lookup requires these keys and permits
only the optional before/after context fields documented below. Bounded literal
search uses its own request schema documented in fresh-literal-search.md:

- `operation`: `inventory` or `lookup`.
- `xml_id`: null for inventory; one exact selected XML identifier for lookup.
- `pins`: all six `ExpectedPins` fields (source, attribution, accession, changes,
  records and manifest SHA-256). Obtain from a separately trusted checkpoint,
  never by hashing the bundle being checked.
- `declaration`: all `StudyDeclaration` fields: exact consumer_version
  `jace-fresh-private-consumer-v1`, preparation_version
  `jace-fresh-private-tei-study-v1`, source_sha256 matching the trusted pin,
  accepted_license `CC-BY-SA-4.0`, purpose `fresh-private-source-study`, and
  opted_in true. The declaration attests existing authorization, not new rights.

Inventory emits only the verified consumer's aggregate metadata. Lookup requires
`--allow-local-disclosure` in addition to the request; this explicitly permits
selected source text and attribution/accession notices on stdout. Terminals and
redirected files can retain that output. Do not enable it on shared/logged
terminals or forward results to providers without separate authorization.

Noncandidate lookup also requires `--review-noncandidates`. This permits private
inspection only, not scholarly validation. Quotation/note/editorial layers and
all false review/admission flags are preserved. There is no context expansion,
translation, correction, database, model call, engine construction or learning.

Whole output is serialized before stdout, bounded to 1 MiB, and JSON ASCII
escaping prevents source control characters being rendered directly. An error
emits no partial source output. Secure POSIX bundle reading is required; Windows
is not supported by this entry point. Legacy `source-study` remains unchanged.
No private corpus or real source output is included in these code/test files.

This makes the fresh API locally usable, not a general Jain reasoner or training
pipeline. Initial focused validation used 13 invented-fixture tests; live
private-corpus use and terminal privacy remain separate operator obligations.

Request template (replace placeholders with independently trusted lowercase
64-character hashes; placeholders deliberately do not pass validation):

```json
{
  "operation": "inventory",
  "xml_id": null,
  "pins": {
    "source_sha256": "<trusted source hash>",
    "attribution_sha256": "<trusted attribution hash>",
    "accession_sha256": "<trusted accession hash>",
    "changes_sha256": "<trusted changes hash>",
    "records_sha256": "<trusted records hash>",
    "manifest_sha256": "<trusted manifest hash>"
  },
  "declaration": {
    "consumer_version": "jace-fresh-private-consumer-v1",
    "preparation_version": "jace-fresh-private-tei-study-v1",
    "source_sha256": "<same trusted source hash>",
    "accepted_license": "CC-BY-SA-4.0",
    "purpose": "fresh-private-source-study",
    "opted_in": true
  }
}
```

For lookup, change the operation to `lookup` and replace `xml_id` with the exact
selected unit ID, then supply the local-disclosure flag. Inventory deliberately
rejects lookup/disclosure options instead of silently ignoring them. No consent
is saved for the next invocation. Preparation candidates are not automatically
validated quotations or ground-truth answers.

Final local full-suite validation: 901 tests ran in 69.641 seconds, OK with 54
optional skips. Independent review passed 13 request and five static container
checks and exercised three separate-process synthetic CLI journeys (inventory,
denied lookup without disclosure, permitted lookup). No actual source corpus
was used. These checks are not native Windows or container-build qualification.

Bounded browsing and later search pages are documented in fresh-source-browsing.md.
Browse has a distinct exact JSON schema and the same explicit disclosure gates.

Lookup can additionally request bounded neighboring extracted units with optional
`before`/`after` fields; see fresh-source-context.md. They are not inferred
commentary/support relations and do not relax disclosure or review permission.

Explicit nonadjacent comparative reading is documented in fresh-source-selection.md.
