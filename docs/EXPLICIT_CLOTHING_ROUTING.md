# Explicit clothing-inventory requests

The local rule-based fallback now recognizes a small English grammar for clothing organization and keep/review questions. It returns the existing unchanged wardrobe plan, including ownership/consent, repair/reuse, uncertainty, source limitations and the warning that fewer possessions are not automatically better. It does not choose individual items, transfer belongings, purchase anything, learn preferences or interpret a private inventory.

Supported clothing nouns are clothes, clothing, shirts, jackets, trousers and sweaters. Examples:

- `Sort my shirts.`
- `How should I organise my clothes?`
- `How can I decide what jackets to keep?`
- `How should I decide which of my sweaters to keep?`
- `I have too many shirts and jackets in my drawers. How can I decide what to keep without buying more?`

The organization form allows organize/organise/sort/declutter/tidy followed by “my” and one listed noun, optionally prefixed by “How can/should/do I”. Decision forms require that question prefix. The inventory form begins “I have too many” or “I have a lot of”, accepts one or two listed clothing nouns and optional “in [my] drawers”, then exactly the keep-decision question, optionally “without buying more”. A single final period, question mark or exclamation mark is optional. Casing is normalized; this is not stemming, paraphrase recognition or a language model.

Extra qualifiers, clauses, creative/translation requests, ambiguous ownership and unrecognized wording in this clothing route abstain instead of silently dropping instructions. Recognized clothing-organization/keep cues can also make a previously recognized compound request abstain, rather than select only its cleaning or dispute portion. Existing software exclusions and the engine harm gate remain unchanged, including conservative refusals for harm-prevention wording. No new Hindi/Gujarati routing or translations are added. Some perfectly reasonable phrasings still fall back.

Original synthetic tests cover accepted forms and negative/compound cases, unchanged original three scenarios, local-only engine behavior and preserved harm refusals. The separate readiness diagnostic is still a same-author template-string observation, not semantic understanding, independent generalization, Jain doctrine, qualified scholarly review or real-source grounding. No source corpus is added and unverified samples remain unverified. The selected test run performs no model training or real model invocation.
