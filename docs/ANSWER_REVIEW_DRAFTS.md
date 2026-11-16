# Preparing incomplete saved-answer review drafts

The [saved-answer evaluator](SAVED_ANSWER_EVALUATION.md) deliberately separates mechanical citations from human judgment. Preparing reviews previously required manually copying each case's binding hash. This helper collects pending bindings without filling judgments, copying private source/answer text, changing inputs or granting any review status.

Run `python scripts/prepare_answer_review.py /absolute/path/evaluation.json --allow-local-disclosure`. The input is the existing evaluator's object with `cases`, `outputs` and optional `reviews`. The existing bounded POSIX regular-file/no-symlink reader accepts at most 8 MiB; duplicate JSON keys and invalid evaluator inputs fail closed. This is not a Windows source-reader workaround. No database, model, provider, training or corpus admission is invoked.

The output has:
- `draft_reviews`: pending output-bearing cases, each with its exact current `review_binding_sha256`, `verdict: null`, `reviewer: ""`, and `rationale: ""`.
- `missing_output_case_ids`: cases without an output; they cannot receive drafts or reviews.
- `already_reviewed_case_ids`: cases whose supplied review validates against the current binding. This means a valid assertion, not authenticated expert review.
- `draft_count`, explicit false semantic-quality/runtime gates, and a scope warning.

Mechanically rejected answers also receive blank drafts. Mechanical acceptance must never automatically choose `supported`; rejected syntax must not automatically choose a semantic verdict either. Existing reviews are validated first and are not replaced or copied into the draft. Stale or malformed existing reviews stop preparation rather than silently discarding someone’s work.

A qualified human must privately inspect the exact saved question, source records and output, then deliberately complete each draft with one allowed verdict (`supported`, `unsupported`, `uncertain`), their reviewer label and rationale. Merge only completed entries into the original input's `reviews` object without overwriting existing reviews, and rerun the original evaluator. Uncompleted drafts are intentionally rejected by the evaluator. A changed question, source, output or citation requirement invalidates the binding. The helper does not save or merge anything and does not authenticate reviewer identity, qualifications or correctness.

**Privacy and bounds:** the required flag permits IDs and source/answer-derived hashes on local stdout, not publication or third-party sharing. IDs and hashes are not anonymized or secret. The helper omits the question, source, answer, reviewer and rationale text. Command-line paths, input files, terminal sessions and redirected output can still expose information. Use nonsensitive case IDs and protected local files. Output is fully serialized and capped at 128 KiB before writing. Invalid input returns status2 with a generic error; output IO failure warns that output may be incomplete and returns nonzero (Python shutdown can alter the requested status). Discard failed output; redirection is not an atomic file save. Argument-parser/interpreter failures are outside this generic-error contract.

The Python function `prepare_answer_review(cases, outputs, reviews=None)` provides the same incomplete drafts for in-process callers using the unchanged evaluator. It adds no independent benchmark, human approval, scholarly or bilingual review, doctrinal correctness, semantic support guarantee, runtime permission or source rights. Tests use original synthetic cases and temporary files only. Existing evaluator validation and its limitations remain unchanged.
