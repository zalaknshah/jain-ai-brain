"""Bounded, local exact-source bundles.

A digest pins bytes, not authorship, licensing, scholarly review or entailment.
Review and rights metadata are operator declarations. Descriptor-relative reads
and stat checks detect ordinary substitutions/mutations; they are not a defense
against a privileged writer able to change files and falsify filesystem state.
Publication requires Linux renameat2(RENAME_NOREPLACE); unsupported systems fail
closed rather than using a check-then-rename overwrite race.
"""
from __future__ import annotations

import ctypes
import errno
import hashlib
import importlib.resources
import json
import math
import os
import re
import secrets
import stat
import sys
from contextlib import AbstractContextManager
from pathlib import Path

from .model_output import checked_text, strict_json

FORMAT = 'jace-source-bundle-v1'
REVIEW_FORMAT = 'jace-source-review-v1'
MAX_REVIEW_HTML_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_SOURCES = 32
MAX_SOURCE_BYTES = 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 256
MAX_PASSAGE_CHARS = 20000
MAX_PASSAGE_BYTES = 65536
MAX_TAGS = 32
MAX_JSON_DEPTH = 32
_READ_CHUNK = 65536
_DIGEST = re.compile(r'[0-9a-f]{64}\Z')
_PASSAGE_CONTROLS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]')
_REQUIRED = frozenset({'entry_id', 'title', 'guidance', 'source', 'work', 'language',
                       'location', 'license', 'verified', 'source_ref'})
_OPTIONAL = frozenset({'edition', 'tags'})
_TEXT_LIMITS = {'entry_id': 128, 'title': 500, 'guidance': 4000, 'source': 1000,
                'work': 1000, 'language': 64, 'location': 1000, 'license': 1000}


def _safe_io_missing() -> list[str]:
    """Inspect runtime primitives only. Never open a caller-supplied path."""
    missing = []
    if os.name != 'posix':
        missing.append('posix_os')
    for flag in ('O_NOFOLLOW', 'O_DIRECTORY', 'O_CLOEXEC', 'O_NONBLOCK'):
        if not hasattr(os, flag):
            missing.append(flag)
    if os.open not in os.supports_dir_fd:
        missing.append('open_dir_fd')
    if os.stat not in os.supports_dir_fd:
        missing.append('stat_dir_fd')
    if os.stat not in os.supports_follow_symlinks:
        missing.append('stat_no_follow')
    if os.scandir not in os.supports_fd:
        missing.append('scandir_fd')
    return missing


def _require_safe_io() -> None:
    missing = _safe_io_missing()
    if missing:
        raise ValueError('safe descriptor-relative source IO is unavailable (' + ', '.join(missing)
                         + '). External source operations remain disabled. Run '
                         'python -m jace.cli source-capabilities for a read-only platform check.')


def _publication_primitive():
    """Resolve the existing Linux primitive without calling it or touching files."""
    if sys.platform != 'linux':
        raise ValueError('linux_platform')
    try:
        library = ctypes.CDLL(None, use_errno=True)
    except OSError as error:
        raise ValueError('libc_unavailable') from error
    rename = getattr(library, 'renameat2', None)
    if rename is None:
        raise ValueError('libc_renameat2')
    return rename


def _publication_io_missing() -> list[str]:
    missing = []
    for name in ('mkdir', 'unlink', 'rmdir'):
        if getattr(os, name, None) not in os.supports_dir_fd:
            missing.append(name + '_dir_fd')
    for name in ('fchmod', 'fsync'):
        if not callable(getattr(os, name, None)):
            missing.append(name)
    return missing


def _require_publication_io() -> None:
    """Fail before source reads or staging when known primitives are absent.

    A symbol is only a prerequisite: each actual publication still handles
    kernel/filesystem rejection and preserves the no-overwrite boundary.
    """
    _require_safe_io()
    missing = _publication_io_missing()
    try:
        if missing:
            raise ValueError(', '.join(missing))
        _publication_primitive()
    except ValueError as error:
        raise ValueError('atomic no-overwrite bundle publication is unavailable (' + str(error)
                         + '). No source copy/export can start on this platform. Run '
                         'python -m jace.cli source-capabilities for a read-only platform check.') from error


