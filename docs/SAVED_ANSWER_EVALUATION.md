# Evaluating saved source-based answers

Run `python scripts/evaluate_source_answers.py /absolute/path/evaluation.json`
to inspect previously saved answers without calling a model, sending source text,
training, modifying a corpus, or granting runtime admission. This uses the same
mechanical citation checker as the optional model adapter.

The local JSON file has `cases` (a list), `outputs` (an object keyed by case ID),
and optionally `reviews` (another object keyed by case ID). Each case contains
only `id`, `question`, `require_citation` (boolean), and `evidence` (a list of
CanonicalEntry record objects). Each output is the raw JSON answer string in the
existing `{answer, citations}` model-output contract. Omit a case from `outputs`
when generation failed or never ran; null is not a saved output.

Case IDs are unique ASCII letters, digits, hyphens or underscores, at most 64
characters. At most 256 cases and 20 evidence records per case are accepted.
The CLI accepts a bounded 8 MiB regular, no-symlink local input file on POSIX.
Duplicate JSON keys and invalid inputs are rejected. Source review and rights
fields remain declarations, not independently authenticated facts. Use only
material you are authorized to study; this tool does not authorize its ingestion.

## Separate mechanical checks from semantic review

The report counts all declared cases, including missing outputs. It separately
reports valid answer/citation structure, satisfaction of the per-case citation
requirement, missing reviews and the three supplied human verdicts. An exact
quote can accompany a contradictory answer; the checker does not mark that
answer semantically supported. A zero exit code means inspection succeeded,
not that the model passed a quality benchmark.

An initial report provides a `review_binding_sha256` for each case. A human review
uses exactly these fields:

```json
{
  "review_binding_sha256": "COPY THE EXACT HASH FROM THE REPORT",
  "verdict": "unsupported",
  "reviewer": "local reviewer label",
  "rationale": "The generated conclusion contradicts the cited passage."
}
```

The allowed verdicts are `supported`, `unsupported`, and `uncertain`. Keep the
original review alongside the input privately. A changed question, source record,
citation requirement or raw output invalidates the review binding. Missing output
cannot receive a review. The hash detects accidental mismatch; it is not a
signature or proof that a qualified human reviewed anything. Self-written or
model-written annotations are not independent human validation.

Output reports omit source, question, answer, reviewer label and rationale text;
case IDs and hashes remain visible. Choose non-sensitive case IDs and do not treat
hashes as anonymization. The tool does not write a report file unless the operator
explicitly redirects stdout. It cannot discover undeclared omitted cases.

`semantic_quality_verified` and `runtime_admitted` are always false. Supplied human
annotations do not establish doctrinal accuracy, expert identity, general Jain
reasoning, robot safety, complete coverage or fitness for deployment. This slice
was tested with original synthetic records, not Agamas or a newly trained model.
