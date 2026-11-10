# Proposed context support annotation contract

## Purpose and status

This contract defines what a supplied context licenses an annotator to label `supported`, `contradicted`, or `not_established`. Adopt explicit attribution boundaries: ordinary unqualified fictional narration supplies stipulated premises; a statement that a source reports a proposition establishes the report, not automatically the proposition.

This is an independently reviewed development proposal, not an adopted runtime policy or a change to the frozen evaluator, historical datasets, labels, or candidates. Earlier drafts and their findings were retained during review. Its accompanying examples are original, exposed development illustrations written after reading the paired trial and its label review. They are not an unseen benchmark, an independent gold set, or evidence of improved model performance.

The target is contextual support. No label by itself establishes real-world truth, source accuracy, scholarly authority, Jain doctrine, or the truth or superiority of any belief. A real-world application would separately need appropriate evidence assessment, source provenance, and domain expertise.

## Why this contract is needed

The archived paired trial reported 12 flagged cases across six matched groups and eight primary-label disagreements. Whole-group exclusion removed four of the five cross-source groups. The review exposed four distinct scope problems:

- A log, roster, inventory, or bulletin was treated as a world fact without a clear truth stipulation.
- Later sentences could be read either as continuing a report or as direct narration.
- A location-restricted rule was applied without an explicit link placing its subject in that location.
- A statement about one agent after an event was extended to all agents or the entire day.

These are annotation-policy questions. The original trial and review remain historical evidence, not material to relabel silently under this proposal. See the source record at the end.

## The unit of judgment

Judge the exact claim against the complete supplied context, including any task preamble that is actually provided to the annotator or model. Do not use author notes, gold rationales, filename hints, private metadata, outside knowledge, or the apparent intent of a fixture author as extra premises.

For each claim, identify:

1. **Target:** the fictional world, what a particular source reports, what an agent believes, or a consequence of explicitly identified accounts.
2. **Proposition:** predicate, polarity, quantity, and any condition.
3. **Referents:** object identity, agent, location, role, and time interval.
4. **Premises:** exact text spans and the scope in which each is valid.
5. **Bridges:** explicit alias, membership, persistence, or truth guarantees needed to connect those premises.

Do not erase “according to,” “says,” “believes,” “at noon,” “in the courtyard,” or “by Mara” while normalizing a claim.

## Label rules

Apply these rules to the exact target using all admissible supplied premises. Track derivations of the claim and its same-target negation separately, without deriving arbitrary conclusions from a contradiction. Excluding a premise requires a stated source, referent, time, or other scope reason, not that it is inconvenient for the desired label.

- `supported`: The context entails the claim at its stated scope, and does not also entail its same-target negation, using ordinary language understanding and valid scoped reasoning from supplied premises.
- `contradicted`: The context entails the negation of the claim at that same scope, and does not also entail the claim. Merely lacking support is insufficient.
- `not_established`: The context entails neither the claim nor its negation. A claim may be plausible, unlikely, reported, or partially supported and still receive this label.

Use an open-world policy. An unmentioned action may have happened. An incomplete list does not exclude other members. A statement that one person did something does not exclude others doing it. Words such as “exactly,” “only,” “none,” and explicitly exhaustive lists can close the relevant scope, but no wider one.

For conjunctions, all conjuncts must follow for support. A negated conjunct can contradict the conjunction; a merely unknown conjunct cannot. Ordinary arithmetic and explicit universal rules may be used, preserving their domain, time, and source scopes.

**Do not force a label for a broken annotation unit.** If admissible premises entail both the claim and its same-target negation, or a material attribution/referent ambiguity gives different labels, set a separate review disposition of `review_needed` and leave the semantic label unset. This is a review status, not a fourth semantic class or a change to the frozen schema. Do not encode a conflict as `not_established`. Proposed new labeled fixtures should omit unresolved units until repaired and reviewed. If every defensible reading has the same label, that label may be retained with the ambiguity documented.

Screen conflicts at the claim's target and relevant inference dependencies. Do not discard an inconvenient admissible premise or select a convenient consistent subset to obtain a label. Record an unrelated conflict separately rather than allowing it to invalidate every other claim or entail anything whatsoever. “S states P” and “S states not-P” can both be true reporting facts; neither is the negation of the other. An unendorsed source disagreeing with a narrator fact does not negate that world fact. If a claim asks what follows from an account that supports both the claim and its same-target negation, that claim needs adjudication. An ambiguous dependency that prevents identifying which scoped premises are available also needs adjudication.

## Narration and reported content

### Direct narration supplies stipulated premises

In an explicitly fictional task, “The violet lamp is lit at noon” supplies that fact at noon. Do not demand an additional source or reliability certificate for ordinary unqualified narration. This is a reading contract for a constructed scenario, not a policy that any real document's assertions are verified facts.

