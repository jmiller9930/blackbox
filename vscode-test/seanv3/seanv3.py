#!/usr/bin/env python3
"""
Thin wrapper around ./seanv3py (same commands). Use either:

  python3 seanv3.py deploy --pull
  ./seanv3py deploy --pull

SSH note: each login is a new SSH session. The Docker container persists after disconnect.
Use ./seanv3py console (tmux) on the server to reattach to the same *terminal workspace*.
"""
from __future__ import annotations

import os
import sys


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    sh = os.path.join(here, "seanv3py")
    if not os.path.isfile(sh):
        print("seanv3py not found next to seanv3.py", file=sys.stderr)
        sys.exit(1)
    os.execv(sh, [sh, *sys.argv[1:]])


if __name__ == "__main__":
    main()
