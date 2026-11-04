# Source IO platform prerequisites

Exact-source reads and private source-bundle publication do not currently have a native Windows backend. The application deliberately fails closed instead of replacing descriptor-safe IO with ordinary pathname reads or check-then-rename publication. A native Windows attempt during November 2026 testing reached this guard; it did not establish working Windows source import or export. Browser access restrictions are separate and must not be bypassed to test this code.

## Read-only check

Run either command before choosing source files or an output directory:

```sh
python -m jace.cli source-capabilities
python scripts/review_sources.py capabilities
```

Both print JSON describing the current Python/OS primitives. They do not instantiate the cognitive engine, load a corpus, create a database or staging directory, inspect user paths, call a model, or contact a service. No configuration or permissions are changed. Exit code zero means the report was produced, **not** that source operations are available; inspect the two `prerequisites_available` fields.

- External source reads need POSIX descriptor-relative `open`/`stat`, no-follow and directory flags, no-follow stat support, and descriptor-based directory enumeration.
- Private publication additionally needs descriptor-relative create/remove operations, `fchmod`, `fsync`, Linux and libc's `renameat2` symbol. The existing operation must still successfully execute `RENAME_NOREPLACE` on the actual target filesystem.
- The fixed packaged six-sample path does not require this external source backend. The capability command does not load or validate those samples, and they are not a reviewed Agama corpus.

These are **prerequisite checks**, not a filesystem self-test. A reported symbol can exist while the kernel or target filesystem rejects it. Permissions, mount behavior, races and IO failures remain checked during each real operation. The final no-overwrite syscall and all source hashing/span checks stay in place; there is no unsafe fallback.

Confirmed exact-source building, review-draft preparation, review export and low-level bundle publication now check the known prerequisites before reading source/decision files or creating staging output. Missing confirmation still stops first. Unsupported platforms therefore fail early rather than reading sources and discovering a known publication limit later. A platform can permit reads but not publication, such as POSIX systems without the Linux publisher.

## What Windows parity would require

A future Windows implementation needs a separately reviewed native backend and native adversarial tests. Removing the POSIX guard, copying sources with `shutil`, or using `Path.resolve()` and `is_symlink()` before `open()` would not meet the current integrity contract.

The required design includes:

1. Pinned, handle-relative traversal and enumeration, rejecting relevant reparse points, junctions, symlinks, devices and nonregular files at every component, not only the final filename.
2. Handle-based identity, link-count, bounded-size and mutation checks, with strict Windows rules for drive and UNC roots, drive-relative paths, device namespaces, alternate data streams and normalization aliases.
3. Private access-control lists from creation, rather than treating Windows `chmod(0600/0700)` as POSIX privacy.
4. A documented atomic no-overwrite publication primitive, same-volume staging, owned-handle cleanup and honest handling of uncertain outcomes. Existing targets must remain untouched under concurrent creation.
5. Native tests for reparse ancestors, hard links, replacement races, ACL inheritance, concurrent publication and filesystem-specific failures.

No native Windows backend is supplied by this preflight. Linux source operations retain their existing limits: trusted private output parents, no full defense against a hostile same-user or privileged filesystem writer, and no blanket crash-durability guarantee. See [source integrity](SOURCE_INTEGRITY.md) and [private review/export](SOURCE_REVIEW.md). Rights, qualified review, source authenticity and semantic correctness remain separate requirements.

## Verification scope

The tests exercise runtime feature reports, simulated Windows/non-Linux cases, missing libc symbols, every publication entry point, no-engine/no-file CLI behavior, and a final filesystem-operation rejection after preflight succeeds. Simulated platform tests are not native Windows qualification. Existing synthetic exact-byte, mutation, private-mode and no-overwrite regression tests remain applicable.