def source_platform_capabilities() -> dict:
    """Read-only platform prerequisites, not a filesystem or browser test.

    Does not instantiate an engine, inspect model/corpus configuration, read
    user paths, create a directory/database, invoke rename, or call a provider.
    """
    reads_missing = _safe_io_missing()
    publication_missing = reads_missing + _publication_io_missing()
    try:
        _publication_primitive()
    except ValueError as error:
        publication_missing.append(str(error))
    return {
        'schema_version': 1, 'platform': sys.platform, 'os_name': os.name,
        'external_source_reads': {
            'prerequisites_available': not reads_missing,
            'required_backend': 'POSIX descriptor-relative no-follow reads',
            'missing_prerequisites': reads_missing,
        },
        'private_bundle_publication': {
            'prerequisites_available': not publication_missing,
            'required_backend': 'POSIX private staging and Linux renameat2(RENAME_NOREPLACE)',
            'missing_prerequisites': publication_missing,
        },
        'built_in_samples': 'The fixed packaged sample path does not require external source IO; it was not loaded by this check.',
        'native_windows_source_backend': 'not implemented',
        'limits': [
            'Runtime feature inspection only. No user files, database, source copies, output directories or network calls.',
            'Available prerequisites do not prove that a kernel, filesystem, directory permissions or actual operation will succeed.',
            'Each source read and publication retains its normal integrity checks; there is no unsafe fallback.',
            'This does not test browser access, downloads, source authenticity, review, rights or model quality.',
        ],
    }


def _parts(path: str | os.PathLike) -> tuple[bool, list[str]]:
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw or '\x00' in raw or '\\' in raw:
        raise ValueError('invalid bundle path')
    parts = raw.split('/')
    if any(part == '..' for part in parts):
        raise ValueError('parent traversal is not allowed')
    parts = [part for part in parts if part not in ('', '.')]
    if not parts:
        raise ValueError('a named bundle path is required')
    return raw.startswith('/'), parts


def _identity(info) -> tuple:
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))


