#!/usr/bin/env python3
"""
Merge FinQuant QLoRA adapter into base weights and register with local Ollama.

Steps:
  1. Load base model (DeepSeek-R1-Distill-Qwen-7B) in float16
  2. Load PEFT adapter
  3. Merge + unload → full model
  4. Save to FINQUANT_BASE/models/finquant-1-qwen7b-v0.1-merged/
  5. Write Ollama Modelfile
  6. Run: ollama create finquant-1-qwen7b-v0.1

Usage (on trx40, inside venv):
  export FINQUANT_BASE=/data/NDE/finquant/agentic_v05
  python3 training/merge_adapter_to_ollama.py

  # With explicit paths:
  python3 training/merge_adapter_to_ollama.py \\
    --adapter $FINQUANT_BASE/adapters/finquant-1-qwen7b-v0.1 \\
    --merged-out $FINQUANT_BASE/models/finquant-1-qwen7b-v0.1-merged \\
    --model-tag finquant-1-qwen7b-v0.1 \\
    --ollama-url http://localhost:11434

Note: merge requires ~16 GB RAM / VRAM. Uses float16. BitsAndBytes NOT loaded here —
merge must run in full precision. If CUDA OOM, add --cpu-merge flag.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def default_base() -> Path:
    env = (os.environ.get("FINQUANT_BASE") or "").strip()
    return Path(env).expanduser().resolve() if env else Path("/data/NDE/finquant/agentic_v05")


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"[merge] $ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, check=check)


def merge_and_save(adapter_path: Path, merged_out: Path, cpu_merge: bool) -> None:
    print(f"[merge] Loading base model + adapter from {adapter_path}", flush=True)

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    adapter_cfg_path = adapter_path / "adapter_config.json"
    import json
    base_model_id = json.loads(adapter_cfg_path.read_text())["base_model_name_or_path"]
    print(f"[merge] Base model: {base_model_id}", flush=True)

    device = "cpu" if cpu_merge else "auto"
    dtype = torch.float16

    print("[merge] Loading tokenizer …", flush=True)
    tok = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True)

    print(f"[merge] Loading base model ({dtype}, device={device}) …", flush=True)
    base = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=dtype,
        device_map=device,
        trust_remote_code=True,
    )

    print("[merge] Attaching PEFT adapter …", flush=True)
    model = PeftModel.from_pretrained(base, str(adapter_path))

    print("[merge] Merging adapter weights …", flush=True)
    model = model.merge_and_unload()

    merged_out.mkdir(parents=True, exist_ok=True)
    print(f"[merge] Saving merged model to {merged_out} …", flush=True)
    model.save_pretrained(str(merged_out))
    tok.save_pretrained(str(merged_out))
    print("[merge] Merge complete.", flush=True)


def write_modelfile(merged_out: Path, model_tag: str) -> Path:
    """Write Ollama Modelfile that points at the merged safetensors."""
    # Ollama FROM can be a local directory containing safetensors + tokenizer
    mf_content = f"""FROM {merged_out}

PARAMETER temperature 0.1
PARAMETER top_p 0.9
PARAMETER num_ctx 8192
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|endoftext|>"

SYSTEM \"\"\"You are FinQuant, a disciplined quantitative crypto-perps reasoning agent.
P-1 NEVER LIE. Only use data in this prompt. Never invent values.
P-2 REASON WITH TOOLS. Cite specific indicator values in your thesis.
P-3 SELECTIVE ENTRY. Enter only when multiple signals align clearly.
P-4 PATTERN SIMILARITY. Weight governed memory records over fuzzy similarity.
Output valid JSON only per the stated contract. No freeform narrative outside JSON.\"\"\"
"""
    mf_path = merged_out / "Modelfile"
    mf_path.write_text(mf_content, encoding="utf-8")
    print(f"[merge] Modelfile written: {mf_path}", flush=True)
    return mf_path


def register_ollama(mf_path: Path, model_tag: str, ollama_url: str) -> None:
    env = os.environ.copy()
    env["OLLAMA_HOST"] = ollama_url
    print(f"[merge] Registering with Ollama as '{model_tag}' …", flush=True)
    result = subprocess.run(
        ["ollama", "create", model_tag, "-f", str(mf_path)],
        check=False, env=env
    )
    if result.returncode != 0:
        print(f"[merge] WARN: ollama create returned {result.returncode} — check manually.", flush=True)
    else:
        print(f"[merge] Ollama model '{model_tag}' registered.", flush=True)

    # Verify
    verify = subprocess.run(
        ["ollama", "show", model_tag],
        capture_output=True, text=True, check=False, env=env
    )
    if verify.returncode == 0:
        print(f"[merge] Verified — '{model_tag}' shows in Ollama.", flush=True)
    else:
        print(f"[merge] Could not verify — run: ollama list", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge FinQuant adapter → Ollama")
    ap.add_argument("--adapter", type=Path, default=None)
    ap.add_argument("--merged-out", type=Path, default=None)
    ap.add_argument("--model-tag", type=str, default="finquant-1-qwen7b-v0.1")
    ap.add_argument("--ollama-url", type=str, default="http://localhost:11434")
    ap.add_argument("--cpu-merge", action="store_true", help="Force CPU merge (slower, avoids VRAM)")
    ap.add_argument("--modelfile-only", action="store_true",
                    help="Skip merge (merged-out already exists), just write Modelfile and register")
    args = ap.parse_args()

    base = default_base()
    adapter = args.adapter or base / "adapters" / "finquant-1-qwen7b-v0.1"
    merged_out = args.merged_out or base / "models" / "finquant-1-qwen7b-v0.1-merged"

    if not adapter.is_dir():
        raise SystemExit(f"Adapter dir not found: {adapter}")

    if not args.modelfile_only:
        merge_and_save(adapter, merged_out, args.cpu_merge)
    else:
        if not merged_out.is_dir():
            raise SystemExit(f"--modelfile-only set but merged-out missing: {merged_out}")
        print(f"[merge] --modelfile-only: skipping merge, using {merged_out}", flush=True)

    mf_path = write_modelfile(merged_out, args.model_tag)
    register_ollama(mf_path, args.model_tag, args.ollama_url)

    print(f"\n[merge] Done. Test with:", flush=True)
    print(f'  ollama run {args.model_tag} "Respond with valid JSON only."', flush=True)
    print(f"\n[merge] Run exam with:", flush=True)
    print(f"  python3 training/exams/finquant_exam_proctor.py \\", flush=True)
    print(f"    --cases training/exams/finquant_adversarial_exam_v1_cases.jsonl \\", flush=True)
    print(f"    --model {args.model_tag} \\", flush=True)
    print(f"    --ollama-url {args.ollama_url}", flush=True)


if __name__ == "__main__":
    main()
