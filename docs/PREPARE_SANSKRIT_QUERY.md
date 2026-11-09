# Preview a Sanskrit query from Devanagari or Gujarati script

This optional helper converts explicitly declared Sanskrit fragments to Latin IAST for review. It makes the private source-study workflow easier to use when a Sanskrit fragment is typed in Devanagari or Gujarati script. It does not translate Hindi or Gujarati questions, detect language, explain Jain doctrine, correct spelling or establish relevance to any source.

## Preview only

After installing JACE, run:

```sh
jace-prepare-study-query --stdin < /path/to/your/local/query.json
```

The input JSON has exactly two fields:

```json
{"input_language": "sa-Deva", "text": "जीव अजीव"}
```

For the same Sanskrit words typed in Gujarati script:

```json
{"input_language": "sa-Gujr", "text": "જીવ અજીવ"}
```

Both produce the previewed query `jīva ajīva`. The original input remains visible beside `suggested_request` and an explicit limitation notice. Review it before separately choosing to copy `suggested_request` into the existing source-study workflow. The enclosing preview is intentionally not accepted as a source-study request. There is no automatic search, file reading, copying, persistence, network connection, model call, engine construction or source opt-in.

Existing [private study requirements](PRIVATE_SOURCE_STUDY.md) are unchanged: the exact approved source/preparation and per-invocation licence/source/purpose declarations remain necessary. Search still requires at least two query terms and sufficient source overlap. A prepared query can abstain or retrieve irrelevant text. No real-source or relevance result is claimed by these synthetic spelling checks.

## Supported orthography and limits

- Use `sa-Deva` for Sanskrit in Devanagari, or `sa-Gujr` for Sanskrit in Gujarati script. `hi`, `gu` and other labels are rejected. The label is the caller's declaration; the helper cannot verify that a string is actually Sanskrit.
- The explicit classical subset supports independent vowels, consonants, vowel signs, virama conjuncts/final consonants, anusvara (`ṃ`), visarga (`ḥ`) and internal avagraha (ASCII apostrophe). Vocalic vowels are `ṛ`, `ṝ`, `ḷ` and `ḹ`.
- Inherent `a` is preserved. For example, `कमल` becomes `kamala`, not Hindi `kamal`. There is no schwa deletion, translation, sandhi splitting, Sanskrit validation or ambiguity resolution.
- Space, tab, CR/LF, nonbreaking spaces and danda/double-danda become word boundaries. The output collapses boundary runs to a single space without joining words. Other punctuation is rejected.
- Mixed scripts, Latin text, digits, nukta letters, Vedic accents, candrabindu, joiners and unlisted regional letters are rejected rather than guessed. Malformed dependent-vowel/virama/mark sequences are rejected; this is an orthographic subset, not a grammar checker.
- Input is bounded to 4 KiB JSON and 1,024 text characters. A generated Latin query longer than the existing source-study limit of 512 characters is rejected without truncation. Unknown/duplicate fields, malformed UTF-8/JSON and unsupported content return a generic rejection, exit status 2 and no partially prepared query.
- The helper writes only its JSON preview to stdout. Your request file, shell history, redirection or terminal may retain input/output; the helper does not manage those copies.

The implementation is a separate standard-library-only module so importing or invoking it does not import JACE's engine, provider, database or private source module. No corpus, trained model or new dependency is bundled. Tests use original words and orthographic combinations, not scripture passages. These checks do not qualify native-speaker usability, general Hindi/Gujarati understanding, doctrinal reasoning, browser/audio or deployment.
