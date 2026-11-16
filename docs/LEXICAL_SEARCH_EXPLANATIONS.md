# Lexical search explanations

`CanonicalStore.search_explained(query, limit=5)` is an additive Python diagnostic API. Each `LexicalSearchHit` contains the original `entry`, a sorted tuple of distinct normalized `matched_terms`, ordered `(field_name, matched_terms)` pairs in `field_matches`, and `score` (the number of distinct matched terms). The method uses existing search ranking, stable ID tie-breaking, limits and fail-closed scan budgets. Existing `search` callers and serialized API responses are unchanged.

This allows a reviewer to distinguish a match in `principle` from one appearing only in a title, tag, guidance or other indexed metadata. Tags retain their zero-based indexes. Original source text, provenance, integrity references and review declarations are not rewritten. Explanation terms are normalized lexical tokens, not verbatim source offsets or quotations.

Repeated words and matches across multiple fields count once. Fields not indexed by search, including language and license, do not acquire search relevance. Hindi/Gujarati tokens use the existing Unicode tokenizer; there is no translation, stemming, semantic retrieval, entailment or multilingual quality claim.

The API does not independently verify a passage, authorize source admission or training, or establish that a retrieved passage supports an answer. It does not alter rights, scholarly or bilingual review, runtime/publication or robot gates. No corpus is added. UI, HTTP and CLI presentation are not implemented by this change.
