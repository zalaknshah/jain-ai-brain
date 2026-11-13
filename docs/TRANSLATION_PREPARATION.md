# Private source-linked translation preparation

This offline tool creates review work, not translations or a training dataset.
It verifies a complete local source digest and explicit UTF-8 byte spans, retains
exact excerpts and required provenance, then creates blank Gujarati, Hindi and
English draft/reviewer slots. It calls no model, sends no network requests and
never admits the packet to runtime, training or public release.

Prakrit is not Sanskrit. Script alone does not identify a language. A mixed
edition can contain Prakrit root verses, Sanskrit renderings, modern Hindi or
English translations, commentary and indexes. Do not treat these layers as one
canonical passage. Before drafting, a qualified reviewer must identify each
layer, compare OCR with the original scan, record corrections separately and
check edition-specific translation/training rights. Preserve attribution and
conditions; a public code license does not relicense the text. JLOR AI
translations remain unverified, and the SARIT Sanskrit source is not a Prakrit
corpus. A new translation is a draft until qualified bilingual and subject-matter
review has checked meaning, omissions, doctrine, tradition and uncertainties.

Run only with authorized local files:

```sh
python scripts/prepare_translation_review.py SOURCE SPECIFICATION NEW_PRIVATE_OUTPUT
```

The specification must contain `source_sha256`, `metadata`, and `spans`.
Metadata requires work, edition, source_url, rights_basis, rights_notice,
attribution, declared_source_language, text_role and locator (all nonempty
strings). Use explicit unverified/mixed declarations when appropriate. Each
span requires id, byte_start, byte_end (exclusive), and locator. No ranges or
languages are guessed. The source binding covers exact source identity,
span, excerpt digest and provenance; it is not a signature, reviewer identity
check or semantic certification. Future draft review must also bind the actual
translation text: the source binding alone does not approve changed drafts.

Outputs contain source excerpts and belong in private storage, never the public
code repository. The output is created exclusively (no overwrite) with mode 0600
on POSIX. This does not qualify Windows ACLs or guarantee privacy against the
same user, administrators or other host mechanisms. Choose an appropriately
protected directory. Original source files are unchanged. stdout contains only
counts and closed admission flags, not excerpts. All training/release flags
remain false even when provenance declarations sound permissive.

A useful workflow is: verified local source -> mixed-page review -> verified
root passage/OCR correction -> independently reviewed translation drafts ->
work/edition-separated evaluation -> distinct training admission and release
review. This tool implements only the first preparation step; it does not train
a model or confer safe robot decision-making.

Validation on 2026-11-13: nine focused synthetic tests passed; the final full
suite ran 815 tests, 761 passed and 54 optional skips. Independent review found
and verified correction of caller-owned metadata/span aliasing. A private local
smoke test prepared one mixed-edition page into three blank language slots;
its source excerpt and generated packet are not part of this public code change.
No translation quality, OCR fidelity, training or robot qualification follows.
