# Used by verify_pattern_game_openai_v1.sh — redact key-like substrings in JSON to stdout.
from __future__ import annotations

import json
import re
import sys


def _redact_str(s: str) -> str:
    t = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-…", s, flags=re.I)
    t = re.sub(r"(?i)bearer\s+\S+", "Bearer …", t)
    return t


def _walk(o: object) -> object:
    if isinstance(o, dict):
        return {k: _walk(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_walk(x) for x in o]
    if isinstance(o, str):
        return _redact_str(o)
    return o


def main() -> None:
    raw = sys.stdin.read()
    o = json.loads(raw)
    out = json.dumps(_walk(o), indent=2, ensure_ascii=False)
    if len(out) > 20_000:
        print(out[:20_000])
        print("… (truncated)", file=sys.stderr)
    else:
        print(out)


if __name__ == "__main__":
    main()
