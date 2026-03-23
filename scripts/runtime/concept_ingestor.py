#!/usr/bin/env python3
"""
Phase 3.7 — Concept intake: add/update staged concepts in staging_registry.json.

Does not read or write registry.json. No automatic promotion, no DB, no Anna wiring.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _paths import repo_root
from anna_modules.util import utc_now

STAGING_KIND = "trading_concept_staging_v1"
SOURCE_TYPES = frozenset({"expert", "system", "external"})
STATUSES = frozenset({"draft", "under_test", "validated", "rejected"})


def staging_path() -> Path:
    return repo_root() / "data" / "concepts" / "staging_registry.json"


def load_staging() -> dict[str, Any] | dict[str, str]:
    p = staging_path()
    if not p.is_file():
        return {"error": "staging_file_missing", "path": str(p)}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"error": "invalid_json", "detail": str(e)}
    if data.get("kind") != STAGING_KIND:
        return {"error": "unexpected_kind", "kind": data.get("kind")}
    if not isinstance(data.get("staged_concepts"), list):
        return {"error": "staged_concepts_invalid"}
    return data


def save_staging(data: dict[str, Any]) -> None:
    data["generated_at"] = utc_now()
    p = staging_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def find_staged(concepts: list[dict[str, Any]], concept_id: str) -> tuple[int, dict[str, Any] | None]:
    cid = concept_id.strip().lower()
    for i, c in enumerate(concepts):
        if isinstance(c, dict) and str(c.get("concept_id", "")).lower() == cid:
            return i, c
    return -1, None


def parse_signals(s: str) -> list[str]:
    parts = [x.strip() for x in s.split(",")]
    return [x for x in parts if x]


def parse_evidence(s: str | None) -> list[str]:
    if not s or not s.strip():
        return []
    s = s.strip()
    if s.startswith("["):
        try:
            v = json.loads(s)
            if isinstance(v, list):
                return [str(x) for x in v]
        except json.JSONDecodeError:
            pass
    return [x.strip() for x in s.split(",") if x.strip()]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Trading concept staging (Phase 3.7).")
    p.add_argument("--add", action="store_true", help="Add a staged concept")
    p.add_argument("--update", metavar="CONCEPT_ID", help="Update an existing staged concept")
    p.add_argument("--list", action="store_true", dest="list_", help="Print full staging JSON")
    p.add_argument("--concept", metavar="ID", help="Print one staged concept by id")

    p.add_argument("--concept-id", dest="concept_id", default=None)
    p.add_argument("--source-type", default=None)
    p.add_argument("--definition", default=None)
    p.add_argument("--rationale", default=None)
    p.add_argument("--signals", default=None, help="Comma-separated signal names")
    p.add_argument("--impact", default=None)
    p.add_argument("--source-reference", default="")
    p.add_argument(
        "--evidence-links",
        default="",
        help="Comma-separated URLs or JSON array string",
    )
    p.add_argument(
        "--status",
        choices=sorted(STATUSES),
        help="With --update: new lifecycle status",
    )

    args = p.parse_args(argv)

    modes = sum(
        bool(x)
        for x in (args.add, args.update is not None, args.list_, args.concept is not None)
    )
    if modes != 1:
        print(
            json.dumps(
                {
                    "error": "exactly_one_mode",
                    "hint": "use one of --add, --update, --list, --concept",
                },
                indent=2,
            )
        )
        return 1

    if args.list_:
        blob = load_staging()
        print(json.dumps(blob, indent=2))
        return 0 if "error" not in blob else 1

    if args.concept is not None:
        blob = load_staging()
        if "error" in blob:
            print(json.dumps(blob, indent=2))
            return 1
        _, c = find_staged(blob["staged_concepts"], args.concept)
        if c is None:
            print(json.dumps({"found": False, "concept_id": args.concept}))
            return 0
        print(json.dumps({"found": True, "concept": c}, indent=2))
        return 0

    if args.add:
        missing = [
            n
            for n, v in (
                ("--concept-id", args.concept_id),
                ("--source-type", args.source_type),
                ("--definition", args.definition),
                ("--rationale", args.rationale),
                ("--signals", args.signals),
                ("--impact", args.impact),
            )
            if not v or not str(v).strip()
        ]
        if missing:
            print(json.dumps({"error": "missing_fields", "fields": missing}))
            return 1

        st = args.source_type.strip().lower()
        if st not in SOURCE_TYPES:
            print(json.dumps({"error": "invalid_source_type", "allowed": sorted(SOURCE_TYPES)}))
            return 1

        blob = load_staging()
        if "error" in blob:
            print(json.dumps(blob, indent=2))
            return 1

        concepts = blob["staged_concepts"]
        _, existing = find_staged(concepts, args.concept_id)
        if existing is not None:
            print(json.dumps({"error": "concept_id_exists", "concept_id": args.concept_id}))
            return 1

        now = utc_now()
        signals = parse_signals(args.signals)
        entry: dict[str, Any] = {
            "concept_id": args.concept_id.strip(),
            "source_type": st,
            "source_reference": (args.source_reference or "").strip(),
            "proposed_definition": args.definition.strip(),
            "rationale": args.rationale.strip(),
            "proposed_signals": signals,
            "expected_impact": args.impact.strip(),
            "status": "draft",
            "evidence_links": parse_evidence(args.evidence_links),
            "created_at": now,
            "updated_at": now,
            "version": 1,
            "status_history": [],
        }
        concepts.append(entry)
        save_staging(blob)
        print(json.dumps(entry, indent=2))
        return 0

    # --update
    assert args.update is not None
    if not args.status:
        print(json.dumps({"error": "missing_status", "hint": "use --status with --update"}))
        return 1

    new_status = args.status.strip().lower()
    blob = load_staging()
    if "error" in blob:
        print(json.dumps(blob, indent=2))
        return 1

    concepts = blob["staged_concepts"]
    idx, prev = find_staged(concepts, args.update)
    if prev is None:
        print(json.dumps({"error": "not_found", "concept_id": args.update}))
        return 1

    old_status = str(prev.get("status", "draft"))
    if old_status == new_status:
        print(json.dumps({"error": "no_change", "status": old_status}))
        return 1

    now = utc_now()
    hist = list(prev.get("status_history") or [])
    if not isinstance(hist, list):
        hist = []
    hist.append({"at": now, "from": old_status, "to": new_status})

    updated = dict(prev)
    updated["status"] = new_status
    updated["updated_at"] = now
    updated["version"] = int(prev.get("version") or 1) + 1
    updated["status_history"] = hist

    concepts[idx] = updated
    save_staging(blob)
    print(json.dumps(updated, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
