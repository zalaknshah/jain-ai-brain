# Offline passage review before source export

This workflow prepares a **review-only** package, lets a person inspect individual passages, and exports approved **records** only after a separate explicit confirmation. It is a local review aid, not an authenticated scholarly or legal approval system. Development and tests use original synthetic text, not collected religious materials.

**A runtime export retains complete original backing source files. Unapproved text outside selected passage ranges can remain in those files. The workflow filters admitted records, not file contents. Keep the package, HTML, decision report and export private. Nothing is automatically uploaded, shared, trained on or activated in a runtime.**

Before choosing files, `python scripts/review_sources.py capabilities` prints read-only platform prerequisites. Native Windows source IO is not implemented; preparation/export fail closed before reading inputs on unsupported platforms. This check does not grant browser file access or verify actual filesystem support. See [platform details](SOURCE_PLATFORMS.md).

## Three separate steps

### 1. Prepare a private draft

Use explicitly chosen UTF-8 text/Markdown files whose copying and review are permitted. Supply the work, source, language, license and location metadata you want the reviewer to inspect. The preparation step does not establish that those declarations are true. If different files need different editions, locations or licenses, prepare separate units instead of applying one inaccurate declaration to all of them.

The `prepare` command in `scripts/review_sources.py` requires explicit copy confirmation. It creates a new private directory containing a `bundle.json`, digest-named original source files, and a self-contained `review.html`. The source bytes and end-exclusive UTF-8 passage ranges are validated without rewriting interior whitespace. Chunking is a bounded convenience, not verse, sentence or language-aware scholarly segmentation.

For example, with an original synthetic local file:

```sh
python scripts/review_sources.py prepare ./reviewed-fixture.txt \
  --output ./draft-review --work "Original synthetic fixture" \
  --source "Operator-authored fixture" --language en \
  --license "Operator owns this fixture" --location "Fixture section 1" \
  --confirm-copy
```

Omit `--confirm-copy` to read the reminder without reading or copying input files. The target parent must exist; the new output directory must not already exist.

The draft uses `jace-source-review-v1` and literal `verified: false`. It is deliberately rejected by the normal runtime corpus loader. Do not rename fields or fabricate approval to bypass review. Preparing the draft does not modify `JACE_CANONICAL_PATH`, user memories or model configuration.

### 2. Review passages and save decisions locally

Open the generated HTML in a trusted local browser. It needs no remote assets or API. It displays one complete passage at a time, its metadata, source digest and byte span. Every passage starts **pending**. Choose approve, reject or pending and enter a note; approval and rejection require a nonblank note. Identify the reviewer before saving the report. These are self-declarations, not authenticated identity, demonstrated qualification or independent rights checks.

If the source or metadata is wrong, reject it and rebuild a corrected draft. Notes do not silently edit the text, fix metadata or authorize a different edition. A review decision binds the displayed passage, normalized metadata, original parsed record declarations, and exact source bytes/range. Changing a declared metadata string, even its normalized-away whitespace, invalidates the decision. JSON key order and serialization whitespace outside values are ignored; neither is scholarly evidence.

A separate default-unchecked confirmation is consumed before a local report download. Changing the reviewer or any decision/note invalidates that confirmation. Download failure is not automatically retried. The report contains reviewer identity and notes. It does not automatically copy source passages, but notes can contain any text the reviewer enters; keep it private too. The complete report is capped at 2 MiB of UTF-8 bytes, including JSON formatting. Individual note limits do not guarantee the total fits; shorten notes if the screen rejects the aggregate size. This is checked before confirmation and again before download, without truncation. Browser-managed download permissions are outside the renderer's control.

The generated HTML itself contains the reviewed passages and remains on disk. Clearing the screen or leaving the page resets in-memory choices, notes and reviewer fields; it does not erase the saved HTML, source files, downloads or browser/OS remnants. The page does not use browser storage, send files, execute source markup or call a model. Actual browser/download behavior remains unverified; Node fixtures exercise the code paths.

### Resume an interrupted review explicitly

To continue from a previously saved report, choose its local JSON file in **Resume a saved review report**. Selecting a file does not read it. Check the separate replacement confirmation and click **Load report for review** to read that one file. A successful load replaces this page’s current reviewer, notes and decisions, so save any work you want to keep first. This is an in-memory replacement, not a merge or an automatic save.

Import requires a nonempty report no larger than 2 MiB, strict UTF-8 and JSON, the exact draft revision, every expected record ID and matching record revision exactly once, supported fields and choices, and bounded valid reviewer/notes. Duplicate JSON keys, malformed or mismatched reports, and unreadable files fail without changing the current review. Reviewer names must fit one line; imported CRLF note line endings become LF for the browser textarea. No other text is silently truncated. Notes render as text, not markup.

Read/replacement confirmation is bound to the selected file, consumed before reading, and invalidated by file changes, review edits, navigation or clearing. A slow read cannot replace edits or a newer import. Loading never restores save consent: inspect the restored choices and explicitly confirm any new save. The imported reviewer name and decisions are unverified declarations, not authenticated identity, scholarly review, permission or rights. Import does not authorize export, runtime activation, training or sharing.

