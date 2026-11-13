"""Private prepare/inspect/export workflow; never trains or invokes a provider."""
import argparse
import json

from .training_review import WARNING, export_review, prepare_review, read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=WARNING)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare = commands.add_parser('prepare', help='Prepare a private draft and all-pending decision template')
    prepare.add_argument('--plan', required=True)
    prepare.add_argument('--output', required=True)
    prepare.add_argument('--confirm-copy', action='store_true')
    inspect = commands.add_parser('inspect', help='Print private draft or decisions to stdout for local review')
    inspect.add_argument('--file', required=True)
    export = commands.add_parser('export', help='Export only fully approved examples for separate training preflight')
    export.add_argument('--draft', required=True)
    export.add_argument('--decisions', required=True)
    export.add_argument('--output', required=True)
    export.add_argument('--confirm-export', action='store_true')
    export.add_argument('--declare-no-personal-data', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            result = {'draft': str(prepare_review(args.plan, args.output, confirm_copy=args.confirm_copy)), 'training_started': False, 'warning': WARNING}
        elif args.command == 'inspect':
            result = read_json(args.file)
        else:
            result = export_review(args.draft, args.decisions, args.output,
                confirm_export=args.confirm_export, declare_no_personal_data=args.declare_no_personal_data)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(2, 'Training review operation rejected: ' + str(error) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
