#!/usr/bin/env python3
"""Verify an extracted skill manifest offline without displaying credentials."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root/'MANIFEST.json').read_text())
    failures = []
    for name, digest in manifest['files'].items():
        path = root/name
        if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
            failures.append(name)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            failures.append(name)
    return {'version': manifest['version'], 'manifest_valid': not failures,
            'checked_files': len(manifest['files']), 'failed_files': failures, 'network_calls': 0}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', nargs='?', default=str(Path(__file__).resolve().parents[1]))
    result = verify(p.parse_args().root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['manifest_valid'] else 1)
