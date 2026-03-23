#!/usr/bin/env python3
"""
Phase 3.5 — Read-only trading concept registry utility.

Loads `data/concepts/registry.json` (Git-versioned). No runtime mutation, no DB, no Anna wiring.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _paths import repo_root

READER_KIND = "concept_registry_reader_v1"
READER_SCHEMA = 1


def registry_path() -> Path:
    return repo_root() / "data" / "concepts" / "registry.json"


def load_registry() -> dict[str, Any]:
    p = registry_path()
    if not p.is_file():
        return {"error": "registry_file_missing", "path": str(p)}
    raw = p.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": "invalid_json", "detail": str(e)}

    if data.get("kind") != "trading_concept_registry_v1":
        return {"error": "unexpected_registry_kind", "kind": data.get("kind")}

    return data


def find_concept(concepts: list[dict[str, Any]], concept_id: str) -> dict[str, Any] | None:
    cid = concept_id.strip().lower()
    for c in concepts:
        if str(c.get("concept_id", "")).lower() == cid:
            return c
    return None


def search_concepts(concepts: list[dict[str, Any]], q: str) -> list[dict[str, Any]]:
    ql = q.lower().strip()
    if not ql:
        return []
    out: list[dict[str, Any]] = []
    for c in concepts:
        hay = " ".join(
            [
                str(c.get("concept_id", "")),
                str(c.get("name", "")),
                str(c.get("definition", "")),
                str(c.get("trader_meaning", "")),
            ]
        ).lower()
        if ql in hay:
            out.append(c)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Read-only concept registry queries (JSON)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="List concept summaries")
    g.add_argument("--concept", metavar="ID", help="Fetch one concept by concept_id")
    g.add_argument("--search", metavar="KEYWORD", help="Substring match on id/name/definition/trader_meaning")
    args = p.parse_args(argv)

    data = load_registry()
    if "error" in data:
        print(json.dumps({"kind": READER_KIND, "schema_version": READER_SCHEMA, "action": "error", **data}, indent=2))
        return 2

    concepts = data.get("concepts") or []
    if not isinstance(concepts, list):
        print(
            json.dumps(
                {"kind": READER_KIND, "schema_version": READER_SCHEMA, "action": "error", "error": "invalid_concepts_array"},
                indent=2,
            )
        )
        return 2

    if args.list:
        summaries = [
            {
                "concept_id": c.get("concept_id"),
                "name": c.get("name"),
                "status": c.get("status"),
                "version": c.get("version"),
            }
            for c in concepts
            if isinstance(c, dict)
        ]
        out = {
            "kind": READER_KIND,
            "schema_version": READER_SCHEMA,
            "action": "list",
            "registry_kind": data.get("kind"),
            "registry_schema_version": data.get("schema_version"),
            "count": len(summaries),
            "concepts": summaries,
        }
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    if args.concept is not None:
        hit = find_concept(concepts, args.concept)
        if hit is None:
            print(
                json.dumps(
                    {
                        "kind": READER_KIND,
                        "schema_version": READER_SCHEMA,
                        "action": "get",
                        "found": False,
                        "concept_id": args.concept.strip(),
                        "error": "concept_not_found",
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return 3
        print(
            json.dumps(
                {
                    "kind": READER_KIND,
                    "schema_version": READER_SCHEMA,
                    "action": "get",
                    "found": True,
                    "concept": hit,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    if args.search is not None:
        matches = search_concepts(concepts, args.search)
        print(
            json.dumps(
                {
                    "kind": READER_KIND,
                    "schema_version": READER_SCHEMA,
                    "action": "search",
                    "query": args.search.strip(),
                    "match_count": len(matches),
                    "concepts": matches,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
