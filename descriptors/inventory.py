"""Explicit local inventory maintenance; never called by ordinary analysis."""
import argparse
import hashlib
import json
from pathlib import Path

from descriptors.organisms import SpeciesInventory, load_inventory, read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    validate = sub.add_parser('validate', help='Validate a supplied local artifact and print its identity')
    validate.add_argument('artifact', type=Path)
    build = sub.add_parser('build', help='Generate a new candidate from supplied local JSON; refuses replacement')
    build.add_argument('source', type=Path)
    build.add_argument('output', type=Path)
    build.add_argument('--version', required=True)
    build.add_argument('--source-description', required=True)
    build.add_argument('--source-release')
    build.add_argument('--source-date')
    args = parser.parse_args(argv)
    try:
        if args.command == 'validate':
            identity = load_inventory(args.artifact).identity
        else:
            raw = args.source.read_bytes()
            data = read_json(raw)
            data.update(schema_version=1, inventory_version=args.version, provenance={
                'source_description': args.source_description, 'source_release': args.source_release,
                'source_date': args.source_date, 'input_sha256': hashlib.sha256(raw).hexdigest()})
            content = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
            identity = SpeciesInventory(data, content).identity
            with args.output.open('xb') as handle:
                handle.write(content)
        print(json.dumps(identity, sort_keys=True))
        return 0
    except (OSError, ValueError, RuntimeError, TypeError, AttributeError) as error:
        parser.exit(2, 'Inventory maintenance failed: {}\n'.format(error))


if __name__ == '__main__':
    raise SystemExit(main())
