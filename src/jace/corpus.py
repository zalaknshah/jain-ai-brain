from __future__ import annotations

import hashlib
import json
import os
import tempfile
import re
from pathlib import Path
from typing import Any, Iterable


SUPPORTED_SUFFIXES = {".txt", ".md", ".markdown"}


def _chunks(text: str, size: int, overlap: int) -> Iterable[str]:
    words = re.findall(r"\S+", text.replace("\r", ""))
    if size <= 0 or overlap < 0 or overlap >= size:
        raise ValueError("chunk_size must be positive and overlap must be smaller than chunk_size")
    step = size - overlap
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + size]).strip()
        if chunk:
            yield chunk
        if start + size >= len(words):
            break


def ingest_files(
    paths: Iterable[str | Path],
    output: str | Path,
    *,
    work: str,
    source: str,
    language: str = "en",
    edition: str | None = None,
    location: str | None = None,
    license_name: str | None = None,
    tags: list[str] | None = None,
    verified: bool = False,
    draft: bool = False,
    chunk_size: int = 220,
    overlap: int = 40,
) -> int:
    """Convert reviewed text files into provenance-aware canonical records.

    The output is JSON, compatible with ``CanonicalStore``. It intentionally
    preserves source and location metadata so generated paraphrases cannot be
    mistaken for canonical quotations.
    """
    if any(not isinstance(value, str) or not value.strip() for value in (work, source, language)):
        raise ValueError("work, source and language are required")
    if not draft and (verified is not True or not isinstance(license_name, str) or not license_name.strip()):
        raise ValueError("Runtime corpus ingestion requires human review and a recorded license; use draft=True for review-only output")
    output_path = Path(output)
    input_paths = [Path(path) for path in paths]
    for path in input_paths:
        if output_path.resolve() == path.resolve() or (
            output_path.exists() and path.exists() and output_path.samefile(path)
        ):
            raise ValueError("Corpus output must not alias an input source")
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    common_tags = tags or []
    for path in input_paths:
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        for index, chunk in enumerate(_chunks(text, chunk_size, overlap), 1):
            identity = {"work": work, "source": source, "language": language, "edition": edition,
                        "location": location or path.name, "chunk": index, "text": chunk}
            digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
            entry_id = f"corpus:{digest}"
            if entry_id in seen_ids:
                raise ValueError("Duplicate corpus entry identity; review repeated inputs or ambiguous source locations before ingestion")
            seen_ids.add(entry_id)
            records.append(
                {
                    "entry_id": entry_id,
                    "title": f"{work} — {path.stem} §{index}",
                    "principle": chunk,
                    "guidance": "Source passage retrieved for contextual analysis; interpretation must be clearly labelled.",
                    "source": source,
                    "tags": common_tags,
                    "work": work,
                    "language": language,
                    "edition": edition,
                    "location": location or path.name,
                    "license": license_name,
                    "verified": verified,
                }
            )
    if not records:
        raise ValueError("No supported nonempty text or Markdown sources were provided")
    # Encode before touching the destination: malformed metadata must not
    # truncate an existing checkpoint. Stage on the same filesystem and replace
    # only after a complete write. This is not a crash-durability guarantee.
    payload = (json.dumps(records, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staged = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=output_path.parent,
                                         prefix=".jace-corpus-", delete=False) as stream:
            staged = Path(stream.name)
            if stream.write(payload) != len(payload):
                raise OSError("Incomplete corpus staging write")
            stream.flush()
        os.replace(staged, output_path)
        staged = None
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return len(records)
