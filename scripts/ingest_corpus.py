"""Ingest reviewed text into JACE's provenance-aware canonical store.

Example:
    python scripts/ingest_corpus.py texts/*.txt --output data/corpus.json \
      --work "Reviewed Jain text" --source "Edition and translator" \
      --language en --license "CC BY" --tag ahimsa
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jace.corpus import ingest_files  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create provenance-aware JACE corpus records")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--language", default="en")
    parser.add_argument("--edition")
    parser.add_argument("--location")
    parser.add_argument("--license", dest="license_name")
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--verified", action="store_true", help="mark as reviewed by a human; do not use for unreviewed text")
    parser.add_argument("--chunk-size", type=int, default=220)
    parser.add_argument("--overlap", type=int, default=40)
    args = parser.parse_args()
    count = ingest_files(
        args.files,
        args.output,
        work=args.work,
        source=args.source,
        language=args.language,
        edition=args.edition,
        location=args.location,
        license_name=args.license_name,
        tags=args.tag,
        verified=args.verified,
        chunk_size=args.chunk_size,
        overlap=args.overlap,
    )
    print(f"Wrote {count} provenance-aware records to {args.output}")


if __name__ == "__main__":
    main()
