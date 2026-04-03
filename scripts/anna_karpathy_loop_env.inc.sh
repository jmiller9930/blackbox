#!/usr/bin/env bash
# shellcheck shell=bash
# Sourced by Karpathy loop start scripts. Loads repo-root env so OLLAMA_BASE_URL,
# BLACKBOX_JACK_EXECUTOR_CMD, etc. match other Anna entrypoints (see scripts/runtime/_ollama.py).
#
# Usage (after cd to repo root):
#   source scripts/anna_karpathy_loop_env.inc.sh
#   _load_karpathy_loop_env "$PWD"
#
_load_karpathy_loop_env() {
  local root="${1:-}"
  if [[ -z "$root" ]]; then
    root="${BLACKBOX_REPO:-${HOME}/blackbox}"
  fi
  local f
  for f in "$root/.env" "$root/.env.local"; do
    if [[ -f "$f" && -r "$f" ]]; then
      set -a
      # shellcheck disable=SC1090
      source "$f"
      set +a
    fi
  done
}
