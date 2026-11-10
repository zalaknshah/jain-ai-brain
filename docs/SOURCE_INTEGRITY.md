# Exact-source corpus bundles

JACE can now bind an admitted passage to exact local UTF-8 source bytes. This is a mechanical integrity feature, not a source-authentication, rights-clearance, scholarly-review or answer-entailment system. It was developed and tested using original synthetic text only. No collected religious material is included or activated by this feature.

## What is checked

A `jace-source-bundle-v1` directory contains `bundle.json` and a `sources` directory. Each source is stored as `sources/<lowercase SHA-256>.txt`. Its manifest descriptor contains that exact relative path and digest. Each record contains descriptive metadata and a `source_ref` with the digest and integer `start`/`end` offsets. The range is zero-based, end-exclusive, and measured in UTF-8 **bytes**, not characters.

The loader hashes the bytes actually read, checks every referenced range and derives `principle` from that slice. It does not accept a caller-supplied principle or integrity result in a bundle record. Both endpoints must be valid UTF-8 boundaries. Interior spaces, tabs, LF and CRLF are preserved. Empty/whitespace-only passages, standalone CR, terminal control characters and selected bidirectional controls are rejected. The original complete source copy is not rewritten.

The admitted immutable `CanonicalEntry` carries `source_sha256`, `source_byte_start` and `source_byte_end`; its tags are frozen too. Those fields participate in the existing content-addressed graph namespace. Different live engines sharing a database retain their own admitted source scope. Failed admission occurs before graph seeding, and changing a file later does not silently change the running engine's snapshot. A fresh engine must read and validate the bundle again. There is no automatic reload or revocation of an already constructed answer.

Server-rendered citations identify the source digest and byte interval checked at admission. An optional model's quote must still be an exact substring of a reviewed record retrieved for that request. The renderer derives its byte range locally; for repeated identical text it identifies the first matching occurrence. Generated prose is not checked for semantic support. Local fallback passages also identify their admitted source range. Metadata never exposes local source paths automatically.

## Build a private local bundle

Only use text for which the intended use is permitted and qualified review is complete. `--verified` and the license/source fields are **operator declarations**: entering them does not prove those facts, authorize transmission, or make a source trustworthy. Source text remains untrusted prompt content.

The following example refers to an original synthetic local file, not a religious work:

```sh
python scripts/build_source_bundle.py ./reviewed-fixture.txt \
  --output ./fixture-bundle \
  --work "Original synthetic fixture" \
  --source "Operator-authored fixture" \
  --language en --license "Operator owns this fixture" \
  --location "Fixture section 1" --verified --confirm-build
```

The output parent must already exist; the target itself must not exist. Omit `--confirm-build` to see the consent reminder without reading or copying source files. `--verified` and `--confirm-build` are both required to build. This copies the **whole** supplied source files, not only selected passages. Keep the result private and do not commit, upload or share it merely because the program succeeded.

Accepted inputs are explicitly named `.txt`, `.md` or `.markdown` files containing strict UTF-8. The default chunk is 220 whitespace-delimited words with a 40-word overlap. Custom chunk sizes are 1–1000 words with a smaller nonnegative overlap. Segmentation retains exact interior source bytes and excludes whitespace outside the first/last word of each chunk. This is not language-aware verse, sentence or scholarly segmentation. Use separately prepared, reviewed source units when different pages/sections need different location metadata; the convenience builder copies the supplied location to every generated chunk rather than inferring page numbers.

After separate approval to use a corpus in a local runtime, set `JACE_CANONICAL_PATH` to its `bundle.json`, or pass that path to `CanonicalStore`. The builder does not set environment variables, alter runtime configuration, populate the memory database, train a model, download content, call a provider or share files. A wheel installation exposes the library builder API; this repository's convenience script is not installed as a separate CLI command.

## Filesystem and resource boundaries

- Manifest: at most 2 MiB, JSON nesting at most 32 levels, no duplicate keys or nonfinite numbers. Unknown fields are rejected.
- Sources: 1–32 regular files, at most 1 MiB each and 8 MiB total. Duplicate/conflicting descriptors, unreferenced sources and undeclared entries inside `sources/` are rejected. Arbitrary extra files elsewhere in the bundle root are not consumed.
- Records: 1–256. Each passage is at most 20,000 characters and 65,536 bytes. IDs are unique, at most 128 characters, with no whitespace or citation delimiters. Titles, metadata and tags have individual limits; tags are at most 32 distinct values of at most 64 characters.
- Reader paths reject parent traversal and walk every component using pinned directory descriptors and `O_NOFOLLOW`. Symlink ancestors/files, hard-linked files and nonregular files are rejected. Nonblocking open prevents a FIFO source from hanging before its type check. Actual reads are bounded independently of the initial stat size. Inode/stat checks before and after reading catch ordinary replacement or mutation.
- Writers validate first, create a same-parent private staging directory, write mode-0600 files under mode-0700 directories, reread/validate staged bytes, then publish by Linux `renameat2(RENAME_NOREPLACE)`. A racing or pre-existing target is never overwritten, even an empty directory. Failed pre-publication writes clean only the owned staging area. There is no unsafe check-then-overwrite fallback.