def _fingerprint(info) -> tuple:
    return (_identity(info), info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


class _DirectoryChain(AbstractContextManager):
    """Keep parents and descendants open; never resolve a supplied symlink."""

    def __init__(self, absolute: bool, components: list[str]):
        self.fds: list[int] = []
        self.links: list[tuple[int, str, int]] = []
        self.files: list[tuple[int, str, tuple]] = []
        try:
            self.fds.append(os.open('/' if absolute else '.', self.flags()))
            for name in components:
                self.descend(self.fds[-1], name)
        except BaseException:
            self.__exit__(None, None, None)
            raise

    @staticmethod
    def flags() -> int:
        return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC

    @property
    def fd(self) -> int:
        return self.fds[-1]

    def descend(self, parent: int, name: str) -> int:
        fd = os.open(name, self.flags(), dir_fd=parent)
        self.fds.append(fd)
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            raise ValueError('bundle path is not a directory')
        self.links.append((parent, name, fd))
        return fd

    def verify(self) -> None:
        for parent, name, fd in self.links:
            if _identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != _identity(os.fstat(fd)):
                raise ValueError('bundle directory changed during IO')
        for parent, name, expected in self.files:
            if _fingerprint(os.stat(name, dir_fd=parent, follow_symlinks=False)) != expected:
                raise ValueError('bundle file changed during IO')

    def __exit__(self, *exc):
        for fd in reversed(self.fds):
            try:
                os.close(fd)
            except OSError:
                # These are read-only directory descriptors, not pending file
                # writes. Never turn completed publication into a false failure
                # because of descriptor cleanup, or retry a possibly closed fd.
                pass
        self.fds.clear()
        return False


def _read_regular(parent: int, name: str, limit: int, chain: _DirectoryChain) -> bytes:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=parent)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError('bundle files must be regular files without hard links')
        if before.st_size < 0 or before.st_size > limit:
            raise ValueError('bundle file exceeds its byte limit')
        chunks = []
        size = 0
        while True:
            chunk = os.read(fd, min(_READ_CHUNK, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                raise ValueError('bundle file exceeds its byte limit')
        after = os.fstat(fd)
        if size != before.st_size or _fingerprint(before) != _fingerprint(after):
            raise ValueError('bundle file changed during read')
        if _fingerprint(os.stat(name, dir_fd=parent, follow_symlinks=False)) != _fingerprint(after):
            raise ValueError('bundle file was replaced during read')
        chain.files.append((parent, name, _fingerprint(after)))
        return b''.join(chunks)
    finally:
        os.close(fd)


def _json(raw: str):
    # Bound nesting before json.loads allocates a tree. Braces inside quoted
    # strings (including escaped quotes) are not structure.
    depth = 0
    quoted = escaped = False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in '[{':
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError('source JSON exceeds its nesting limit')
        elif char in ']}':
            depth -= 1
    value = strict_json(raw)
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise ValueError('nonfinite JSON')
    return value


def _digest(value) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError('source SHA256 must be 64 lowercase hexadecimal characters')
    return value


def _text(value, field: str, maximum: int) -> str:
    # Normalize descriptive metadata only. Source bytes and passages never change.
    return ' '.join(checked_text(value, field, maximum).split())


def _metadata(record, *, require_review: bool = True) -> tuple[dict, dict]:
    if not isinstance(record, dict) or not _REQUIRED <= record.keys() or record.keys() - (_REQUIRED | _OPTIONAL):
        raise ValueError('invalid source record fields')
    result = {name: _text(record[name], name, maximum) for name, maximum in _TEXT_LIMITS.items()}
    if any(char.isspace() or char in '[]' for char in result['entry_id']):
        raise ValueError('invalid source entry ID')
    if type(require_review) is not bool or record['verified'] is not require_review:
        raise ValueError('source review declaration does not match the required mode')
    result['verified'] = require_review
    edition = record.get('edition')
    result['edition'] = None if edition is None else _text(edition, 'edition', 1000)
    tags = record.get('tags', [])
    if not isinstance(tags, list) or len(tags) > MAX_TAGS:
        raise ValueError('invalid source tags')
    result['tags'] = [_text(tag, 'tag', 64) for tag in tags]
    if len(set(result['tags'])) != len(result['tags']):
        raise ValueError('duplicate source tags')
    ref = record['source_ref']
    if not isinstance(ref, dict) or set(ref) != {'sha256', 'start', 'end'}:
        raise ValueError('invalid source reference fields')
    digest = _digest(ref['sha256'])
    start, end = ref['start'], ref['end']
    if type(start) is not int or type(end) is not int or start < 0 or end <= start:
        raise ValueError('invalid source byte span')
    if end - start > MAX_PASSAGE_BYTES:
        raise ValueError('source passage exceeds its byte limit')
    return result, {'sha256': digest, 'start': start, 'end': end}


def _validated_sources(sources: dict[str, bytes]) -> None:
    if not isinstance(sources, dict) or not 1 <= len(sources) <= MAX_SOURCES:
        raise ValueError('invalid source count')
    total = 0
    for digest, data in sources.items():
        _digest(digest)
        if type(data) is not bytes or not data or len(data) > MAX_SOURCE_BYTES:
            raise ValueError('invalid source bytes or source byte limit')
        total += len(data)
        if total > MAX_TOTAL_SOURCE_BYTES:
            raise ValueError('source bundle exceeds its total byte limit')
    for digest, data in sources.items():
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('source digest does not match original bytes')
        try:
            data.decode('utf-8', errors='strict')
        except UnicodeError as error:
            raise ValueError('source is not strict UTF-8') from error


def _validated_records(records, sources: dict[str, bytes], *,
                       require_review: bool = True) -> tuple[list[dict], list[dict]]:
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_RECORDS:
        raise ValueError('invalid source record count')
    loaded, normalized, seen, referenced = [], [], set(), set()
    for record in records:
        metadata, ref = _metadata(record, require_review=require_review)
        if metadata['entry_id'] in seen:
            raise ValueError('duplicate source entry ID')
        seen.add(metadata['entry_id'])
        digest, start, end = ref['sha256'], ref['start'], ref['end']
        if digest not in sources or end > len(sources[digest]):
            raise ValueError('source reference is missing or outside source bytes')
        try:
            passage = sources[digest][start:end].decode('utf-8', errors='strict')
        except UnicodeError as error:
            raise ValueError('source byte span splits a UTF-8 character') from error
        if not passage.strip() or len(passage) > MAX_PASSAGE_CHARS or _PASSAGE_CONTROLS.search(passage) or '\r' in passage.replace('\r\n', ''):
            raise ValueError('invalid source passage')
        referenced.add(digest)
        normalized.append({**metadata, 'source_ref': ref})
        loaded.append({**metadata, 'principle': passage, 'source_sha256': digest,
                       'source_byte_start': start, 'source_byte_end': end})
    if referenced != set(sources):
        raise ValueError('source bundle contains unreferenced sources')
    return loaded, normalized


def _declarations(manifest, *, expected_format: str = FORMAT) -> dict[str, str]:
    if (not isinstance(manifest, dict) or set(manifest) != {'format', 'sources', 'records'}
            or expected_format not in (FORMAT, REVIEW_FORMAT) or manifest['format'] != expected_format):
        raise ValueError('invalid source bundle format')
    declarations = manifest['sources']
    if not isinstance(declarations, list) or not 1 <= len(declarations) <= MAX_SOURCES:
        raise ValueError('invalid source count')
    if not isinstance(manifest['records'], list) or not 1 <= len(manifest['records']) <= MAX_RECORDS:
        raise ValueError('invalid source record count')
    result = {}
    for declaration in declarations:
        if not isinstance(declaration, dict) or set(declaration) != {'path', 'sha256'}:
            raise ValueError('invalid source declaration fields')
        digest = _digest(declaration['sha256'])
        if declaration['path'] != f'sources/{digest}.txt' or digest in result:
            raise ValueError('invalid or duplicate source declaration')
        result[digest] = digest + '.txt'
    return result


def _check_source_names(source_fd: int, expected: set[str]) -> None:
    # scandir streams directory entries; never allocate an unbounded listdir.
    seen = set()
    with os.scandir(source_fd) as entries:
        for entry in entries:
            if entry.name not in expected or entry.name in seen:
                raise ValueError('source directory contains undeclared assets')
            seen.add(entry.name)
            if len(seen) > MAX_SOURCES:
                raise ValueError('source directory exceeds its file limit')
    if seen != expected:
        raise ValueError('source directory is missing declared assets')


def _load(path: str | os.PathLike, allow_legacy: bool) -> tuple[list[dict], bool]:
    _require_safe_io()
    absolute, components = _parts(path)
    try:
        with _DirectoryChain(absolute, components[:-1]) as chain:
            root = chain.fd
            raw = _read_regular(root, components[-1], MAX_MANIFEST_BYTES, chain)
            try:
                manifest = _json(raw.decode('utf-8', errors='strict'))
            except (UnicodeError, ValueError) as error:
                raise ValueError('invalid UTF-8 source manifest JSON') from error
            if allow_legacy and isinstance(manifest, list):
                chain.verify()
                return manifest, False
            declarations = _declarations(manifest)
            source_fd = chain.descend(root, 'sources')
            _check_source_names(source_fd, set(declarations.values()))
            sources = {}
            total = 0
            for digest, filename in declarations.items():
                remaining = MAX_TOTAL_SOURCE_BYTES - total
                data = _read_regular(source_fd, filename, min(MAX_SOURCE_BYTES, remaining), chain)
                total += len(data)
                sources[digest] = data
            _validated_sources(sources)
            loaded, _ = _validated_records(manifest['records'], sources)
            _check_source_names(source_fd, set(declarations.values()))
            chain.verify()
            return loaded, True
    except OSError as error:
        raise ValueError('cannot safely read source bundle files') from error


def load_source_bundle(manifest_path: str | os.PathLike) -> list[dict]:
    """Return exact passages and digest/byte provenance; reject legacy corpora."""
    return _load(manifest_path, allow_legacy=False)[0]


def load_corpus_records(manifest_path: str | os.PathLike) -> list[dict]:
    """Read once, safely: derive bundle records or return a legacy JSON list.

    The caller remains responsible for validating legacy record contents. Legacy
    lists do not gain original-source-byte provenance merely by using this IO.
    """
    return load_corpus_snapshot(manifest_path)[0]


def load_corpus_snapshot(manifest_path: str | os.PathLike) -> tuple[list[dict], bool]:
    """Return records plus True only for a validated exact-source bundle.

    A False flag means unvalidated legacy record contents. Callers must reject
    provenance claims in those records rather than trusting caller-supplied keys.
    """
    return _load(manifest_path, allow_legacy=True)


def load_builtin_samples() -> list[dict]:
    """Bounded installed-package samples, with no original-source-byte claim.

    The fixed package resource is part of the trusted application installation,
    not an operator-supplied path. This keeps default startup portable without
    weakening descriptor-safe admission for any external corpus.
    """
    resource = importlib.resources.files('jace').joinpath('data', 'canonical.json')
    with resource.open('rb') as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError('built-in sample file exceeds its byte limit')
    try:
        value = _json(raw.decode('utf-8', errors='strict'))
    except (UnicodeError, ValueError) as error:
        raise ValueError('invalid built-in sample JSON') from error
    if not isinstance(value, list):
        raise ValueError('built-in samples must be legacy records without source-byte provenance')
    return value


def read_source_file(path: str | os.PathLike) -> bytes:
    """Read a bounded local UTF-8 source through pinned, no-symlink descriptors."""
    _require_safe_io()
    absolute, components = _parts(path)
    try:
        with _DirectoryChain(absolute, components[:-1]) as chain:
            data = _read_regular(chain.fd, components[-1], MAX_SOURCE_BYTES, chain)
            if not data:
                raise ValueError('source must not be empty')
            try:
                data.decode('utf-8', errors='strict')
            except UnicodeError as error:
                raise ValueError('source is not strict UTF-8') from error
            chain.verify()
            return data
    except OSError as error:
        raise ValueError('cannot safely read source file') from error


def _write_private(parent: int, name: str, data: bytes) -> None:
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=parent)
    try:
        os.fchmod(fd, 0o600)
        offset = 0
        while offset < len(data):
            written = os.write(fd, memoryview(data)[offset:offset + _READ_CHUNK])
            if written <= 0:
                raise ValueError('source bundle write made no progress')
            offset += written
        os.fsync(fd)
    finally:
        os.close(fd)


def _rename_noreplace(parent: int, stage_name: str, target_name: str) -> None:
    try:
        rename = _publication_primitive()
    except ValueError as error:
        raise ValueError('atomic no-overwrite bundle publication is unavailable') from error
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(parent, os.fsencode(stage_name), parent, os.fsencode(target_name), 1) != 0:
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise ValueError('source bundle destination already exists')
        if code in (errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP):
            raise ValueError('atomic no-overwrite bundle publication is unavailable')
        raise OSError(code, 'atomic bundle publication failed')


def _remove_stage(parent: int, stage_name: str, stage_fd: int, *, review_html: bool = False) -> None:
    """Remove only entries in our pinned private staging directory."""
    try:
        source_fd = os.open('sources', _DirectoryChain.flags(), dir_fd=stage_fd)
    except FileNotFoundError:
        source_fd = None
    if source_fd is not None:
        try:
            with os.scandir(source_fd) as entries:
                for entry in entries:
                    os.unlink(entry.name, dir_fd=source_fd)
        finally:
            os.close(source_fd)
        os.rmdir('sources', dir_fd=stage_fd)
    try:
        os.unlink('bundle.json', dir_fd=stage_fd)
    except FileNotFoundError:
        pass
    if review_html:
        try:
            os.unlink('review.html', dir_fd=stage_fd)
        except FileNotFoundError:
            pass
    if _identity(os.stat(stage_name, dir_fd=parent, follow_symlinks=False)) != _identity(os.fstat(stage_fd)):
        raise ValueError('private staging directory changed during cleanup')
    os.rmdir(stage_name, dir_fd=parent)


def write_source_bundle(output_directory: str | os.PathLike, sources: dict[str, bytes],
                        records: list[dict]) -> Path:
    """Validate then atomically publish a fresh, private local bundle directory.

    Existing targets (including empty directories and symlinks) are never
    replaced. The output's parent must already exist. No network IO occurs.
    """
    return _write_bundle(output_directory, sources, records)


def _write_bundle(output_directory: str | os.PathLike, sources: dict[str, bytes],
                  records: list[dict], *, expected_format: str = FORMAT,
                  require_review: bool = True, review_html: bytes | None = None) -> Path:
    """Shared publisher with two explicit modes and one fixed optional asset."""
    if expected_format == FORMAT:
        if require_review is not True or review_html is not None:
            raise ValueError('runtime bundles require review and cannot include review assets')
    elif expected_format == REVIEW_FORMAT:
        if (require_review is not False or type(review_html) is not bytes
                or not review_html or len(review_html) > MAX_REVIEW_HTML_BYTES):
            raise ValueError('draft bundles require unreviewed records and bounded review HTML')
    else:
        raise ValueError('invalid source bundle format')
    _require_publication_io()
    absolute, components = _parts(output_directory)
    _validated_sources(sources)
    sources = dict(sources)
    _, normalized = (_validated_records(records, sources) if require_review else
                     _validated_records(records, sources, require_review=False))
    manifest = {'format': expected_format,
                'sources': [{'path': f'sources/{digest}.txt', 'sha256': digest} for digest in sorted(sources)],
                'records': normalized}
    payload = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ValueError('source manifest exceeds its byte limit')
    try:
        with _DirectoryChain(absolute, components[:-1]) as chain:
            parent = chain.fd
            target = components[-1]
            try:
                os.stat(target, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise ValueError('source bundle destination already exists')
            stage_name = '.jace-source-' + secrets.token_hex(16)
            os.mkdir(stage_name, 0o700, dir_fd=parent)
            stage_fd = None
            published = False
            try:
                stage_fd = chain.descend(parent, stage_name)
                os.fchmod(stage_fd, 0o700)
                os.mkdir('sources', 0o700, dir_fd=stage_fd)
                source_fd = chain.descend(stage_fd, 'sources')
                os.fchmod(source_fd, 0o700)
                for digest in sorted(sources):
                    _write_private(source_fd, digest + '.txt', sources[digest])
                _write_private(stage_fd, 'bundle.json', payload)
                if review_html is not None:
                    _write_private(stage_fd, 'review.html', review_html)
                # Validate the bytes actually written, not only the input objects.
                actual = {}
                for digest in sorted(sources):
                    actual[digest] = _read_regular(source_fd, digest + '.txt', MAX_SOURCE_BYTES, chain)
                _validated_sources(actual)
                written_raw = _read_regular(stage_fd, 'bundle.json', MAX_MANIFEST_BYTES, chain)
                if written_raw != payload:
                    raise ValueError('source manifest changed after writing')
                written = _json(written_raw.decode('utf-8'))
                if set(_declarations(written, expected_format=expected_format)) != set(actual):
                    raise ValueError('written source declarations changed')
                if require_review:
                    _validated_records(written['records'], actual)
                else:
                    _validated_records(written['records'], actual, require_review=False)
                    if _read_regular(stage_fd, 'review.html', MAX_REVIEW_HTML_BYTES, chain) != review_html:
                        raise ValueError('review document changed after writing')
                _check_source_names(source_fd, {digest + '.txt' for digest in sources})
                chain.verify()
                os.fsync(source_fd)
                os.fsync(stage_fd)
                # Publication is the last fallible filesystem operation. Do not
                # report an fsync error after a complete target has appeared.
                os.fsync(parent)
                _rename_noreplace(parent, stage_name, target)
                published = True
            finally:
                if not published:
                    if stage_fd is not None:
                        _remove_stage(parent, stage_name, stage_fd, review_html=review_html is not None)
                    else:
                        os.rmdir(stage_name, dir_fd=parent)
    except OSError as error:
        raise ValueError('cannot safely write source bundle files') from error
    return Path(output_directory) / 'bundle.json'
