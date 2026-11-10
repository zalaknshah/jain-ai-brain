# Private source layer coverage

`jace.source_layers.audit_source_layers(source_bytes, selection, layers)` checks
manual annotations against bytes already supplied in memory. It performs no IO,
PDF parsing, OCR, corrections, model calls or source admission. Obtain permission
to acquire and process inputs separately. No collected text is packaged here.

The selection is an exact dictionary with `source_sha256`, `start`, `end` and
`span_sha256`. Each layer is an exact dictionary with `start`, `end`,
`span_sha256` and `layer`. Digests are lowercase SHA-256. Offsets are zero-based,
end-exclusive UTF-8 bytes of the original source, not character indexes. Layer
labels are `main_body`, `editorial_note`, `section_heading`, `running_header`,
`printer_signature` or `unclassified`. The caller, not the program, supplies
these labels. Nested semantic labels (such as a paragraph number within body
text) belong in a separate annotation set, not an overlapping layer partition.

The audit rejects stale source/span digests, invalid UTF-8 or mid-character
endpoints, unknown fields/labels, overlapping, reversed or out-of-order spans,
and spans outside the selection. It never sorts, clips, normalizes or repairs
inputs. Empty layer lists are allowed and report the whole selection as a gap.
All uncovered intervals, including whitespace-only gaps, retain original byte
ranges and hashes. Unicode `str.isspace` defines whitespace for counting only.
Newlines, spaces and CRLF are never rewritten.

Three different coverage results avoid conflating partial evidence:

- `selection_fully_partitioned`: every selected byte belongs to an interval.
- `all_selection_non_whitespace_assigned`: any remaining gaps are whitespace.
- `all_selection_non_whitespace_classified`: in addition, no non-whitespace
  character is inside an `unclassified` interval.

None means that a label is correct, that OCR matches a scan, or that this is a
complete page. A completely wrong layer declaration can pass every mechanical
check. Page identity, line-by-line comparison, omitted context, continuation
across pages, transliteration and editorial versus main text require separate
review. Audit output always keeps scan identity, layer verification, scholarly
review, runtime and training flags false. Do not treat it as a review decision
or feed it into an admission path. Existing automatic OCR candidates remain
unchanged even if a separate manual selection has complete coverage.

Inputs are bounded to 1 MiB of strict UTF-8 source, a nonblank selection of at
most 65,536 bytes, and 0–256 layer intervals. Dictionaries, lists, strings,
bytes and integers must have the exact expected types; booleans are not offsets.
Returned data contains no source text, arbitrary metadata or paths. Hashes,
lengths, ranges and labels may still reveal private information and need separate
permission before publication. Bounds do not sandbox the caller or whole process.

Original synthetic tests cover byte/hash identity, Unicode and CRLF, whitespace
gaps versus omitted text, explicitly unclassified text, overlap and bounds,
invalid types, strict fields, input immutability and non-admission. These tests
do not establish real-corpus OCR, semantic or scholarly accuracy.
