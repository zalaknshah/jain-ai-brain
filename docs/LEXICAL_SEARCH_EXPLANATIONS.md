# Lexical search explanations

`CanonicalStore.search_explained(query, limit=5)` is an additive Python diagnostic API. Each `LexicalSearchHit` contains the original `entry`, a sorted tuple of distinct normalized `matched_terms`, ordered `(field_name, matched_terms)` pairs in `field_matches`, and `score` (the number of distinct matched terms). The method uses existing search ranking, stable ID tie-breaking, limits and fail-closed scan budgets. Existing `search` callers and serialized API responses are unchanged.

This allows a reviewer to distinguish a match in `principle` from one appearing only in a title, tag, guidance or other indexed metadata. Tags retain their zero-based indexes. Original source text, provenance, integrity references and review declarations are not rewritten. Explanation terms are normalized lexical tokens, not verbatim source offsets or quotations.

Repeated words and matches across multiple fields count once. Fields not indexed by search, including language and license, do not acquire search relevance. Hindi/Gujarati tokens use the existing Unicode tokenizer; there is no translation, stemming, semantic retrieval, entailment or multilingual quality claim.

The API does not independently verify a passage, authorize source admission or training, or establish that a retrieved passage supports an answer. It does not alter rights, scholarly or bilingual review, runtime/publication or robot gates. No corpus is added. UI, HTTP and CLI presentation are not implemented by this change.

## Stateless CLI diagnostics

`jace explain-search 'your query' --allow-local-disclosure` searches only built-in sample records. It does not instantiate the engine, open its database, load memories, call a model/provider or honor an environment-configured corpus. The samples are not reviewed scripture.

For an already permitted external canonical corpus, specify `--corpus /absolute/path/to/manifest.json`. Existing descriptor-safe source reading, corpus bounds and admission checks apply unchanged. Missing secure IO support (including unsupported platforms) fails closed; this command is not a Windows source-reader workaround. An empty explicit corpus path is an error, not a sample fallback. `--limit` accepts 1 through 100.

The required `--allow-local-disclosure` acknowledges that source IDs and normalized matched query terms will appear on stdout, including per-field names and lexical scores. It does not grant publication or source/training rights. Queries and paths supplied on the command line may be retained in shell history or visible in process arguments. Use only nonsensitive command-line values in shared environments. The report omits passage excerpts, source metadata and filesystem paths, but its terms/IDs are not anonymized. It is not a safe public report of private source content.

Retrieval validation failures, including malformed limit values, return exit status 2 and a generic error before any report is written. Output is serialized and bounded to 1 MiB before writing. An output-device write or flush failure returns a nonzero process status with a generic incomplete-output warning, but may leave partial JSON already written. Python may replace the requested exit status during shutdown if flushing fails again (for example, status 120 instead of 2); consumers must discard output on nonzero exit and not treat redirected output as an atomic file. This sanitization covers retrieval validation and output IO, not arbitrary interpreter failures or ordinary argparse errors for unknown options. Command-line values should therefore remain nonsensitive. Exit status 0 means a diagnostic report was produced, not that sources support an answer. `semantic_support_verified` and `runtime_admitted` remain false. Native Windows, browser/UI and real-source acceptance are not established by the synthetic CLI tests.

### Query input through stdin

`jace explain-search --stdin --allow-local-disclosure` accepts a UTF-8 JSON object containing exactly `{"query":"your query"}` on standard input instead of a positional query. Exactly one input mode is required. This avoids placing the query in the JACE process arguments; it does not make stdin secret storage. Shell construction, input files, terminal echo, other processes, logs and the diagnostic output can still disclose content. Prefer an appropriately protected input source rather than typing sensitive data into a shell command.

The disclosure flag is required before input is read. Input reads at most 65,537 bytes and rejects more than 65,536; duplicate JSON keys, unknown fields, malformed UTF-8/JSON and nontext queries are rejected without echoing the payload. Existing query-character/term and source/output limits remain unchanged. The operator must close or finish the input stream: this synchronous read is byte-bounded, not time-bounded, and may wait for input/EOF. No file is written by this input mode. `--corpus` remains explicit and still uses the unchanged secure reader; no private content, source rights or runtime admission is inferred from using stdin.

### Passage-only retrieval

Use `jace explain-search 'your query' --passages-only --allow-local-disclosure` (or combine `--stdin` with `--passages-only`) to rank only lexical matches in the `principle` field. Titles, tags, guidance and other metadata cannot increase scores or occupy the top-k results in this mode. Filtering happens before ranking and limiting, so a metadata-only hit cannot hide a lower-ranked matching passage. Explanations then list only matched principle terms and the report includes `search_fields: ["principle"]`.

The Python methods `CanonicalStore.search` and `search_explained` accept keyword-only `passages_only=True`; the value must be a boolean. The omitted/false default retains the prior ranking and CLI report shape. Stable ID tie-breaking, distinct-term scoring and Unicode normalization remain unchanged. Both modes still account for full record fields in scan budgets and fail closed rather than return partial results if a later record exceeds a limit.

“Passage” means the existing principle field, which may contain an unverified sample summary rather than a verified quotation. Exact lexical overlap does not prove relevance, entailment, doctrinal accuracy, translation quality or answer support. No source record, review declaration, source-reader requirement, disclosure condition or runtime/training gate changes. This filter does not add semantic retrieval, cross-language search or new corpus material.
