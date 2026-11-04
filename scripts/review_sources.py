"""Prepare offline review-only source packages and separately export approvals."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jace.source_review import (WHOLE_FILE_WARNING, export_reviewed_sources,
                                prepare_source_review)  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=(
        'Offline local source review. Drafts cannot run as runtime corpora. Rights and review '
        'declarations are not verification. No network, training, sharing or automatic activation.'))
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare', help='Copy whole explicitly chosen UTF-8 files for private human review')
    prepare.add_argument('files', nargs='+', type=Path)
    prepare.add_argument('--output', required=True, type=Path, help='New private draft directory; never overwritten')
    for name in ('work', 'source', 'language', 'license', 'location'):
        prepare.add_argument('--' + name, required=True)
    prepare.add_argument('--edition')
    prepare.add_argument('--tag', action='append', default=[])
    prepare.add_argument('--confirm-copy', action='store_true', help='Explicitly permit reading and copying WHOLE selected files locally')
    prepare.add_argument('--chunk-words', type=int, default=220)
    prepare.add_argument('--overlap-words', type=int, default=40)
    export = commands.add_parser('export', help='Export approved records, retaining WHOLE backing files including unapproved text',
        description=WHOLE_FILE_WARNING + ' Rights and qualified review are declarations, not verification.')
    export.add_argument('--manifest', required=True, type=Path, help='Review-only draft bundle.json')
    export.add_argument('--decisions', required=True, type=Path, help='Human-saved revision-bound decision JSON')
    export.add_argument('--output', required=True, type=Path, help='New runtime bundle directory; never overwritten')
    export.add_argument('--confirm-export', action='store_true', help='Confirm local export including WHOLE backing files and unapproved bytes')
    export.add_argument('--declare-qualified-review', action='store_true', help='Attest approved spans and metadata received qualified human review; identity is not authenticated')
    export.add_argument('--declare-rights-for-local-retrieval', action='store_true', help='Attest rights for local retrieval and retention of WHOLE files; not verified legal rights')
    args = parser.parse_args(argv)
    if args.command == 'export':
        print(WHOLE_FILE_WARNING, flush=True)
        if not (args.confirm_export and args.declare_qualified_review and args.declare_rights_for_local_retrieval):
            print('No files were read or exported. Review the whole-file warning and add all three confirmation/declaration flags to export locally. Declarations are not independent verification.')
            return 0
    elif not args.confirm_copy:
        print('No files were read or copied. Add --confirm-copy to copy WHOLE supplied files into a private review-only package. Drafts cannot run as runtime corpora.')
        return 0
    try:
        if args.command == 'prepare':
            result = prepare_source_review(args.files, args.output, work=args.work, source=args.source,
                language=args.language, license_name=args.license, location=args.location,
                edition=args.edition, tags=args.tag, confirm_copy=args.confirm_copy,
                chunk_words=args.chunk_words, overlap_words=args.overlap_words)
            print(f'Private review-only package prepared at {result}. Open {result.parent / "review.html"} offline to review exact spans and metadata and save decisions. Whole originals are retained. Drafts cannot run; no activation, sharing or training occurred.')
        else:
            result = export_reviewed_sources(args.manifest, args.decisions, args.output,
                confirm_export=args.confirm_export, declare_qualified_review=args.declare_qualified_review,
                declare_rights_for_local_retrieval=args.declare_rights_for_local_retrieval)
            print(f'Local runtime bundle exported at {result["manifest_path"]}: {result["approved_records"]} approved records, {result["source_count"]} WHOLE source files. Qualified review and rights remain declarations. No activation, sharing or training occurred.')
    except (ValueError, OSError) as error:
        parser.exit(2, f'Source review operation not published: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
