"""
Context-indexed answer memory (SQLite). Reuse only when intent/topic/question match.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from typing import Any

from anna_modules.util import utc_now
from learning_core.enforcement import is_reusable_by_source
from learning_core.store import create_learning_record


def _norm_q(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"[^\w\s\-?]", " ", t)
    return " ".join(t.split())


def extract_slots(text: str) -> dict[str, Any]:
    low = (text or "").lower()
    sym_m = re.search(r"\b(sol|btc|eth|sol-perp|btc-perp)\b", low)
    tf_m = re.search(r"\b(5m|15m|1h|4h|daily|5min)\b", low)
    return {
        "symbol": sym_m.group(1) if sym_m else None,
        "timeframe": tf_m.group(1) if tf_m else None,
        "question_mode": "live" if re.search(r"\b(live|my position|this trade)\b", low) else "general",
    }


def find_reusable_answer(
    conn: sqlite3.Connection,
    *,
    question_text: str,
    human_intent: dict[str, Any],
) -> dict[str, Any] | None:
    """Return latest matching row if intent+topic+normalized question align."""
    intent = str(human_intent.get("intent") or "")
    topic = str(human_intent.get("topic") or "")
    nq = _norm_q(question_text)
    row = conn.execute(
        """
        SELECT id, answer_text, answer_source, validation_status, human_intent_json, question_text
        FROM anna_context_memory
        WHERE intent = ? AND topic = ? AND lower(trim(question_text)) = ?
        ORDER BY datetime(created_at) DESC
        LIMIT 1
        """,
        (intent, topic, nq),
    ).fetchone()
    if not row:
        return None
    # 4.6.3.2 Part A enforcement: only validated learning records may be reused.
    if not is_reusable_by_source(
        conn,
        source="anna_context_memory",
        source_record_id=str(row[0]),
    ):
        return None
    return {
        "id": row[0],
        "answer_text": row[1],
        "answer_source": row[2],
        "validation_status": row[3],
        "human_intent_json": row[4],
        "question_text": row[5],
    }


def store_interaction(
    conn: sqlite3.Connection,
    *,
    question_text: str,
    answer_text: str,
    answer_source: str,
    human_intent: dict[str, Any],
    pipeline_meta: dict[str, Any],
    validation_status: str = "candidate",
) -> str:
    """Persist Q+A with context slots. New rows are always candidate until promoted."""
    now = utc_now()
    slots = extract_slots(question_text)
    rid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO anna_context_memory (
          id, created_at, updated_at, question_text, intent, topic, question_mode,
          symbol, timeframe, context_tags, answer_text, answer_source, validation_status,
          human_intent_json, pipeline_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rid,
            now,
            now,
            _norm_q(question_text),
            str(human_intent.get("intent") or ""),
            str(human_intent.get("topic") or ""),
            slots["question_mode"],
            slots["symbol"],
            slots["timeframe"],
            json.dumps([], ensure_ascii=False),
            answer_text,
            answer_source,
            validation_status,
            json.dumps(human_intent, ensure_ascii=False),
            json.dumps(pipeline_meta, ensure_ascii=False),
        ),
    )
    conn.commit()
    # Mirror into learning lifecycle as candidate (non-invasive: no decision-path influence yet).
    create_learning_record(
        conn,
        source="anna_context_memory",
        source_record_id=rid,
        content=answer_text,
        validation_notes=f"seeded from answer_source={answer_source}",
        state="candidate",
    )
    return rid
