#!/usr/bin/env bash
# Install canonical NDE host layout from the repo to /data/NDE (or DEST).
# Safe: copies static tree only; does not touch /data/finquant-1 or running jobs.
set -euo pipefail

DEST="${1:-/data/NDE}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAYOUT="${REPO_ROOT}/nde_factory/layout"

if [[ ! -d "${LAYOUT}" ]]; then
  echo "error: missing layout at ${LAYOUT}" >&2
  exit 1
fi

echo "Installing NDE layout from ${LAYOUT} -> ${DEST}"
mkdir -p "${DEST}"
# Portable copy (no rsync dependency on minimal hosts).
cp -a "${LAYOUT}/." "${DEST}/"

# Canonical runtime dirs (layout already provides secops/ + finquant/; tools/ always comes from repo).
mkdir -p "${DEST}/tools" "${DEST}/secops" "${DEST}/finquant"

TOOLS="${REPO_ROOT}/nde/tools"
if [[ ! -d "${TOOLS}" ]]; then
  echo "warning: repo nde/tools missing at ${TOOLS}; ${DEST}/tools left empty except mkdir" >&2
else
  # Python entrypoints and SecOps proof libs (nde_graph_runner imports secops_proof_lib from cwd).
  for _py in nde_source_processor.py nde_graph_runner.py nde_validation_lib.py secops_proof_lib.py secops_nde_proof_runner.py check_langgraph_enforcement.py validate_domain_contract.py validate_training_dataset.py; do
    [[ -f "${TOOLS}/${_py}" ]] && cp -f "${TOOLS}/${_py}" "${DEST}/tools/"
  done
  [[ -f "${TOOLS}/requirements.txt" ]] && cp -f "${TOOLS}/requirements.txt" "${DEST}/tools/"
  for _helper in setup_env.sh setup_train_env.sh run_processor.sh run_graph.sh run_finquant_v02_eval.sh; do
    [[ -f "${TOOLS}/${_helper}" ]] && cp -f "${TOOLS}/${_helper}" "${DEST}/tools/" && chmod +x "${DEST}/tools/${_helper}"
  done
  [[ -f "${TOOLS}/langgraph_enforcement_allowlist.json" ]] && cp -f "${TOOLS}/langgraph_enforcement_allowlist.json" "${DEST}/tools/"
  # Operator docs (single source of truth with installer, not ad-hoc cp on host).
  for _doc in HOWTO_SECOPS_NDE.md README.md; do
    [[ -f "${TOOLS}/${_doc}" ]] && cp -f "${TOOLS}/${_doc}" "${DEST}/tools/"
  done
  echo "Installed tools under ${DEST}/tools/ (Python, shell helpers, HOWTO_SECOPS_NDE.md)"
fi

# FinQuant progressive baseline: copy certified v0.2 combined corpus into NDE staging when legacy tree exists.
# nde_validation_lib.resolve_staging_jsonl falls back to this file when newer staging is absent.
FINQUANT_STAGING="${DEST}/finquant/datasets/staging"
LEGACY_FINQUANT_BASELINE="/data/finquant-1/datasets/staging/v0.2c_combined.jsonl"
mkdir -p "${FINQUANT_STAGING}"
if [[ -f "${LEGACY_FINQUANT_BASELINE}" ]]; then
  cp -f "${LEGACY_FINQUANT_BASELINE}" "${FINQUANT_STAGING}/v0.2c_combined.jsonl"
  echo "FinQuant: synced progressive baseline ${LEGACY_FINQUANT_BASELINE} -> ${FINQUANT_STAGING}/v0.2c_combined.jsonl"
else
  echo "warning: FinQuant baseline missing at ${LEGACY_FINQUANT_BASELINE}; NDE dataset validation may fail until copied" >&2
fi

echo "Done. Top-level README: ${DEST}/README.md"
echo "Verify: ls -ld ${DEST}/tools ${DEST}/secops ${DEST}/finquant"
