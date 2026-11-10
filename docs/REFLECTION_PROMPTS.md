# Unanswered reflection prompts

`jace.syadvada.evaluate(text, evidence=None)` retains its legacy name, arguments,
seven-row order, Sanskrit labels and English labels. It no longer evaluates
lexical cues or uses the mere presence of evidence to assign scores. Neither
argument is analyzed. All questions are original editorial scaffolding, not a
translation, formalization or validated application of Jain doctrine.

Each row has:

- `index`, `sanskrit`, `label`: existing compatibility identifiers.
- `conclusion`: an explicit statement that no evaluation or claim about support,
  contradiction or truth has been made. This is not an answer to the question.
- `confidence`: JSON `null`, **not zero probability**, a low-confidence score or
  an estimate that can be ranked. No calibrated confidence is available.
- `basis`: the fixed editorial and non-analysis limits.
- `prompt`: an unanswered conditional reflection question.
- `status`: `not_evaluated`.

The change from numeric confidence to null and the changed meaning of
`conclusion` are intentional contract changes. Consumers must stop rendering a
percentage, sorting/ranking rows by confidence, or treating `conclusion` as a
finding. Two new required dataclass fields, `prompt` and `status`, also affect
callers constructing `Perspective` directly. The normal API/CLI retain their
`perspectives` array. HTTP health advertises `reflection_prompt_protocol: 1`.
Old persisted responses are not rewritten and may still contain the previous
unsupported scores. Update downstream consumers before relying on this contract.

The standard engine supplies these rows to the local or configured reasoner.
The local reasoner does not use them to calculate its answer. The configured
HTTP adapter keeps the legacy `seven_perspectives` context key but explicitly
identifies the rows as unanswered prompts, not findings or supporting evidence.
This instruction is not a guarantee that an external model will follow it.
The browser reports the count only as metadata, not validated reasoning; it does
not display the questions. Evidence-only selected-context mode remains separate
and returns no perspective rows.

## What was wrong

The previous implementation assigned fixed numeric scores from English regex
matches and whether an evidence list was nonempty. Even `['']` raised the first
score from 0.45 to 0.62. Supporting, contradicting, unrelated and instruction-like
passages could all produce the same apparent conclusions. The words “because”
or “currently” could raise a score without adding evidence. These were not
probabilities, calibrated confidence or semantic-support assessments.

Replacing the scores with unevaluated prompts removes those unsupported
assertions. It does **not** add factual reasoning, entailment, multilingual
understanding, doctrinal competence or source admission. The same fixed prompts
for every input are now an explicit limitation, not evidence of correct answers.
The separate semantic-support diagnostic still exposes the existing mechanical
citation check's inability to determine whether a passage supports a claim.

## Validation scope

Regression controls cover empty, blank, supporting, contradicting, unrelated,
instruction-like and reordered evidence, input polarity/lexical variations,
serialization, the engine's blocked and normal paths, actual loopback HTTP,
CLI, captured mock-provider context, and source/wheel installation. No external
provider, new corpus, real user text or doctrinal benchmark is needed or used.
Tests establish this output contract, not the truth of any answer or the validity
of the seven historical predicates.
