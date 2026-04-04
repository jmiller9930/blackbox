"""
Structured lesson memory (W9) — similarity-based retrieval, bounded injection.

Validation (eligibility for FACT-layer injection)
---------------------------------------------------
  ``candidate``   — Stored only. **Never** injected into reasoning (default for new rows).
  ``validated``   — Reviewed and approved for use; **eligible** for injection when score ≥ threshold.
  ``promoted``    — Highest trust tier; **eligible** for injection (same gates as validated).

Only ``validated`` and ``promoted`` rows are considered by ``retrieve_lessons_for_situation``.
This is not optional: unvalidated memory must not influence analysis.

Structured ``context_tags`` may be a JSON **object** (not only an array), e.g.
``{"tags": ["perp"], "behavior_effect": "tighten_suggested_action"}`` — see ``policy.LESSON_BEHAVIOR_*``.

Environment
-----------
  ANNA_LESSON_MAX_INJECT — max lessons to inject (default 3)
  ANNA_LESSON_MIN_SCORE  — minimum integer similarity score (default 3)
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

import sqlite3

from anna_modules.context_memory import extract_slots
from anna_modules.util import utc_now

# Injection eligibility — do not drift without Architect sign-off
INJECT_ELIGIBLE_STATUSES: frozenset[str] = frozenset({"validated", "promoted"})

STATUS_CANDIDATE = "candidate"
STATUS_VALIDATED = "validated"
STATUS_PROMOTED = "promoted"


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def max_inject() -> int:
    return max(1, _env_int("ANNA_LESSON_MAX_INJECT", 3))


def min_score_threshold() -> int:
    return max(1, _env_int("ANNA_LESSON_MIN_SCORE", 3))


def normalize_symbol(sym: str | None) -> str | None:
    if not sym:
        return None
    s = str(sym).strip().upper()
    if s.endswith("-PERP"):
        s = s[:-5]
    if s.endswith("PERP"):
        s = re.sub(r"PERP$", "", s).rstrip("-")
    return s or None


def symbols_near_match(a: str | None, b: str | None) -> bool:
    """True if same normalized symbol or one is a prefix family (e.g. SOL vs SOL-PERP)."""
    na, nb = normalize_symbol(a), normalize_symbol(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    return na.startswith(nb) or nb.startswith(na)


def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x).lower() for x in data]
        if isinstance(data, dict):
            inner = data.get("tags")
            if isinstance(inner, list):
                return [str(x).lower() for x in inner]
    except json.JSONDecodeError:
        pass
    return [t.strip().lower() for t in str(raw).split(",") if t.strip()]


def behavior_effect_from_row(row: dict[str, Any]) -> str | None:
    """Read optional ``behavior_effect`` from JSON object in ``context_tags`` column."""
    raw = row.get("context_tags")
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(data, dict):
            eff = data.get("behavior_effect")
            if eff is not None:
                s = str(eff).strip()
                return s or None
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _serialize_context_tags(tags: list[str] | dict[str, Any] | None) -> str:
    if tags is None:
        return "[]"
    if isinstance(tags, dict):
        return json.dumps(tags)
    return json.dumps(list(tags))


def score_lesson(row: dict[str, Any], situation: dict[str, Any]) -> int:
    """Integer similarity score (non-exact): symbol / regime / timeframe / tag overlap."""
    score = 0
    sym_s = situation.get("symbol")
    sym_r = row.get("symbol")
    if sym_s and sym_r:
        if normalize_symbol(sym_s) == normalize_symbol(sym_r):
            score += 3
        elif symbols_near_match(sym_s, sym_r):
            score += 1
    reg_s = (situation.get("regime_tag") or "").strip().lower()
    reg_r = (row.get("regime_tag") or "").strip().lower()
    if reg_s and reg_r and reg_s == reg_r:
        score += 2
    tf_s = (situation.get("timeframe") or "").strip().lower()
    tf_r = (row.get("timeframe") or "").strip().lower()
    if tf_s and tf_r and tf_s == tf_r:
        score += 1
    tags_s = set(situation.get("context_tags") or [])
    tags_r = set(_parse_tags(row.get("context_tags")))
    if tags_s and tags_r:
        overlap = len(tags_s & tags_r)
        score += min(3, overlap)
    return score


def build_situation(
    *,
    input_text: str,
    regime_tag: str | None = None,
    timeframe_override: str | None = None,
    context_tags: list[str] | None = None,
) -> dict[str, Any]:
    slots = extract_slots(input_text)
    tags = [t.lower() for t in (context_tags or [])]
    return {
        "symbol": slots.get("symbol"),
        "regime_tag": regime_tag,
        "timeframe": (timeframe_override or slots.get("timeframe") or "").strip() or None,
        "context_tags": tags,
        "input_text": input_text,
    }


def insert_lesson(
    conn: sqlite3.Connection,
    *,
    lesson_text: str,
    validation_status: str = STATUS_CANDIDATE,
    symbol: str | None = None,
    regime_tag: str | None = None,
    timeframe: str | None = None,
    outcome_class: str | None = None,
    context_tags: list[str] | dict[str, Any] | None = None,
    source: str = "operator",
    situation_summary: str | None = None,
    paper_trade_id: str | None = None,
    request_id: str | None = None,
    notes: str | None = None,
) -> str:
    """Insert a structured lesson. Default status is candidate (not injectable)."""
    lid = str(uuid.uuid4())
    now = utc_now()
    tags_json = _serialize_context_tags(context_tags)
    conn.execute(
        """
        INSERT INTO anna_lesson_memory (
          id, created_at, updated_at, lesson_text, situation_summary,
          symbol, regime_tag, timeframe, outcome_class, context_tags,
          source, validation_status, paper_trade_id, request_id, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lid,
            now,
            now,
            lesson_text,
            (situation_summary or "")[:500],
            symbol,
            regime_tag,
            timeframe,
            outcome_class,
            tags_json,
            source,
            validation_status,
            paper_trade_id,
            request_id,
            notes,
        ),
    )
    conn.commit()
    return lid


