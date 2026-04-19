"""
Pluggable **pattern-game agent** for host applications (Foreman, services, CLIs).

Import this module once; use :class:`PatternGameAgent` to list JSON presets, load scenarios,
run the Referee batch in parallel, and optionally run the **player agent** layer (markdown report +
optional Anna narrative + repo context). You do not rebuild wiring — swap **presets** (scenario JSON)
and **manifest paths** inside them to explore different strategy manifests / policy-adjacent candidates.

**Not** LLM fine-tuning: “skills” are **repo docs + logs + presets** you attach; see ``agent_context_bundle``.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from renaissance_v4.game_theory.memory_paths import default_experience_log_jsonl, default_run_memory_jsonl
from renaissance_v4.game_theory.parallel_runner import run_scenarios_parallel
from renaissance_v4.game_theory.player_agent import run_player_batch
from renaissance_v4.game_theory.scenario_contract import (
    resolve_scenario_manifest_path,
    validate_scenarios,
)

_GAME_THEORY = Path(__file__).resolve().parent
_DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]


def _parse_scenarios_payload(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict) and "scenarios" in raw:
        raw = raw["scenarios"]
    if not isinstance(raw, list):
        raise ValueError("Expected a JSON array of scenario objects or {scenarios: [...]}")
    out = [x for x in raw if isinstance(x, dict)]
    if not out:
        raise ValueError("No scenario objects in payload")
    return out


@contextmanager
def _optional_env(updates: dict[str, str | None]) -> Any:
    saved: dict[str, str | None] = {}
    try:
        for k, v in updates.items():
            saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


@dataclass
class PatternGameAgent:
    """
    Application-facing facade: presets under ``presets_dir``, runs under ``repo_root``.
    """

    repo_root: Path = field(default_factory=lambda: _DEFAULT_REPO_ROOT)
    presets_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.presets_dir is None:
            self.presets_dir = _GAME_THEORY / "examples"
        self.repo_root = Path(self.repo_root).resolve()
        self.presets_dir = Path(self.presets_dir).resolve()

    def plugin_info(self) -> dict[str, Any]:
        """Stable metadata for host apps (about screen, feature flags)."""
        return {
            "module": "renaissance_v4.game_theory.pattern_game_agent",
            "kind": "pattern_game_player_agent",
            "repo_root": str(self.repo_root),
            "presets_dir": str(self.presets_dir),
            "referee": "parallel_runner.run_scenarios_parallel",
            "player_layer": "player_agent.run_player_batch",
        }

    def list_presets(self) -> list[dict[str, str]]:
        """Each preset is a ``*.json`` file in ``presets_dir`` (named scenarios batch)."""
        rows: list[dict[str, str]] = []
        if not self.presets_dir.is_dir():
            return rows
        for p in sorted(self.presets_dir.glob("*.json")):
            label = p.name.replace("_", " ").replace(".example.json", "").replace(".json", "")
            rows.append({"id": p.name, "filename": p.name, "label": label})
        return rows

    def load_preset(self, preset_id: str) -> list[dict[str, Any]]:
        """Load scenarios from a preset filename (e.g. ``tier1_twelve_month.example.json``)."""
        name = Path(preset_id).name
        if name != preset_id or not name.endswith(".json"):
            raise ValueError("preset_id must be a bare *.json filename")
        path = (self.presets_dir / name).resolve()
        if not str(path).startswith(str(self.presets_dir)):
            raise ValueError("Invalid preset path")
        if not path.is_file():
            raise FileNotFoundError(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        return _parse_scenarios_payload(raw)

    def load_scenarios_json(self, text: str) -> list[dict[str, Any]]:
        """Parse a JSON string (array or ``{scenarios: [...]}``)."""
        raw = json.loads(text)
        return _parse_scenarios_payload(raw)

    def normalize_manifest_paths(self, scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Resolve ``manifest_path`` to absolute paths from ``repo_root`` (mutates copies)."""
        out: list[dict[str, Any]] = []
        for s in scenarios:
            n = dict(s)
            mp = n.get("manifest_path")
            if mp:
                n["manifest_path"] = str(resolve_scenario_manifest_path(mp, repo_root=self.repo_root))
            out.append(n)
        return out

    def validate(self, scenarios: list[dict[str, Any]]) -> tuple[bool, list[str]]:
        return validate_scenarios(scenarios, check_manifest_exists=False, repo_root=self.repo_root)

    def run_referee_only(
        self,
        scenarios: list[dict[str, Any]],
        *,
        max_workers: int | None = None,
        experience_log_path: Path | str | bool | None = None,
        run_memory_log_path: Path | str | bool | None = None,
        write_session_logs: bool = True,
        session_logs_base: Path | str | None = None,
    ) -> list[dict[str, Any]]:
        """Parallel Referee batch — no player-agent markdown, no Anna."""
        scenarios = self.normalize_manifest_paths(scenarios)
        ok, msgs = self.validate(scenarios)
        if not ok:
            raise ValueError(msgs[0] if msgs else "Invalid scenarios")
        log_path: Path | None = None
        if experience_log_path is True or experience_log_path == "1" or experience_log_path == "default":
            log_path = default_experience_log_jsonl()
        elif experience_log_path:
            log_path = Path(str(experience_log_path))
        rmem_path: Path | None = None
        if run_memory_log_path is True or run_memory_log_path == "1" or run_memory_log_path == "default":
            rmem_path = default_run_memory_jsonl()
        elif run_memory_log_path:
            rmem_path = Path(str(run_memory_log_path))
        sbase = session_logs_base
        if sbase is None and os.environ.get("PATTERN_GAME_SESSION_LOGS_ROOT"):
            sbase = os.environ.get("PATTERN_GAME_SESSION_LOGS_ROOT")
        return run_scenarios_parallel(
            scenarios,
            max_workers=max_workers,
            experience_log_path=log_path,
            run_memory_log_path=rmem_path,
            write_session_logs=write_session_logs,
            session_logs_base=sbase,
        )

    def run(
        self,
        scenarios: list[dict[str, Any]],
        *,
        max_workers: int | None = None,
        experience_log_path: Path | str | bool | None = None,
        run_memory_log_path: Path | str | bool | None = None,
        write_session_logs: bool = True,
        session_logs_base: Path | str | None = None,
        fill_missing_explanations: bool = True,
        with_anna: bool | None = None,
        anna_context_profile: str | None = None,
    ) -> dict[str, Any]:
        """
        Full player-agent run: Referee batch + markdown + optional Anna.

        ``anna_context_profile`` sets ``ANNA_CONTEXT_PROFILE`` only for the duration of this call
        (e.g. ``policy,pattern_game``). If ``None``, ``player_agent`` uses its default (**full** prefix
        ``all`` when the env profile is unset — see ``ANNA_PATTERN_GAME_CONTEXT_MINIMAL``). Does not fine-tune any model.
        """
        scenarios = self.normalize_manifest_paths(scenarios)
        ok, msgs = self.validate(scenarios)
        if not ok:
            raise ValueError(msgs[0] if msgs else "Invalid scenarios")
        log_path: Path | None = None
        if experience_log_path is True or experience_log_path == "1" or experience_log_path == "default":
            log_path = default_experience_log_jsonl()
        elif experience_log_path:
            log_path = Path(str(experience_log_path))
        rmem_arg: Path | str | bool | None = run_memory_log_path
        if rmem_arg is None and os.environ.get("RUN_MEMORY_LOG"):
            rmem_arg = os.environ.get("RUN_MEMORY_LOG")
        rmem_out: Path | str | None = None
        if rmem_arg is True or rmem_arg == "1" or rmem_arg == "default":
            rmem_out = default_run_memory_jsonl()
        elif rmem_arg:
            rmem_out = Path(str(rmem_arg))

        # REPO_ROOT: so ``agent_context_bundle`` resolves docs when the host process cwd is not the repo.
        env_updates: dict[str, str | None] = {"REPO_ROOT": str(self.repo_root)}
        if anna_context_profile is not None:
            env_updates["ANNA_CONTEXT_PROFILE"] = anna_context_profile if anna_context_profile else None
        sbase = session_logs_base
        if sbase is None and os.environ.get("PATTERN_GAME_SESSION_LOGS_ROOT"):
            sbase = os.environ.get("PATTERN_GAME_SESSION_LOGS_ROOT")
        with _optional_env(env_updates):
            return run_player_batch(
                scenarios,
                max_workers=max_workers,
                experience_log_path=log_path,
                run_memory_log_path=rmem_out,
                write_session_logs=write_session_logs,
                session_logs_base=sbase,
                fill_missing_explanations=fill_missing_explanations,
                with_anna=with_anna,
            )

    def run_preset(
        self,
        preset_id: str,
        *,
        max_workers: int | None = None,
        experience_log_path: Path | str | bool | None = None,
        run_memory_log_path: Path | str | bool | None = None,
        write_session_logs: bool = True,
        session_logs_base: Path | str | None = None,
        fill_missing_explanations: bool = True,
        with_anna: bool | None = None,
        anna_context_profile: str | None = None,
    ) -> dict[str, Any]:
        """Load a named preset file and :meth:`run`."""
        scenarios = self.load_preset(preset_id)
        return self.run(
            scenarios,
            max_workers=max_workers,
            experience_log_path=experience_log_path,
            run_memory_log_path=run_memory_log_path,
            write_session_logs=write_session_logs,
            session_logs_base=session_logs_base,
            fill_missing_explanations=fill_missing_explanations,
            with_anna=with_anna,
            anna_context_profile=anna_context_profile,
        )