Explicit qualifications override this default: quotations, reported speech, beliefs, hypotheticals, dreams, imagined alternatives, and a declared unreliable narrator remain inside their stated scopes. An unqualified narrator statement that a source exists or says something establishes that reporting event, not the truth of the quoted content.

### Reports retain their attribution

“The notice says the violet lamp is lit at noon” establishes what the notice says. It does not alone establish that the lamp is lit, or that it is unlit. The same rule applies to a log, register, database entry, diagram, witness account, official bulletin, or confident expert statement.

Repeated or agreeing reports do not become world facts merely by repetition, source count, prestige, or apparent independence. A report of a negative proposition also remains a report: “The note says no guest entered” does not by itself contradict the world claim “A guest entered.”

Keep nesting intact. “Memo A says that Memo B says P” establishes A's account of B, not necessarily that B actually says P, and not P.

### Source scoped claims are legitimate targets

For this task, “S says P,” “S reports P,” and “S explicitly states P” require a direct assertion or faithful paraphrase in the specified source content, not merely a logical consequence. If “according to S” has materially different assertion-versus-consequence readings, adjudicate or rewrite the claim. A faithful source-content claim can be supported without establishing P. A claim that the source is correct is a different, world-directed claim and needs a truth bridge.

Distinguish content from consequences. “The report explicitly states P” requires a direct assertion or faithful paraphrase, not a new deduction. “P follows from the report's account” may use valid inference within that account. “P follows from reports A and B taken together” may combine those reports only with explicit compatible referents and scopes; it does not mean either report individually states P.

A report saying P does not automatically contradict “The report also says not-P.” A source can contain both statements. To contradict a positive claim about what a source says, the context must establish the relevant absence, for example by providing its expressly complete content, or explicitly stating that it never makes that assertion. Source silence alone does not contradict the underlying world proposition.

Completeness closes only the content expressly identified. A complete quotation of one passage does not establish completeness of the entire document, another version, or another time. To negate “S states P,” the closed content scope must match the claim's source, version, and extent. Check faithful paraphrases and equivalent assertions, not just exact word matches. A supplied complete excerpt that omits P cannot establish that the whole source never states P.

## Truth guarantees and their limits

Promotion from reported P to world P requires either a direct narrator assertion of P or an explicit narrator-level guarantee that the relevant reported proposition is true in this scenario. The guarantee must cover the source, proposition type, entities, event time, and version needed by the inference. Every report-derived world premise in a multi-source argument needs its own applicable bridge.

Prefer an exact proposition reference: “Narrator fact: The proposition ‘The violet lamp is lit at noon’ is true in this scenario.” If a report's sentence contains several conjuncts, a reference to “the statement about” one time or entity can select either a conjunct or the entire sentence. Quote the intended proposition and state that the stipulation does not address the other assertion when needed. Do not write “only P is true” when the intended meaning is merely that other propositions remain unspecified.

A guarantee inside a source's own claims is only another report unless independently stipulated. “The notice says that it is always correct” is not self-validating.

Do not confuse these distinct properties:

- **Authenticity:** This really is the named source or version.
- **Transcription fidelity:** The displayed words accurately reproduce that source.
- **Completeness:** All of the specified source content is shown.
- **Authority:** The source is official, authorized, expert, or institutionally designated.
- **Rights or licensing:** A stated permission or license determines which uses of a source are allowed.
- **Review or admission status:** A named review, approval, or admission process has occurred.
- **Proposition truth:** The particular reported content is true in the supplied world.

None of the first six properties by itself establishes proposition truth. A document can be licensed, approved, authentic, faithfully copied, complete, and wrong. An accurate transcript can faithfully record a false statement. Conversely, truth of a quoted proposition does not establish that a document is complete, permitted for use, approved, or correct in every other assertion.

A source's own claim to any of these properties remains attributed content unless independently stipulated. Even a narrator-stipulated permission, licensing, review, approval, or admission event is not a truth guarantee. Substantive review findings can be assessed only when their content and scope are supplied, under the same report-versus-narration rules as any other content. Supplying those findings does not itself promote a reported proposition to a world fact; review status alone cannot do so.

Bare “reliable,” “verified,” “accurate,” or “authoritative” is insufficiently precise when it could refer to transcription, authenticity, probability, or truth. New fixtures must state the intended guarantee. A historical ambiguous use goes to review if the reading changes its label. “Usually correct” provides no deductive guarantee for this instance. Explicitly “this report is false” does not negate every proposition in a multi-proposition report; a specific proposition must be identified or its negation separately established.

## Mixed narration and report boundaries