External corpus reads require POSIX descriptor-relative and no-follow support. Default startup instead uses a bounded fixed package sample resource on every platform, with no exact-source provenance; it does not fall back to an arbitrary external file or the repository-level data mirror. This preserves the cross-platform local sample path, while a later native Windows source-operation attempt correctly failed closed; successful Windows exact-source support remains unimplemented. Publication requires Linux and the installed libc's `renameat2` support; unsupported platforms/filesystems fail closed. The feature does not provide a portable Windows export path. These bounds constrain this admission code, not a full-process memory/CPU sandbox or a privileged writer. A privileged writer able to falsify filesystem state is outside the guarantee. A hostile same-user writer could also alter an ancestor or replace a staging name after the last check: the rename-by-name publication primitive does not atomically bind every previously checked inode. Use a trusted private output parent, not a shared writable directory. Hard-link rejection adds defense but is not an identity/authenticity proof: matching digests bind the admitted bytes, not their creator.

Publication is atomic visibility of a fully validated directory, not a promise of power-loss durability. Files and staging directories are synced before rename, but no post-rename parent sync is claimed; a hard crash can require operator inspection/rebuild. If an OS/filesystem error prevents cleanup, an inaccessible private staging directory may remain. Do not blindly retry an uncertain external operation or delete an unfamiliar directory.

## Legacy records and compatibility

Existing JSON-list corpora are still supported but explicitly labeled **record-only excerpt matching**: no backing source-file bytes were checked. The older `scripts/ingest_corpus.py` normalizes whitespace into records and does not create byte provenance. It remains useful for review-only drafts, but its output is not equivalent to an exact-source bundle.

Legacy draft ingestion always writes `verified: false`. Draft and verified-runtime
declarations are mutually exclusive at both the CLI and library boundary, and
both library mode values must be literal booleans. A conflicting declaration is
rejected before any input read or output change, rather than emitting a draft
that can be runtime-admitted. Adding licence/location metadata alone cannot
promote a draft. Existing files are not rewritten or reclassified by this fix;
review any previously generated output separately. These controls prevent an
accidental mode conflict, not deliberate manual editing, false review statements
or an operator changing code. Rights and scholarly review remain required.

Runtime admission of legacy lists is now bounded too: the safe manifest reader, 2 MiB/nesting limits, 1–256 records, field/text/tag limits, unique IDs and strict known fields apply. A legacy list cannot assert any of the three source-integrity keys, even with null values. Existing reviewed records still need nonempty work/source/language/location/license and literal `verified: true`; built-in unreviewed samples remain sample-only. Oversized, malformed, extra-field, symlinked or hard-linked corpora that previously loaded can now be rejected, not truncated or silently upgraded. Rebuild or review such data explicitly.

Legacy serialization omits absent integrity fields, preserving existing admitted corpus hashes. Historical canonical graph records remain on disk under the existing non-destructive retention behavior, while active retrieval excludes another corpus's nodes. Private memories are neither copied into bundles nor erased by changing the corpus.

## Evidence and remaining work

```sh
PYTHONPATH=src python -m unittest discover -s tests -p 'test_source*.py' -v
```

The 54 original fixture tests cover malformed/oversized/nested metadata, duplicate fields, byte/range/UTF-8 failures, symlink/hard-link/FIFO handling, source and ancestry substitution, bounded reads, atomic no-overwrite races, injected write/fsync/publication failures, private-stage cleanup, exact chunk spans, CRLF-preserving citations, repeated-quote offsets, legacy provenance rejection, immutable startup snapshots, different live engines sharing a temporary database, and mocked unavailable POSIX support with bounded default-package startup. These are code and local-filesystem regressions, not validation of any religious source or real provider.

Still required: authentic licensed editions with qualified review, reliable page/verse alignment, reviewed retrieval/answer holdouts, meaningful semantic support checks, and a qualified model. A valid local digest cannot establish any of those.

## Platform preflight

`python -m jace.cli source-capabilities` reports read and publication prerequisites without opening sources, initializing the engine or creating output. Confirmed builders/review exporters check known publication prerequisites before reading inputs or staging files. Presence of a libc API is not proof of kernel or filesystem support, so the final operation still fails closed if unsupported. See [platform boundaries and required Windows design](SOURCE_PLATFORMS.md).
