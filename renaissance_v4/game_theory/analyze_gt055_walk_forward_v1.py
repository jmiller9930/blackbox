"""
GT055 — Triple-barrier labels + walk-forward proof (training / test split).

Reads ``student_learning_records_v1.jsonl`` for ``{job_id}-pass2``, chronologically splits rows,
builds label memory from the **train** slice only (by ``signature_hash_v1``), evaluates a **test-only**
decision rule on the **test** slice without peeking at train outcomes for the same row's policy
inputs beyond prior-window aggregates.

Decision rule (Directive GT055):

* ``label_avg_train > 0`` → allow (strategy takes trade PnL).
* ``label_avg_train < 0`` → block (PnL contribution 0).
* ``label_avg_train == 0`` (neutral mean) → no_trade / flat (PnL contribution 0).

``label_avg_train`` for a test row uses training rows sharing the same ``signature_hash_v1``;
if none, falls back to **global** train label mean.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    # .../<repo>/renaissance_v4/game_theory/this_file.py → repo root is parents[2]
    return Path(__file__).resolve().parents[2]


def _decision_at_ms(rec: dict[str, Any]) -> int:
    so = rec.get("student_output")
    if isinstance(so, dict):
        try:
            return int(so.get("decision_at_ms") or 0)
        except (TypeError, ValueError):
            pass
    return 0


def _sig_hash(rec: dict[str, Any]) -> str | None:
    pps = rec.get("perps_pattern_signature_v1")
    if isinstance(pps, dict):
        h = pps.get("signature_hash_v1")
        return str(h).strip() if h else None
    return None


def _referee(rec: dict[str, Any]) -> dict[str, Any]:
    ref = rec.get("referee_outcome_subset")
    return ref if isinstance(ref, dict) else {}


def analyze_gt055_walk_forward_v1(
    *,
    store_path: Path,
    job_id: str,
    train_fraction: float = 0.6,
    closed_trades: int | None = None,
) -> dict[str, Any]:
    jid = str(job_id).strip()
    pass2 = f"{jid}-pass2"
    rows: list[dict[str, Any]] = []
    p = Path(store_path)
    if not p.is_file():
        return {
            "job_id": jid,
            "closed_trades": int(closed_trades) if closed_trades is not None else None,
            "error": "store_not_found",
            "verdict": "INSUFFICIENT_DATA",
        }
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                doc = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(doc, dict) and str(doc.get("run_id") or "") == pass2:
                rows.append(doc)

    rows.sort(key=_decision_at_ms)
    n = len(rows)
    if n < 2:
        return {
            "job_id": jid,
            "closed_trades": int(closed_trades) if closed_trades is not None else None,
            "pass2_rows": n,
            "verdict": "INSUFFICIENT_DATA",
            "error": "need_at_least_2_pass2_rows",
        }

    tf = float(train_fraction)
    if not (0.5 <= tf < 1.0):
        tf = 0.6
    split = int(math.floor(tf * n))
    split = max(1, min(n - 1, split))
    train_rows = rows[:split]
    test_rows = rows[split:]

    def _labels(rs: list[dict[str, Any]]) -> list[int]:
        out: list[int] = []
        for r in rs:
            lab = _referee(r).get("triple_barrier_label_v1")
            if lab is None:
                continue
            try:
                out.append(int(lab))
            except (TypeError, ValueError):
                continue
        return out

    train_labels = _labels(train_rows)
    all_labels = _labels(rows)

    if not train_labels:
        return {
            "job_id": jid,
            "closed_trades": int(closed_trades) if closed_trades is not None else None,
            "pass2_rows": n,
            "train_rows": len(train_rows),
            "test_rows": len(test_rows),
            "verdict": "INSUFFICIENT_DATA",
            "error": "missing_triple_barrier_label_v1_on_training_rows",
        }

    sig_map: dict[str, list[int]] = {}
    for r in train_rows:
        lab = _referee(r).get("triple_barrier_label_v1")
        sh = _sig_hash(r)
        if lab is None or sh is None:
            continue
        try:
            ilab = int(lab)
        except (TypeError, ValueError):
            continue
        sig_map.setdefault(sh, []).append(ilab)

    def _mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    global_train_avg = _mean([float(x) for x in train_labels])

    def _train_avg_for_sig(sh: str | None) -> float:
        if sh and sh in sig_map and sig_map[sh]:
            return _mean([float(x) for x in sig_map[sh]])
        return global_train_avg

    test_pnls: list[float] = []
    loss_avoided = 0
    test_label_pnls_pos: list[float] = []
    test_label_pnls_neg: list[float] = []

    for r in test_rows:
        ref = _referee(r)
        try:
            pnl = float(ref.get("pnl"))
        except (TypeError, ValueError):
            continue
        lab = ref.get("triple_barrier_label_v1")
        try:
            ilab = int(lab) if lab is not None else None
        except (TypeError, ValueError):
            ilab = None
        if ilab == 1:
            test_label_pnls_pos.append(pnl)
        elif ilab == -1:
            test_label_pnls_neg.append(pnl)

        sh = _sig_hash(r)
        avg_tr = _train_avg_for_sig(sh)
        if avg_tr > 0.0:
            allow = True
        elif avg_tr < 0.0:
            allow = False
        else:
            allow = False
        if allow:
            test_pnls.append(pnl)
        else:
            if pnl < 0.0:
                loss_avoided += 1

    test_pnl = sum(test_pnls)

    def _safe_avg(xs: list[float]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    train_label_avg = round(global_train_avg, 10)
    test_labels_only = _labels(test_rows)
    test_label_avg = round(_mean([float(x) for x in test_labels_only]), 10) if test_labels_only else None

    pos_n = sum(1 for x in all_labels if x == 1)
    neg_n = sum(1 for x in all_labels if x == -1)
    neu_n = sum(1 for x in all_labels if x == 0)

    lbl_pos_avg = _safe_avg(test_label_pnls_pos)
    lbl_neg_avg = _safe_avg(test_label_pnls_neg)

    checks = {
        "label_positive_avg_pnl_gt_label_negative": None,
        "test_loss_avoided_count_gt_0": loss_avoided > 0,
        "test_pnl_non_negative": test_pnl >= 0.0,
    }
    if lbl_pos_avg is not None and lbl_neg_avg is not None:
        checks["label_positive_avg_pnl_gt_label_negative"] = bool(lbl_pos_avg > lbl_neg_avg)

    proven = bool(
        checks.get("label_positive_avg_pnl_gt_label_negative") is True
        and checks["test_loss_avoided_count_gt_0"]
        and checks["test_pnl_non_negative"]
    )

    def _yn(b: bool | None) -> str:
        if b is True:
            return "YES"
        if b is False:
            return "NO"
        return "N/A"

    required_yes_no = {
        "label_positive_avg_pnl_gt_label_negative": _yn(checks.get("label_positive_avg_pnl_gt_label_negative")),
        "test_loss_avoided_count_gt_0": _yn(checks["test_loss_avoided_count_gt_0"]),
        "test_pnl_non_negative": _yn(checks["test_pnl_non_negative"]),
    }

    verdict = "LABEL_LEARNING_PROVEN" if proven else "LABEL_LEARNING_NOT_PROVEN"
    if n < 10 or len(test_rows) < 2:
        verdict = "INSUFFICIENT_DATA"

    out: dict[str, Any] = {
        "job_id": jid,
        "closed_trades": int(closed_trades) if closed_trades is not None else None,
        "pass2_rows": n,
        "train_rows": len(train_rows),
        "test_rows": len(test_rows),
        "train_fraction_config": tf,
        "label_distribution": {
            "positive": pos_n,
            "negative": neg_n,
            "neutral": neu_n,
        },
        "train_label_avg": train_label_avg,
        "test_label_avg": test_label_avg,
        "test_pnl": round(test_pnl, 10),
        "test_loss_avoided_count": int(loss_avoided),
        "label_positive_avg_pnl": None if lbl_pos_avg is None else round(lbl_pos_avg, 10),
        "label_negative_avg_pnl": None if lbl_neg_avg is None else round(lbl_neg_avg, 10),
        "checks": checks,
        "required_yes_no": required_yes_no,
        "verdict": verdict,
        "signature_groups_in_train": len(sig_map),
    }
    return out


def main_cli() -> int:
    import argparse
    import sys

    repo = _repo_root()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job-id", type=str, required=True)
    ap.add_argument("--store", type=str, default="")
    ap.add_argument("--train-fraction", type=float, default=0.6)
    args = ap.parse_args()
    jid = str(args.job_id).strip()
    store = Path(args.store).expanduser() if args.store else repo / "runtime" / "gt048_cycle" / jid / "student_learning_records_v1.jsonl"
    rep = analyze_gt055_walk_forward_v1(store_path=store, job_id=jid, train_fraction=float(args.train_fraction))
    print(json.dumps(rep, indent=2))
    v = str(rep.get("verdict") or "")
    return 0 if v == "LABEL_LEARNING_PROVEN" else 3


__all__ = ["analyze_gt055_walk_forward_v1", "main_cli"]
