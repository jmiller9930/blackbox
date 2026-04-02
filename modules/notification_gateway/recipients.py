"""Resolve SMS recipients: distro JSON, comma-separated E.164, or single env phone."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def normalize_to_e164(raw: str) -> str:
    """Normalize US-style or digit-only strings to E.164 when unambiguous."""
    s = (raw or "").strip()
    if not s:
        return ""
    if s.startswith("+"):
        d = re.sub(r"\D", "", s[1:])
        return f"+{d}" if d else ""
    d = re.sub(r"\D", "", s)
    if not d:
        return ""
    if len(d) == 10:
        return "+1" + d
    if len(d) == 11 and d.startswith("1"):
        return "+" + d
    return "+" + d


def _load_json_recipients(path: Path) -> list[tuple[str, str]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("recipients") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    out: list[tuple[str, str]] = []
    for i, row in enumerate(items):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("label") or f"recipient{i+1}").strip()
        raw = row.get("phone_e164") or row.get("phone") or row.get("number") or ""
        e164 = normalize_to_e164(str(raw))
        if e164:
            out.append((name, e164))
    return out


def _parse_csv_e164(s: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for i, part in enumerate(s.split(",")):
        p = part.strip()
        if not p:
            continue
        e164 = normalize_to_e164(p)
        if e164:
            out.append((f"recipient{i+1}", e164))
    return out


def resolve_recipient_targets() -> list[tuple[str, str]]:
    """
    Order:
      1. BLACKBOX_NOTIFY_DISTRO — comma-separated E.164 (optional +1)
      2. BLACKBOX_NOTIFY_RECIPIENTS_PATH — explicit JSON path
      3. config/notification_recipients.local.json (gitignored)
      4. config/notification_recipients.json
      5. BLACKBOX_NOTIFY_PHONE_E164 — single legacy default
    """
    distro = (os.environ.get("BLACKBOX_NOTIFY_DISTRO") or "").strip()
    if distro:
        parsed = _parse_csv_e164(distro)
        if parsed:
            return parsed

    explicit = (os.environ.get("BLACKBOX_NOTIFY_RECIPIENTS_PATH") or "").strip()
    paths: list[Path] = []
    if explicit:
        paths.append(Path(os.path.expanduser(explicit)))
    root = _repo_root()
    paths.append(root / "config" / "notification_recipients.local.json")
    paths.append(root / "config" / "notification_recipients.json")

    for p in paths:
        got = _load_json_recipients(p)
        if got:
            return got

    single = (os.environ.get("BLACKBOX_NOTIFY_PHONE_E164") or "").strip()
    if single:
        e164 = normalize_to_e164(single)
        if e164:
            return [("default", e164)]
    return []


__all__ = ["normalize_to_e164", "resolve_recipient_targets"]