def update_validation_status(conn: sqlite3.Connection, lesson_id: str, validation_status: str) -> None:
    conn.execute(
        "UPDATE anna_lesson_memory SET validation_status = ?, updated_at = ? WHERE id = ?",
        (validation_status, utc_now(), lesson_id),
    )
    conn.commit()


def retrieve_lessons_for_situation(
    conn: sqlite3.Connection,
    situation: dict[str, Any],
    *,
    top_k: int | None = None,
    min_score: int | None = None,
) -> list[tuple[dict[str, Any], int]]:
    """
    Similarity-ranked lessons. Only validated/promoted rows participate.
    Returns [(row_dict, score), ...] descending score.
    """
    tk = top_k if top_k is not None else max_inject()
    ms = min_score if min_score is not None else min_score_threshold()
    placeholders = ",".join("?" * len(INJECT_ELIGIBLE_STATUSES))
    cur = conn.execute(
        f"""
        SELECT id, created_at, updated_at, lesson_text, situation_summary,
               symbol, regime_tag, timeframe, outcome_class, context_tags,
               source, validation_status, paper_trade_id, request_id, notes
        FROM anna_lesson_memory
        WHERE validation_status IN ({placeholders})
        ORDER BY created_at DESC
        """,
        tuple(INJECT_ELIGIBLE_STATUSES),
    )
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    scored: list[tuple[dict[str, Any], int]] = []
    for row in rows:
        d = dict(zip(cols, row))
        sc = score_lesson(d, situation)
        if sc >= ms:
            scored.append((d, sc))
    scored.sort(key=lambda x: -x[1])
    return scored[:tk]


def build_lesson_memory_fact_lines(
    conn: sqlite3.Connection | None,
    situation: dict[str, Any],
    *,
    top_k: int | None = None,
    min_score: int | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """
    FACT lines for merge_authoritative_fact_layers + payload for analysis transparency.

    Returns (fact_lines, injected_records).
    """
    if conn is None:
        return [], []
    retrieved = retrieve_lessons_for_situation(conn, situation, top_k=top_k, min_score=min_score)
    lines: list[str] = []
    injected: list[dict[str, Any]] = []
    for row, sc in retrieved:
        lt = (row.get("lesson_text") or "").strip()
        if not lt:
            continue
        sid = str(row.get("id") or "")[:8]
        lines.append(
            f"FACT (lesson memory): [{sid}] (score={sc}) {lt[:1200]}"
            + ("…" if len(lt) > 1200 else "")
        )
        injected.append(
            {
                "id": row.get("id"),
                "score": sc,
                "validation_status": row.get("validation_status"),
                "symbol": row.get("symbol"),
                "regime_tag": row.get("regime_tag"),
                "preview": lt[:240],
                "behavior_effect": behavior_effect_from_row(row),
            }
        )
    return lines, injected