Within a quoted block, embedded complement, or explicitly labeled report section, retain report scope until it clearly closes. Outside it, an explicit “Narrator fact” or “In the actual scenario” marks a return to direct narration.

A period alone is not a universal reset rule. “The log says P. Q happened next” can be a continuing account or a narrator assertion. If that distinction affects the label, flag the unit instead of silently choosing the author-friendly reading. For new fixtures, make the boundary explicit with quotation marks, a stated endpoint, repeated attribution, or clear narration markers. These markers must appear in the supplied context, not only in annotation notes.

Do not let one direct fact validate its reported neighbors. If a source reports eight objects initially and narration establishes three removals and no additions, the removals are facts, but the unknown actual starting count prevents concluding that five remain. Direct narration and a disagreeing report can coexist without a world-level contradiction; a false report is possible.

## Geography and rule membership

A local universal, such as “Every marker in the courtyard is blue at noon,” applies only after the relevant marker is established to be in that courtyard at noon. Naming a marker in another passage does not establish membership. A nearby topic, common chapter, adjacent passage, source location, or author intention is not a membership premise.

Membership may follow from an explicit location statement, an unambiguous supplied containment relation, or an explicit global setting clause that places the relevant entities in the location at the relevant time. Do not import a real-world map. “The rule is discussed in the courtyard” does not limit or expand the rule's logical domain.

Being outside the domain means the rule is inapplicable, not that its conclusion is false there. A marker outside the courtyard may still be blue. A universal also does not by itself establish that any members exist.

## Time agents and persistence

Preserve the exact time interval and quantifier. “After noon,” “at noon,” and “all day” are different scopes. “Mara did not move the token again after noon” excludes later moves by Mara; it does not exclude her earlier moves, anyone else's moves, or other ways the token could change location.

A positive state at one time does not automatically persist to a later time. Support persistence only when directly stated or licensed by an explicit rule whose relevant alternatives are covered. “The token's location did not change from noon through 18:00” can license persistence. “Nobody moved it” alone may leave natural motion or an undefined movement domain unresolved; new examples should state unchanged location when that is the intended premise.

Role assignments, possession, identity over versions, and agent participation must also align in time. A morning role assignment does not identify the afternoon role holder without a supplied persistence statement. “No one exchanged roles” can exclude exchanges but does not necessarily exclude resignations, reassignment, or replacement. State that the actual role holders stayed the same when that is what the argument requires.

Use only unambiguous supplied reference links. Explicit aliases may connect an object across passages. A shared name is not sufficient if two objects, versions, or dates remain possible. Avoid inferring unique actors or single events unless the context supplies uniqueness.

For inventory arithmetic, specify that the listed additions and removals exhaust changes in counted membership and that counted item identity and category stay fixed over the interval. Define one accounting interval covering every change after the initial count up to and including the final count. Explicitly state that the final count is taken after all inventory changes at its timestamp. Apply that whole interval to every event bound, exclusion, and identity/category condition; an ambiguous “between” interval must not leave endpoint changes outside the restrictions.

When the intended calculation allows removals but no additions, state separately that no items were added anywhere in the accounting interval and that no removals occurred besides the explicitly described removal events. Excluding additions includes returning any of the same removed items. “No other beads were added or removed” is insufficient if “other” can modify the objects rather than the events. Count removed items or removal events precisely, and do not confuse the number of distinct items with repeated removals of the same item.

Place every event restriction and transition premise in the appropriate world or source-account scope. A quoted account's interval definition, no-additions rule, and removal bounds remain reported content; they must not be silently promoted to narrator facts. Do not silently use stricter persistence rules for a moving object but unstated identity or category persistence for a count. The revision 2 inventory examples make these premises explicit; they do not require inventing exotic changes in ordinary prose.

## Annotation procedure

1. Read the full supplied context and exact claim before assigning a label.
2. Mark the claim's target and all agent, time, location, and quantity restrictions.
3. Inventory direct facts separately from each attributed account; retain nested scopes.
4. Identify each required bridge, including identity, membership, persistence, and proposition truth. Cite the supplied span or record that it is missing.
5. Use all admissible scoped premises to track support for the claim and its same-target negation. Do not use lack of a derivation as a negation, omit inconvenient premises, or derive arbitrary conclusions from a conflict.
6. If only one follows, label accordingly. If neither follows, use `not_established`. If both follow, or materially different readings yield different labels, leave the semantic label unset and mark the separate disposition `review_needed`.
7. Write a short rationale naming the decisive premise or missing bridge. For `not_established`, give a compact compatible alternative when helpful.
8. Have an independent reviewer apply this contract without seeing author labels. Resolve policy disagreements before freezing new evaluation material.

