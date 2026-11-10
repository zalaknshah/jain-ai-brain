# Source-first local responses

The local rule-based fallback now gives explicit English source questions
priority over practical templates. Asking for an exact verse about cleaning must
not silently become an authored household-cleaning plan. The harm gate still
runs first. This change does not replace or qualify an external model.

Recognized cues include requests to cite, quotations, reviewed passages, textual
evidence, source-backed answers, and verse/passage requests with textual-source
context. Ordinary mentions of ahimsa or aparigraha can still select an authored
practical plan. This is a bounded English cue recognizer, not general intent,
negation, paraphrase or multilingual understanding. Mixed requests and unfamiliar
wording may be missed or over-selected; held-out routing outcomes must be
reported, not treated as proof of general comprehension.

Narrow exclusions cover parking/traffic/speeding citations and explicit phrases
such as "I am not asking for a scripture quotation". Only that phrase is masked;
a separate positive citation request still counts. These are not general
negation rules. Navigation proposals now require an explicit leading movement
command, rather than any mention of movement in an explanation or quotation.
Recognized source requests never produce such proposals, including through the
HTTP adapter's shared action mapper. Other command phrasing may receive no
proposal; existing proposals still require confirmation.

Without an eligible reviewed record, the response leads with its inability to
give a source-grounded answer. Built-in unverified samples are never promoted to
quotations. An explicit request to invent a citation is not presented as authentic
source evidence. No navigation or other action is proposed by this source route.

With eligible records, the response displays at most two exact excerpts of 600
characters, identifying work, source, location, language and supplied edition.
It reports undisplayed eligible records and truncation. Leading whitespace can
be omitted, but internal whitespace is preserved and source-bound byte ranges
refer to the actual displayed excerpt, not an undisplayed suffix. Eligibility
uses the existing citation-record checks; invalid or ambiguous collections fail
closed. At most five input records are accepted. Source text remains untrusted
data and its embedded instructions are not executed.

**Retrieval is not an answer.** The fallback explicitly does not infer that an
excerpt answers the question, reconcile contradictions, or validate a doctrinal
interpretation. Irrelevant reviewed text may still be retrieved and displayed.
Review, licensing and edition fields are declarations, not authenticated facts.
A structurally valid exact-source reference alone cannot recheck a file; an
engine-admitted bundle must have separately checked its backing bytes. Direct
library callers must not forge admitted records or treat these checks as a
process sandbox.

This behavior was developed using original synthetic records. It admits no
religious corpus, trains no model, performs no source acquisition and establishes
no scholarly or doctrinal correctness. The practical templates, semantic answer
support, sevenfold analysis, and multilingual intent still need separate work.
