"""
Contract for the **single** host OpenAI secrets file + optional live OpenAI HTTP smoke.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from renaissance_v4.game_theory.unified_agent_v1 import external_openai_secrets_contract_v1 as c
from renaissance_v4.game_theory.unified_agent_v1 import external_openai_adapter_v1 as adapter


def test_default_path_is_one_home_file_v1() -> None:
    p = c.default_external_openai_env_file_v1()
    assert p.endswith(f"{c.DEFAULT_HOME_SUBPATH[0]}/{c.DEFAULT_HOME_SUBPATH[1]}")
    assert os.path.isabs(p)


def test_resolved_path_respects_blackbox_override_v1(monkeypatch, tmp_path) -> None:
    f = tmp_path / "only.env"
    f.write_text("export OPENAI_API_KEY='x'\n", encoding="utf-8")
    monkeypatch.setenv(c.EXTERNAL_API_OPENAI_ENV_FILE_ENV, str(f))
    assert c.resolved_external_openai_env_file_v1() == str(f)
    assert adapter.host_secrets_path_openai_v1() == str(f)
    assert adapter._path_host_openai_envfile_v1() == str(f)  # noqa: SLF001


def test_adapter_eager_load_matches_secrets_file_v1(monkeypatch, tmp_path) -> None:
    adapter.reset_external_openai_bootstrap_state_for_tests_v1()
    monkeypatch.delenv(c.EXTERNAL_API_OPENAI_KEY_ENV, raising=False)
    f = tmp_path / "a.env"
    f.write_text("export OPENAI_API_KEY='sk-eager-smoke-test-key'\n", encoding="utf-8")
    monkeypatch.setenv(c.EXTERNAL_API_OPENAI_ENV_FILE_ENV, str(f))
    assert adapter.eager_load_openai_api_key_v1() is True


def test_pattern_game_restart_sources_single_resolved_path_v1() -> None:
    """Bash: one O_ENV variable, no extra runtime/ duplicate for OpenAI."""
    root = Path(__file__).resolve().parents[3]  # blackbox
    sh = (root / "scripts" / "pattern_game_remote_restart.sh").read_text(encoding="utf-8")
    assert 'O_ENV="${BLACKBOX_OPENAI_ENV_FILE' in sh
    assert ".blackbox_secrets/openai.env" in sh
    # Must not re-introduce a second key store (runtime) for the same key.
    assert "runtime/secrets/openai.env" not in sh


def _live_enabled() -> bool:
    v = (os.environ.get("RUN_OPENAI_ADAPTER_LIVE") or "").strip().lower()
    return v in ("1", "true", "yes", "y")


@pytest.mark.skipif(
    not _live_enabled(),
    reason="Set RUN_OPENAI_ADAPTER_LIVE=1 and ensure OPENAI in env or the single host file; hits api.openai.com",
)
def test_openai_responses_smoke_ok_live_v1() -> None:
    """Real API call — same as ./scripts/openai_adapter_smoke_v1.sh; run on clawbot/CI with secret attached."""
    adapter.reset_external_openai_bootstrap_state_for_tests_v1()
    r = adapter.run_smoke_test_strict_json_v1()
    assert r.get("smoke_ok") is True, r
    assert r.get("error") is None, r
    assert r.get("model_resolved"), r
    t = str(r)
    assert "sk-" not in t and "sk_" not in t
