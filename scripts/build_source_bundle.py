"""Build a local exact-source bundle; never download, train or auto-admit texts."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jace.bundle_builder import build_exact_bundle  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description='Pin reviewed UTF-8 source bytes and exact passage spans. Rights/review are declarations, not verified facts.')
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New bundle directory; existing destinations are never overwritten')
    for name in ('work', 'source', 'language', 'license', 'location'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--edition')
    parser.add_argument('--tag', action='append', default=[])
    parser.add_argument('--verified', action='store_true', help='Declare that a qualified human has reviewed these sources; not an automated verification')
    parser.add_argument('--confirm-build', action='store_true', help='Explicitly copy the supplied sources into a new local bundle; does not authorize sharing/training')
    parser.add_argument('--chunk-words', type=int, default=220)
    parser.add_argument('--overlap-words', type=int, default=40)
    args = parser.parse_args()
    if not args.confirm_build:
        print('No files were copied or read. Review the source rights, metadata and output destination, then add --verified and --confirm-build to build locally. No training, sharing or runtime configuration is performed.')
        return
    try:
        result = build_exact_bundle(args.files, args.output, work=args.work, source=args.source,
            language=args.language, license_name=args.license, location=args.location, edition=args.edition,
            tags=args.tag, verified=args.verified, confirm_build=args.confirm_build,
            chunk_words=args.chunk_words, overlap_words=args.overlap_words)
    except (ValueError, OSError) as error:
        parser.exit(2, f'Bundle not published: {error}\n')
    print(f'Local source bundle published at {result}. Source bytes are pinned, not authenticated; rights and review remain declarations. No model, sharing or runtime activation performed.')


if __name__ == '__main__':
    main()
