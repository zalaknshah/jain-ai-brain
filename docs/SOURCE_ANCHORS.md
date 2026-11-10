# OCR source navigation candidates

`jace.source_anchors.find_source_anchors(source_bytes, page_texts)` is a pure,
bounded helper for reviewers who already have source OCR bytes and page-ordered
OCR text extracted elsewhere. It reads no files, parses no PDF, and invokes no
model, engine, network, training or source-admission path. The caller must
separately have permission to acquire and process those inputs. No source corpus
or real-source output is packaged with this feature.

The helper looks for unique exact sequences of eight words by default, accepting
an explicit integer from four through sixteen. Matching ignores Unicode
whitespace only. It never changes case, punctuation, spelling, diacritics or
Unicode composition. It returns hashes and original UTF-8 byte offsets, not
passages, filenames or source metadata.

For an interior-span candidate, at least two unique anchors must be ordered and
non-overlapping in both inputs. All matching anchors on that page must follow
source order. The span between outer anchors must contain no more than twice
the page OCR word count. Duplicate source anchors are unusable, not resolved by
guessing. Any overlap or order conflict across candidate pages marks every
involved candidate as conflicting, including when an intervening candidate has
already been rejected. Status counts always include unresolved and empty pages.

These are **interior navigation candidates, not complete page boundaries or
certified citations**. Unmatched words outside anchors are neither included nor
inferred. A word count measures agreement between supplied OCR strings, not
accuracy against a scan. Both strings may share the same OCR mistakes. Main
text, headings and footnotes may be mixed in a candidate. Visually inspect the
correct scan, establish page identity and content layers, retain correction
provenance and complete separate scholarly/rights review before further use.
All scan-review, layer-separation, runtime and training flags remain false.

Uniqueness is relative to the supplied OCR words, not the printed edition. A
repeated printed phrase can look unique elsewhere when one OCR copy contains a
spelling error. If such a match jumps against surrounding anchors, the page
stays unresolved even when most other words match; do not discard inconvenient
anchors just to obtain a candidate. Entire consistently matching fragments can
also coincide with the wrong occurrence without triggering an ordering conflict.
The helper has no scan or page-identity oracle, so even a clean candidate still
requires visual page verification before it can support a citation.

Bounds: source bytes 1 through 1 MiB, at most 200,000 source words, 1 through
1,000 page strings, each at most 20,000 characters, and at most 2 MiB combined
UTF-8 page text. Invalid types/UTF-8 or exceeded bounds reject the whole call.
These bounds do not sandbox the caller or promise whole-process resource limits.
Output may still reveal source length, page counts and matched positions; do
not publish it without appropriate permission merely because text is omitted.

Synthetic regressions cover exact hashes/offsets, multibyte characters and CRLF,
duplicates, missing/short pages, reordered anchors/pages, distant spans,
nonadjacent conflicts, input limits, unchanged original inputs and non-admission.
Additional original synthetic cases preserve the repeated-phrase/OCR-variation
failure mode and demonstrate that uniqueness never certifies scan-page identity.
They do not establish real-corpus or semantic accuracy.

For separately prepared manual layer annotations, the
[source layer coverage audit](SOURCE_LAYERS.md) checks exact byte/hash bindings,
overlap and omitted coverage without changing these candidates or granting any
review approval. Complete mechanical coverage is not proof of a correct label.
