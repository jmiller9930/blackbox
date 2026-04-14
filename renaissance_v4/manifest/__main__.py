"""python -m renaissance_v4.manifest <path/to/manifest.json> — validate and print errors."""

from __future__ import annotations

import sys

from renaissance_v4.manifest.validate import load_manifest_file, validate_manifest_against_catalog


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python -m renaissance_v4.manifest <manifest.json>", file=sys.stderr)
        return 2
    m = load_manifest_file(sys.argv[1])
    errs = validate_manifest_against_catalog(m)
    if errs:
        for e in errs:
            print(e, file=sys.stderr)
        return 1
    print("manifest OK (v1 registry checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
