#!/usr/bin/env python3
"""
Universal NDE source → extracted → concepts → staging JSONL (+ report).

Deploy path: /data/NDE/tools/nde_source_processor.py
Repo path:    nde/tools/nde_source_processor.py

Flow:
  <domain>/sources/raw/* → extracted text → concept cards (JSONL) → staging JSONL → report

Does not run training.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as e:  # pragma: no cover
    raise SystemExit("PyYAML required: pip install pyyaml") from e


DEFAULT_NDE_ROOT = Path(os.environ.get("NDE_ROOT", "/data/NDE"))


def _read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    t = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    t = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return ""
    try:
        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts).strip()
    except Exception:
        return ""


def extract_json(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _read_text_file(path)
    return json.dumps(data, indent=2, ensure_ascii=False)


def extract_csv(path: Path) -> str:
    lines: list[str] = []
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i >= 500:
                    break
                lines.append(" | ".join(cell.strip() for cell in row))
    except Exception:
        return _read_text_file(path)
    return "\n".join(lines)


def extract_source(path: Path, allowed: set[str]) -> tuple[str, str | None]:
    """Returns (text, warning_or_none)."""
    suf = path.suffix.lower().lstrip(".")
    if suf not in allowed:
        return "", f"skipped extension .{suf}"
    if suf in ("txt", "md"):
        return _read_text_file(path), None
    if suf == "html" or suf == "htm":
        return _strip_html(_read_text_file(path)), None
    if suf == "pdf":
        t = extract_pdf(path)
        if not t.strip():
            return "", "pdf extraction empty or pypdf/PyPDF2 not installed"
        return t, None
    if suf == "json":
        return extract_json(path), None
    if suf == "csv":
        return extract_csv(path), None
    return "", f"unhandled .{suf}"


def stable_source_id(rel_key: str, content_hash: str) -> str:
    h = hashlib.sha256((rel_key + "\n" + content_hash).encode()).hexdigest()[:12]
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", rel_key)[:80].strip("_").lower() or "src"
    return f"{safe}_{h}"


def chunk_text(text: str, chunk_chars: int, overlap: int) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    i = 0
    step = max(1, chunk_chars - overlap)
    while i < len(text):
        chunks.append(text[i : i + chunk_chars].strip())
        i += step
    return [c for c in chunks if len(c) >= 40]


def load_domain_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description="NDE universal source processor")
    ap.add_argument("--domain", required=True, help="Domain folder name under NDE root")
    ap.add_argument("--nde-root", type=Path, default=DEFAULT_NDE_ROOT, help="NDE root (default /data/NDE)")
    ap.add_argument("--input", type=Path, default=None, help="Raw sources directory")
    ap.add_argument("--output", type=Path, default=None, help="Staging JSONL output path")
    ap.add_argument("--config", type=Path, default=None, help="domain_config.yaml path")
    args = ap.parse_args()

    nde = Path(args.nde_root).resolve()
    domain = args.domain.strip()
    dom_root = nde / domain
    cfg_path = args.config or (dom_root / "domain_config.yaml")
    if not cfg_path.is_file():
        raise SystemExit(f"Missing domain config: {cfg_path}")

    cfg = load_domain_config(cfg_path)
    allowed = {x.lower().lstrip(".") for x in cfg.get("allowed_source_types", [])}

    def _dom_path(key: str, default: Path) -> Path:
        v = cfg.get("paths", {}).get(key)
        if v is None:
            return default.resolve()
        p = Path(v)
        return (p.resolve() if p.is_absolute() else (dom_root / p).resolve())

    raw_default = dom_root / "sources" / "raw"
    raw_dir = Path(args.input).resolve() if args.input else _dom_path("raw", raw_default)

    out_cfg = cfg.get("output", {})
    staging_default = dom_root / "datasets" / "staging" / out_cfg.get("staging_filename", "staging.jsonl")
    staging_out = Path(args.output).resolve() if args.output else staging_default.resolve()

    extracted_dir = _dom_path("extracted", dom_root / "sources" / "extracted")
    concepts_dir = _dom_path("concepts", dom_root / "sources" / "concepts")
    reports_dir = _dom_path("reports", dom_root / "reports")

    concepts_name = out_cfg.get("concepts_filename", "concepts_v0.1.jsonl")
    report_name = out_cfg.get("report_filename", "source_processor_report_v0.1.md")

    concepts_path = concepts_dir / concepts_name
    report_path = reports_dir / report_name

    extracted_dir.mkdir(parents=True, exist_ok=True)
    concepts_dir.mkdir(parents=True, exist_ok=True)
    staging_out.parent.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    chunk_chars = int(cfg.get("chunk_chars", 1200))
    chunk_overlap = int(cfg.get("chunk_overlap", 200))
    target_rows = int(cfg.get("target_row_count", 100))
    adv_frac = float(cfg.get("adversarial_ratio", 0.7))

    verifier = cfg.get("verifier", {})
    instr_template = str(
        verifier.get(
            "instruction_template",
            "Verify the claim using exactly four sections: Claim reviewed:, Math verdict:, "
            "DATA evidence required:, Final verifier status:",
        )
    )

    ext_schema = cfg.get("concept_schema_extensions", {})

    # --- extract ---
    warnings: list[str] = []
    extracted_manifest: list[dict[str, Any]] = []
    all_chunks_meta: list[tuple[str, str, str]] = []  # source_id, segment_id, chunk_text

    if not raw_dir.is_dir():
        raise SystemExit(f"Input directory not found: {raw_dir}")

    for fp in sorted(raw_dir.rglob("*")):
        if not fp.is_file():
            continue
        rel = str(fp.relative_to(raw_dir))
        text, warn = extract_source(fp, allowed)
        if warn:
            warnings.append(f"{rel}: {warn}")
            continue
        if not text or len(text.strip()) < 10:
            warnings.append(f"{rel}: empty or trivial extraction")
            continue
        h = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        sid = stable_source_id(rel, h)
        meta = {"source_id": sid, "relative_path": rel, "sha256": h, "bytes": fp.stat().st_size}
        extracted_manifest.append(meta)

        out_txt = extracted_dir / f"{sid}.txt"
        out_txt.write_text(text, encoding="utf-8")
        (extracted_dir / f"{sid}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        for si, chunk in enumerate(chunk_text(text, chunk_chars, chunk_overlap)):
            seg_id = f"seg_{si}"
            all_chunks_meta.append((sid, seg_id, chunk))

    if not all_chunks_meta:
        raise SystemExit("No extractable chunks — add sources under raw/ or fix extraction.")

    # --- concepts JSONL ---
    concept_records: list[dict[str, Any]] = []
    for sid, seg_id, chunk in all_chunks_meta:
        cid = "c_" + hashlib.sha256(f"{sid}:{seg_id}:{chunk[:200]}".encode()).hexdigest()[:16]
        claims = [chunk[:240].strip() + ("…" if len(chunk) > 240 else "")]
        rec = {
            "concept_id": cid,
            "domain": cfg.get("domain", domain),
            "source_ids": [{"source_id": sid, "segment_id": seg_id}],
            "text_excerpt": chunk[:4000],
            "claims": claims,
            "extensions": ext_schema,
            "risk_notes": cfg.get("default_risk_notes", "Over-interpretation without cited controls."),
        }
        concept_records.append(rec)

    with concepts_path.open("w", encoding="utf-8") as f:
        for rec in concept_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # --- staging JSONL (cycle concepts to target_row_count) ---
    n_adv = int(round(target_rows * adv_frac))
    n_clean = target_rows - n_adv

    staging_rows: list[dict[str, Any]] = []

    def four_section_output(*, claim: str, verdict: str, data_lines: list[str], status: str) -> str:
        body = "\n".join(f"- {x}" for x in data_lines)
        return (
            f"Claim reviewed:\n{claim.strip()}\n\n"
            f"Math verdict:\n{verdict.strip()}\n\n"
            f"DATA evidence required:\n{body}\n\n"
            f"Final verifier status:\n{status.strip()}"
        )

    data_lines_template = cfg.get(
        "data_evidence_template",
        [
            "Control / framework mapping / IDs referenced in source excerpts",
            "System logs (UTC timestamps, facility, collector source)",
            "IAM evidence (roles, MFA enrollment state where applicable)",
            "Patch or vuln posture (versions, CVE IDs when cited)",
            "Audit artifacts (reviews, assessor requests, POA&M pointers)",
        ],
    )

    trap_templates = cfg.get(
        "adversarial_claim_templates",
        [
            "The organization fully complies with all controls related to this excerpt without independent verification.",
            "This excerpt alone proves MFA is universally enforced.",
            "Logging can be skipped because no breach was disclosed.",
            "Quarterly patching is sufficient for every system referenced here.",
        ],
    )

    ci = 0
    for i in range(target_rows):
        rec = concept_records[ci % len(concept_records)]
        ci += 1
        cid = rec["concept_id"]
        sid_pack = rec["source_ids"][0]
        src_line = rec["claims"][0]

        src_ids_field = [
            {
                "concept_id": cid,
                "source_id": sid_pack["source_id"],
                "segment_id": sid_pack["segment_id"],
            }
        ]

        if i < n_adv:
            trap = trap_templates[i % len(trap_templates)]
            inp = f"[VERIFY] {trap} (Derived from concept {cid})."
            out = four_section_output(
                claim=trap,
                verdict="Incorrect — unsupported inference from excerpt without corroborating controls and artifacts.",
                data_lines=list(data_lines_template),
                status="FAIL",
            )
            staging_rows.append(
                {
                    "instruction": instr_template,
                    "input": inp + "\n",
                    "output": out,
                    "source_ids": src_ids_field,
                    "category": cfg.get("domain", domain),
                    "adversarial": True,
                    "quality_flags": ["concept_derived", "trap"],
                }
            )
        else:
            inp = f"[VERIFY] Assess whether this excerpt supports a compliance conclusion without extra evidence: {src_line}"
            out = four_section_output(
                claim="The excerpt requires mapping to controls and corroborating artifacts before compliance conclusions.",
                verdict="Correct — excerpt alone is insufficient; conclusions remain unsupported until DATA listed is collected.",
                data_lines=list(data_lines_template),
                status="PASS",
            )
            staging_rows.append(
                {
                    "instruction": instr_template,
                    "input": inp + "\n",
                    "output": out,
                    "source_ids": src_ids_field,
                    "category": cfg.get("domain", domain),
                    "adversarial": False,
                    "quality_flags": ["concept_derived", "hedged_reference"],
                }
            )

    # Validate source_ids
    for j, row in enumerate(staging_rows):
        sid = row.get("source_ids")
        if not sid or not isinstance(sid, list) or not sid[0].get("source_id"):
            raise SystemExit(f"Row {j} missing valid source_ids")

    with staging_out.open("w", encoding="utf-8") as f:
        for row in staging_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report_lines = [
        f"# Source processor report — {cfg.get('domain', domain)}",
        "",
        f"**Generated:** `{ts}` UTC",
        f"**NDE root:** `{nde}`",
        f"**Domain:** `{domain}`",
        f"**Config:** `{cfg_path}`",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Raw files processed (extracted non-empty) | {len(extracted_manifest)} |",
        f"| Concept segments | {len(concept_records)} |",
        f"| Staging rows | {len(staging_rows)} |",
        f"| Adversarial (target ratio {adv_frac:.2f}) | {n_adv} |",
        f"| Non-adversarial | {n_clean} |",
        "",
        "## Outputs",
        "",
        f"- **Extracted:** `{extracted_dir}`",
        f"- **Concepts:** `{concepts_path}`",
        f"- **Staging:** `{staging_out}`",
        "",
        "## Source traceability",
        "",
        "Every staging row includes `source_ids` with `concept_id`, `source_id`, and `segment_id`.",
        "",
        "## Warnings",
        "",
    ]
    report_lines.extend([f"- {w}" for w in warnings] if warnings else ["- (none)"])
    report_lines.extend(
        [
        "",
        "## Policy",
        "",
        "Build aligns with `source_to_training_policy_v0.1.md` (concepts + provenance). Training not run.",
        "",
        ]
    )
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "concepts_path": str(concepts_path),
                "staging_path": str(staging_out),
                "report_path": str(report_path),
                "extracted_dir": str(extracted_dir),
                "rows": len(staging_rows),
                "concept_segments": len(concept_records),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
