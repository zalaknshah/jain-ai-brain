# Mixed-edition source-layer preparation

`prepare_layers(source_bytes, specification)` in `scripts.prepare_layer_alignment`
prepares explicit root, rendering, translation, commentary and editorial units
for human review. This addresses a concrete corpus problem: an edition page may
mix Prakrit root text, Sanskrit rendering and modern-language commentary. A
page-level language declaration must not become a training label for every layer.

The specification contains source_sha256, metadata and layers. Edition metadata
uses the translation-preparation fields except declared_source_language/text_role.
Each layer requires id, byte_start, byte_end, locator, language, role, family and
root_id. Ranges are exclusive-ended UTF-8 byte offsets, nonempty and nonoverlapping.
The root_id is null for roots; other layers must reference an included root in
the same declared passage family, even when listed before that root. Unsupported
schema fields, overlapping units and bad references fail closed. Up to 64 units
and the existing 4 MiB source/24,000-byte excerpt bounds apply.

All declarations are provisional. Language is never inferred from script. A
root link is a reviewer hypothesis, not proof of equivalent meaning. Root source
bindings are included in linked alignment hashes. Canonical digests use sorted
JSON, ensure_ascii=True and compact separators. Caller mutation cannot rewrite
the resulting evidence. Outputs retain exact source bytes as decoded text, so
keep them in authorized private storage, not this public code repository.

Every unit retains blank Gujarati/Hindi/English translation-review slots, pending
language/role/OCR/training-rights checks, and false training/runtime/public-release
gates. No API, model, download, persistence, filesystem or external service is
called. The library does not import these proposals into the training manifest.
Preserve actual source attribution and rights separately. Keep all translations
and commentary of a passage family together in later splits; this tool records
that relationship but does not implement dataset splitting or admission.

This is useful preparation infrastructure, not general Prakrit understanding,
translation, scholarship, model training or robot qualification. Real mixed-page
span selection and qualified review remain necessary. Tests contain synthetic
text only, no private literature or corpus-derived expected answers.

Validation (2026-11-14): initial six focused tests passed and full suite completed
831 tests with 54 optional skips and no failures. Independent review found no
blocking source defect and requested an isolated valid-UTF8 overlap case; that
case plus adjacent-span acceptance was added, and all seven focused tests passed.
No source code changed after the full run. A transient execution transport
failure interrupted status reads, not the completed test process. No real corpus
was processed or uploaded by this change.
