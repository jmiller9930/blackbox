#!/usr/bin/env python3
"""
FinQuant-1 — QLoRA adapter training (smoke or full). Does not modify Blackbox.

Requires GPU + CUDA (trx40-class). Install:
  pip install -r finquant/requirements-finquant-training.txt

Deploy paths:
  /data/finquant-1/training/train_qlora.py
  /data/finquant-1/training/config_v0.1.yaml

Phase 3 smoke:
  export FINQUANT_BASE=/data/finquant-1
  python3 finquant/training/train_qlora.py smoke --config finquant/training/config_v0.1.yaml

Phase 6 full (after approval only):
  python3 finquant/training/train_qlora.py full --config finquant/training/config_v0.1.yaml

Writes smoke training report:
  {FINQUANT_BASE}/reports/smoke_training_report.md   (smoke mode only)
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import random
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml


def finquant_base() -> Path:
    env = (os.environ.get("FINQUANT_BASE") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def load_config(path: Path, base: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    rel = Path(raw["data"]["staging_jsonl"])
    data_path = rel if rel.is_absolute() else (base / rel)
    raw["_resolved_staging"] = data_path.resolve()
    return raw


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def format_example_text(tokenizer: Any, row: dict[str, Any]) -> str:
    instruction = str(row.get("instruction") or "")
    inp = str(row.get("input") or "")
    output = str(row.get("output") or "")
    user = f"{instruction}\n\n{inp}".strip()
    messages = [
        {"role": "user", "content": user},
        {"role": "assistant", "content": output},
    ]
    tmpl = getattr(tokenizer, "chat_template", None)
    if tmpl:
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
    return (
        "<|im_start|>user\n"
        + user
        + "<|im_end|>\n<|im_start|>assistant\n"
        + output
        + "<|im_end|>"
    )


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch

        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        torch.use_deterministic_algorithms(False)
    except Exception:
        pass


def write_smoke_report(
    base: Path,
    *,
    mode: str,
    cfg_path: Path,
    staging: Path,
    out_dir: Path,
    log_history: list[dict[str, Any]],
    extra: str = "",
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    host = socket.gethostname()
    lines = [
        "# FinQuant-1 — smoke training report",
        "",
        f"**Generated:** `{ts}` UTC",
        f"**Host:** `{host}`",
        f"**Mode:** `{mode}`",
        f"**Config:** `{cfg_path}`",
        f"**Staging:** `{staging}`",
        f"**Output:** `{out_dir}`",
        "",
        "## Loss log (trainer history tail)",
        "",
        "```json",
        json.dumps(log_history[-40:], indent=2),
        "```",
        "",
        "## Acceptance checklist",
        "",
        "| Item | Notes |",
        "|------|-------|",
        "| Training starts without error | See log history |",
        "| Loss logs appear | non-empty log_history after steps |",
        "| Adapter checkpoint saved | see output dir / checkpoint-* |",
        "",
        extra,
    ]
    report = base / "reports" / "smoke_training_report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {report}")


def main() -> None:
    ap = argparse.ArgumentParser(description="FinQuant-1 QLoRA training")
    ap.add_argument("mode", choices=("smoke", "full"), help="smoke = short run; full = v0.1 production run")
    ap.add_argument(
        "--config",
        type=Path,
        default=None,
        help="YAML config (default: finquant/training/config_v0.1.yaml next to this script)",
    )
    ap.add_argument("--base", type=Path, default=None, help="FINQUANT_BASE override")
    args = ap.parse_args()

    base = (args.base or finquant_base()).resolve()
    cfg_path = args.config or (Path(__file__).resolve().parent / "config_v0.1.yaml")
    cfg = load_config(cfg_path, base)

    staging = cfg["_resolved_staging"]
    if not staging.is_file():
        raise SystemExit(f"Staging JSONL not found: {staging} — run source_to_training.py build first.")

    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from trl import SFTConfig, SFTTrainer
    except ImportError as e:
        raise SystemExit(
            "Missing training deps. Install: pip install -r finquant/requirements-finquant-training.txt\n" + str(e)
        ) from e

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU required for 4-bit QLoRA (run on trx40 or equivalent).")

    train_section = cfg["training"][args.mode]
    seed = int(cfg["training"]["seed"])
    set_seed(seed)

    rows = read_jsonl(staging)
    texts = []
    tok_path = cfg["model_name_or_path"]
    tokenizer = AutoTokenizer.from_pretrained(tok_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    for row in rows:
        texts.append({"text": format_example_text(tokenizer, row)})

    ds = Dataset.from_list(texts)

    qconf = cfg["quantization"]
    compute_dtype = getattr(torch, str(qconf.get("bnb_4bit_compute_dtype", "bfloat16")))
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type=qconf.get("bnb_4bit_quant_type", "nf4"),
        bnb_4bit_use_double_quant=bool(qconf.get("bnb_4bit_use_double_quant", True)),
        bnb_4bit_compute_dtype=compute_dtype,
    )

    model = AutoModelForCausalLM.from_pretrained(
        tok_path,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    lc = cfg["lora"]
    peft_config = LoraConfig(
        r=int(lc["r"]),
        lora_alpha=int(lc["lora_alpha"]),
        lora_dropout=float(lc["lora_dropout"]),
        bias=str(lc.get("bias", "none")),
        task_type=TaskType.CAUSAL_LM,
        target_modules=list(lc["target_modules"]),
    )
    model = get_peft_model(model, peft_config)

    out_dir = base / train_section["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)

    max_seq = int(cfg["data"].get("max_seq_length", 4096))
    common = cfg["training"]
    sft_kw: dict[str, Any] = {
        "output_dir": str(out_dir),
        "max_steps": int(train_section["max_steps"]),
        "per_device_train_batch_size": int(train_section["per_device_train_batch_size"]),
        "gradient_accumulation_steps": int(train_section["gradient_accumulation_steps"]),
        "learning_rate": float(common["learning_rate"]),
        "lr_scheduler_type": str(common["lr_scheduler_type"]),
        "warmup_ratio": float(common["warmup_ratio"]),
        "weight_decay": float(common["weight_decay"]),
        "logging_steps": int(train_section["logging_steps"]),
        "save_steps": int(train_section["save_steps"]),
        "save_total_limit": int(train_section["save_total_limit"]),
        "bf16": bool(common.get("bf16", True)),
        "fp16": bool(common.get("fp16", False)),
        "gradient_checkpointing": bool(common.get("gradient_checkpointing", True)),
        "seed": seed,
        "report_to": "none",
        "dataset_text_field": "text",
        "max_length": max_seq,
    }
    sig = inspect.signature(SFTConfig.__init__)
    sft_kw = {k: v for k, v in sft_kw.items() if k in sig.parameters}
    if "max_length" not in sig.parameters and "max_seq_length" in sig.parameters:
        sft_kw["max_seq_length"] = max_seq
        sft_kw.pop("max_length", None)

    sft_args = SFTConfig(**sft_kw)

    trainer_kw: dict[str, Any] = {
        "model": model,
        "args": sft_args,
        "train_dataset": ds,
    }
    if "processing_class" in inspect.signature(SFTTrainer.__init__).parameters:
        trainer_kw["processing_class"] = tokenizer
    else:
        trainer_kw["tokenizer"] = tokenizer

    trainer = SFTTrainer(**trainer_kw)

    trainer.train()

    log_history = getattr(trainer.state, "log_history", []) or []
    trainer.save_model(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))

    if args.mode == "smoke":
        write_smoke_report(
            base,
            mode=args.mode,
            cfg_path=cfg_path,
            staging=staging,
            out_dir=out_dir,
            log_history=log_history,
            extra="## Status\n\n**Smoke run complete.** Review loss trend and checkpoint before full v0.1 training.\n",
        )

    print(json.dumps({"output_dir": str(out_dir), "mode": args.mode, "steps": train_section["max_steps"]}, indent=2))


if __name__ == "__main__":
    main()
