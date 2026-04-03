"""Load repo-root ``.env`` / ``.env.local`` into ``os.environ`` (same keys as ``anna_karpathy_loop_env.inc.sh``).

Skips keys already set in the environment so Docker/systemd exports win. ``.env.local`` overrides
values from ``.env`` (and can override inherited env for keys it sets).

No third-party dependency — simple ``KEY=value`` lines only.
"""

from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_env_line(line: str) -> tuple[str, str] | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("export "):
        s = s[7:].strip()
    if "=" not in s:
        return None
    key, _, rest = s.partition("=")
    key = key.strip()
    if not key:
        return None
    val = rest.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
        val = val[1:-1]
    return key, val


def _apply_file(path: Path, *, override: bool) -> None:
    raw = path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        parsed = _parse_env_line(line)
        if not parsed:
            continue
        k, v = parsed
        if override:
            os.environ[k] = v
        else:
            os.environ.setdefault(k, v)


def apply_repo_dotenv(repo_root: Path | None = None) -> None:
    """Load ``<repo>/.env`` then ``<repo>/.env.local`` if those files exist."""
    root = repo_root or _repo_root()
    for name, override in ((".env", False), (".env.local", True)):
        p = root / name
        if p.is_file():
            _apply_file(p, override=override)
