# Bounded Hindi and Gujarati text support

The default local rule-based reasoner now has original Hindi and Gujarati versions of its three existing practical plans: household cleaning, wardrobe organization and a business-partner disagreement. It also has language-matched abstention, refusal and source-limit messages. No model download, provider call or corpus is needed for these fixed responses.

## Try it

With JACE installed, use the ordinary `ask` command or type one of these questions in the conversation console. The authenticated HTTP `/v1/think` and selected-context answer paths use the same local reasoner. Existing API fields and confirmation/identity bindings are unchanged.

- Hindi cleaning: `jace ask 'घर की सफाई कैसे करूँ?'`
- Hindi wardrobe: `jace ask 'कपड़ों की अलमारी व्यवस्थित कैसे करूँ?'`
- Hindi business: `jace ask 'व्यापार के साझेदार से मतभेद कैसे सुलझाएँ?'`
- Gujarati cleaning: `jace ask 'ઘરની સફાઈ કેવી રીતે કરું?'`
- Gujarati wardrobe: `jace ask 'કપડાંનું કબાટ કેવી રીતે ગોઠવવું?'`
- Gujarati business: `jace ask 'વ્યવસાયના ભાગીદાર સાથે મતભેદ કેવી રીતે ઉકેલું?'`

The translations preserve the original plans' safety and consent conditions: hygiene and product instructions, checking ownership, agreement before donations or business commitments, and qualified advice for legal rights. They are application prose, not translations of scripture. They do not add source records, establish religious authority or perform actions.

## How selection works

A small script cue selects Hindi for Devanagari letters or Gujarati for Gujarati letters. This is not language detection: Devanagari is also used by other languages. Requests containing both scripts fall back to English. English is unchanged when neither script is present. Romanized Hindi/Gujarati, arbitrary paraphrases and requests to translate arbitrary text are not supported.

A small set of exact normalized words selects one of the three templates. A few explicit Gujarati inflections and Hindi/Gujarati synonyms are recognized, for example `કપડાંને ગોઠવવા માટે માર્ગદર્શન આપો.` and `कारोबार के भागीदार से अनबन कैसे सुलझाऊँ?`. There is no stemming. New business aliases require a short business-partner-conflict phrase at the start of the request, such as `વેપારમાં ભાગીદાર સાથે મતભેદ` or `व्यापार के साझेदार से अनबन`. This deliberately declines other word orders rather than attaching business words to life or sporting partners elsewhere in the sentence. The ambiguous new cupboard alias `કબાટની` is not supported by itself: say explicitly that the request concerns clothing.

Requests using a newly added alias also abstain on listed conjunctions or more than one punctuation-separated clause, even when that is overly cautious. The discarded cupboard alias remains an abstention cue for such compounds. Explicit book/toy cupboard words do not select the clothing plan. These remain limited lexical checks, not a guarantee that every unsupported subject or compound is recognized. An otherwise matching subject followed by an unsupported instruction, such as asking for a poem about the dispute, can still select the fixed practical plan. Generic partnership, clothing-folding requests and unlisted wardrobe paraphrases can still abstain. Listed negations, software/database terms and multiple recognized scenarios cause abstention. These checks do not understand arbitrary negation, constraints, compound questions or intent. The structured cleaning/wardrobe/dispute planners remain separate and English-only. Fixed English retrieval terms associated with a recognized template may retrieve existing principles; this is not cross-language semantic search.

## Source and privacy boundaries

- Original source passages, names, locations, language labels and integrity references remain verbatim. No source is silently translated or relabeled as Hindi/Gujarati.
- The six built-in records remain unverified sample summaries. An answer with no reviewed passage says so in the selected language.
- Review/license flags in an external corpus are still declarations, not independent scholarly or legal verification.
- Saved preferences are not interpreted by the fixed plan. A localized notice identifies that limit when memories are supplied.
- Memory learning remains opt-in and retains its existing limited English extraction cues. This change does not silently broaden automatic memory extraction.
- API metadata, error messages, seven-perspective metadata, other screens and structured planners are not fully localized.

## Safety and model limits

Listed Hindi/Gujarati harm or weapon terms are conservatively rejected by the existing engine gate before any configured reasoner is called. Some benign prevention questions will also be rejected. This is a narrow lexical boundary, not a semantic multilingual safety classifier. Unlisted spellings, obfuscation and general harmful intent are not comprehensively recognized. Do not use this prototype to authorize real-world business, legal, financial, medical or physical actions.

The optional HTTP model adapter has not gained a trained multilingual model or guaranteed language-matched output. If its output fails validation, the existing local fallback can use these fixed templates. No real-provider evaluation was run.

## Voice and qualification

The voice selector only requests a browser recognition/voice language; it does not translate text. Real Hindi/Gujarati recognition, pronunciation, voice availability and media permissions remain untested. Browser, device and service permissions are still required. Synthetic loopback tests are not browser or audio qualification.

Tests use original application fixtures, synthetic users, ephemeral databases and local loopback only. They cover the six plans, normalized text, conservative abstention/refusal, unchanged English behavior, exact source preservation, API/CLI output, selected-context binding and no automatic learning/provider calls. They are development regressions, not held-out multilingual reasoning quality, native-speaker acceptance, Jain scholarly review or Agama training.