A sidecar review may record `target_scope`, `evidence_spans`, `missing_bridges`, `ambiguity_reason`, and `review_status`. These are proposed review aids, not additions to the existing evaluator schema. Do not leave reasoning-critical assumptions only in these fields.

## Development examples and validation limits

[`support_scope_development.json`](../evals/support_scope_development.json) contains 30 case rows in 15 pedagogical pairs, with 29 unique original context-claim inputs. P01B and P02A intentionally reuse one anchor to connect the narration/report and world/source distinctions. Each case repeats all necessary context. Some pairs change the context; others change only the claim's target. The file exposes proposed labels and rationales. [`support_scope_review_cases.json`](../evals/support_scope_review_cases.json) supplies four deliberately unresolved examples without gold labels, illustrating when adjudication rather than a forced answer is required. Its conditional outcomes describe specific repairs, not labels for the unresolved originals.

The initial independent label-free development review assigned 29 semantic labels and held P06A for an ambiguous truth-guarantee reference. Revision 1 quoted exact propositions in both P06 rows and made inventory transitions explicit in P07, P08, and P14. A targeted recheck resolved the P06 reference issue but held P07B, P08B, and P14B for endpoint and addition/removal wording that admitted different readings. This was a newly identified ambiguity in the earlier wording, not a model result.

Revision 2 gives both members of P07, P08, and P14 the same explicit count-to-count interval and closes all addition and removal events through the final count. The P14 changes remain wholly inside Sheet B's reported account. All claims and author-proposed labels are unchanged. The final targeted recheck found no remaining material issue in these six inputs under this contract and no changed judgment for the other 24 rows. The current independent judgments agree with all 30 proposed labels, but this is development agreement, not expert gold validation. The same reviewer performed the initial review and both targeted rechecks; the later reviews were informed by earlier findings, not fresh blinded evaluations. The four review cases exposed issue and repair hints to their reviewer; that portion was not blinded. Earlier drafts and findings were preserved rather than overwritten. The [review record](../evals/support_scope_development_review.json) binds the final inputs to the current judgments and summarizes the revisions.

The examples demonstrate distinctions, not frequency, representativeness, novelty to pretrained models, statistical performance, or qualification. They are deliberately constructed after inspecting the known scope failures. Do not count them as a fresh held-out test, balance or optimize them for candidate scores, or use them to rewrite the historical trial. No model is run for this work. Structural validation checks formatting and internal references, not semantic correctness.

## Open decisions and tradeoffs

- **Pragmatic reports:** Strict report scope differs from everyday trust in routine records and some conventional NLI datasets. The benefit is a visible truth premise; the cost is more `not_established` labels. Reviewers must explicitly agree to this task policy before any new freeze.
- **Attribution across sentences:** This proposal rejects outcome-changing ambiguous scope rather than choosing a universal punctuation rule. That improves clarity but excludes some natural prose. A later natural-text evaluation needs an explicit ambiguity process and coverage accounting.
- **Factive and evidential verbs:** “Discovered,” “confirmed,” “proved,” and “verified” have context-dependent implications. This draft uses explicit truth stipulations in labeled examples. A broader contract needs reviewed lexical guidance rather than ad hoc decisions.
- **Source content versus inferred meaning:** The distinction between explicit statement, faithful paraphrase, and logical consequence needs independent reviewer testing, especially for arithmetic, presuppositions, and nested belief reports. The present examples do not settle all such cases.
- **Conflict representation:** The frozen three-label schema has no conflict or ambiguity label. This draft requires a separate adjudication record; whether future data should represent conflict directly is an unresolved schema decision, outside this work.
- **Persistence and granularity:** Restricting inference to explicit intervals avoids whole-day and cross-agent leakage but can be more literal than ordinary narratives. Reviewers should test whether practical task inputs can supply the necessary intervals without making the task artificial.
- **External knowledge:** This development contract allows language comprehension and logical inference, not new factual premises. Any future real-world or specialist task must separately specify admissible background knowledge, source scope, and expert review. No synthetic success warrants claims about religious or scholarly truth.

The next step is to freeze the intended task policy before designing genuinely new independently reviewed evaluation cases. This proposal supplies neither an automated annotation validator nor a source-truth detector, and does not qualify either pretrained candidate or authorize corpus admission.

## Source record

Read-only repository references:

- [Paired support results](PAIRED_SUPPORT_RESULTS.md), especially Independent label review and unresolved scope and Next useful work.
- [Paired support label review](../evals/paired_support_label_review.json), including reviewer rationales and ambiguity flags.
- [Original paired support cases](../evals/paired_support_cases.json), for the exact contexts and claims identified by that review.

The case file was inspected for diagnosis. Its wording and labels were not copied into the new development examples or edited. The original predictions, reported scores, and qualification conclusion remain unchanged.