The report file remains on disk, and browser-managed file selection/read behavior still needs real-browser testing. Clearing the page resets the selected file and in-memory state; it does not delete saved reports or source files.

### 3. Explicitly export approved records

The separate `export` command reads the draft and decision report through bounded, descriptor-safe local IO. It requires final export confirmation, a declaration of qualified review, and a declaration that the intended local retrieval use is permitted. Those assertions do not verify legal rights or scholarly accuracy and do not grant permission to share, train on, commercially reuse or redistribute the source.

The report must cover every draft record exactly once with its matching revision. Duplicate IDs, extra/missing records, changed source bytes/spans/metadata, mismatched draft revisions or malformed decisions fail closed. At least one record must be approved. Pending/rejected records are not runtime-admitted.

**Every backing file referenced by an approved record is copied in full, including unapproved text elsewhere in that file.** A digest of the original source cannot be preserved by silently cutting out the rest of the file. If retaining those bytes is inappropriate, do not export that package. Prepare a separately licensed/reviewed source unit and review it again instead.

The exporter prints the whole-file warning before any export, even when all flags are supplied. Without all three flags it reads and exports no files:

```sh
python scripts/review_sources.py export \
  --manifest ./draft-review/bundle.json \
  --decisions ./jace-source-decisions.json --output ./approved-bundle \
  --confirm-export --declare-qualified-review \
  --declare-rights-for-local-retrieval
```

Use those declarations only when they are true for the intended use, not simply to make the command proceed. `--confirm-export` explicitly includes complete backing files and their unapproved bytes.

The resulting ordinary exact-source bundle marks only the approved records as reviewed declarations. It preserves their exact passages and metadata. Reviewer notes/identity remain in the separate decision report rather than being silently inserted into runtime citations. No export is automatically activated, published or used for training.

## Integrity and privacy boundaries

- Source/range integrity uses the existing [exact-source protections](SOURCE_INTEGRITY.md): bounded strict UTF-8/JSON, duplicate rejection, pinned directory descriptors, no symlinks or hard-linked/nonregular source files, mutation checks and actual-byte hashing.
- Draft preparation and final export use private mode-0700 directories and mode-0600 files, same-parent staging and atomic no-overwrite publication. Existing destinations are never replaced. Linux/POSIX requirements and the earlier same-user race/power-loss limitations remain; this is not an encrypted store or hostile-privileged-filesystem sandbox.
- Export uses an admitted source-byte snapshot after validating decisions, never a later unvalidated live reread. A matching digest establishes byte identity, not who wrote the file or whether its attribution/license is authentic.
- The HTML embeds escaped data and renders it as text, with restricted connections/assets. Source text cannot intentionally become instructions to a provider because this workflow has no provider path. That does not make the source trustworthy for later model use.
- Review reports are not signed attestations or tamper-proof human decisions. Someone with write access can fabricate a new report or change the application. Fingerprints catch stale/mismatched content; they do not authenticate a scholar, prove consent or replace permission checks.
- Only the approved record set is filtered. Whole retained files, the private HTML, report notes and local backups may contain more information. None is safe to publish merely because export succeeded.

## Evidence and remaining gates

Use the command help for exact options. The checked-in regression commands are:

```sh
PYTHONPATH=src python -m unittest discover -s tests -p 'test_source_review*.py' -v
PYTHONPATH=src python -m unittest discover -s tests -p test_review_document.py -v
```

The backend, renderer/DOM and cross-layer integration tests use original synthetic sources, temporary directories and mocked browser interfaces. The integration executes the actual generated HTML's script in a Node DOM harness, captures its bound decision JSON, and exports/loads that exact report through the Python runtime. They do not use an actual browser or download manager. The resume integration reloads a bound synthetic report through the actual embedded JavaScript, explicitly saves it again, and checks the resulting bytes through the exporter/runtime. Tests cover runtime draft rejection, source/metadata/span binding, malformed and stale decisions, explicit confirmation, approved-record subsets with retained unapproved backing bytes, no-overwrite/private modes, failed writes and source changes, literal markup rendering, consumed download consent and no network/storage behavior.

Still needed for a real religious corpus: verified rights for the intended use and retained backing files, authentic editions/translations, qualified independent source/interpretation review, accurate page/verse provenance and reviewed retrieval/answer evaluation. This workflow supplies none of those facts automatically.

The resume regression additionally covers explicit file-read consent, no-read selection, UTF-8 and duplicate-key rejection, reordered but exact record sets, CRLF note normalization, failed reads, file-size changes, repeated clicks, and asynchronous completion after edits, clear, page lifecycle events or newer imports. Before applying a read, the page also rechecks the selected file and visible reviewer, decision and note, so silent changes during the read cancel replacement without overwriting new edits. Restored checkbox/button state alone cannot authorize reading or saving. These are controlled Node File/DOM fixtures, not verification of browser file pickers, native form restoration or downloads. The checks do not detect silent changes restored between observations or protect against malicious scripts/extensions.
