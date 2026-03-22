"""Normalize Cody plan output: JSON-first, then heading parse, then safe fallback."""
from __future__ import annotations

import json
import re
from typing import Any


_HEADING_RE = re.compile(
    r"^\s*(?:\*\*)?\s*(OBJECTIVE|STEPS|FILES\s+IMPACTED|FILES|RISKS|VALIDATION)\s*:\s*(?:\*\*)?\s*(.*)$",
    re.I,
)


def _split_sections(text: str) -> dict[str, list[str]]:
    """Split body into heading -> lines (content until next heading)."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.replace("\r\n", "\n").splitlines():
        m = _HEADING_RE.match(line)
        if m:
            name = m.group(1).upper().replace("  ", " ")
            if name == "FILES":
                name = "FILES IMPACTED"
            rest = (m.group(2) or "").strip()
            current = name
            sections.setdefault(current, [])
            if rest and not rest.startswith("```"):
                sections[current].append(rest)
            continue
        if current is None:
            continue
        if line.strip().startswith("```") and "OBJECTIVE" not in line.upper():
            continue
        sections[current].append(line)
    return sections


def _clean_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("```"):
            continue
        s = re.sub(r"^\d+\.\s*", "", s)
        s = re.sub(r"^\s*[-*]\s+", "", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
        if s:
            out.append(s)
    return out


def _parse_headings(text: str) -> dict[str, Any]:
    sec = _split_sections(text)
    objective = ""
    if "OBJECTIVE" in sec:
        objective = " ".join(_clean_lines(sec["OBJECTIVE"][:20]))  # first lines as paragraph
        if not objective:
            objective = "\n".join(sec["OBJECTIVE"]).strip()
    steps = _clean_lines(sec.get("STEPS", []))
    files = _clean_lines(sec.get("FILES IMPACTED", []))
    risks = _clean_lines(sec.get("RISKS", []))
    validation = _clean_lines(sec.get("VALIDATION", []))
    return {
        "objective": objective.strip(),
        "steps": steps,
        "files_impacted": files,
        "risks": risks,
        "validation": validation,
        "raw": text,
    }


def _try_json_extract(text: str) -> dict[str, Any] | None:
    for pat in (
        r"```json\s*([\s\S]*?)\s*```",
        r"```\s*([\s\S]*?)\s*```",
    ):
        m = re.search(pat, text, re.I)
        if m:
            try:
                j = json.loads(m.group(1).strip())
                if isinstance(j, dict):
                    return j
            except json.JSONDecodeError:
                continue
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                chunk = text[start : i + 1]
                try:
                    j = json.loads(chunk)
                    if isinstance(j, dict) and any(
                        k in j for k in ("objective", "steps", "files_impacted", "files")
                    ):
                        return j
                except json.JSONDecodeError:
                    pass
                start = -1
    return None


def _normalize_dict(j: dict[str, Any], raw: str) -> dict[str, Any]:
    def as_list(v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            return [ln.strip() for ln in v.splitlines() if ln.strip()]
        return [str(v)]

    def as_str(v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    return {
        "schema_version": 1,
        "objective": as_str(j.get("objective")),
        "steps": as_list(j.get("steps")),
        "files_impacted": as_list(j.get("files_impacted") or j.get("files")),
        "risks": as_list(j.get("risks")),
        "validation": as_list(j.get("validation")),
        "raw_model_output": raw,
        "parse_ok": True,
        "parse_method": "json",
    }


def normalize_plan(raw: str) -> dict[str, Any]:
    """
    Always returns schema_version 1 with normalized fields.
    If JSON/heading parse fails, objective holds a truncated raw excerpt.
    """
    j = _try_json_extract(raw)
    if j:
        return _normalize_dict(j, raw)

    h = _parse_headings(raw)
    has_content = bool(
        h.get("objective")
        or h.get("steps")
        or h.get("files_impacted")
        or h.get("risks")
        or h.get("validation")
    )
    if has_content:
        return {
            "schema_version": 1,
            "objective": h.get("objective") or "",
            "steps": h.get("steps") or [],
            "files_impacted": h.get("files_impacted") or [],
            "risks": h.get("risks") or [],
            "validation": h.get("validation") or [],
            "raw_model_output": raw,
            "parse_ok": True,
            "parse_method": "headings",
        }

    excerpt = raw.strip()
    if len(excerpt) > 8000:
        excerpt = excerpt[:8000] + "\n…"
    return {
        "schema_version": 1,
        "objective": excerpt or "(empty model response)",
        "steps": [],
        "files_impacted": [],
        "risks": [],
        "validation": [],
        "raw_model_output": raw,
        "parse_ok": False,
        "parse_method": "fallback",
    }
