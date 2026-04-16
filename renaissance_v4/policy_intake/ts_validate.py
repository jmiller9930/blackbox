"""TypeScript structural validation — bundle with esbuild (parse + resolve); optional tsc."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def validate_typescript_file(ts_path: Path, *, timeout_sec: int = 120) -> tuple[bool, str]:
    """
    Validate that the file is parseable and bundleable (same toolchain as deterministic test).
    Falls back to explicit error text if esbuild/npx is unavailable.
    """
    ts_path = ts_path.resolve()
    if not ts_path.is_file():
        return False, "TypeScript file not found"

    with tempfile.TemporaryDirectory(prefix="rv4_tsval_") as td:
        out_mjs = Path(td) / "bundle.mjs"
        env = {**os.environ, "npm_config_yes": "true"}
        r = subprocess.run(
            [
                "npx",
                "-y",
                "esbuild@0.20.2",
                str(ts_path),
                "--bundle",
                "--format=esm",
                "--platform=neutral",
                f"--outfile={out_mjs}",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=env,
        )
        if r.returncode == 0 and out_mjs.is_file():
            return True, "TypeScript OK (esbuild bundle)"

        err = ((r.stderr or "") + "\n" + (r.stdout or "")).strip()
        if not err:
            err = f"esbuild exit {r.returncode}"
        return False, err[:8000]
