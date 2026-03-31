"""Static checks for UIUX.Web deliverables (Phases 1–4 shell)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "UIUX.Web"


def test_unified_plan_build_script_exists() -> None:
    assert (REPO / "scripts" / "build_unified_portal_plan.py").is_file()


@pytest.mark.parametrize(
    "name",
    [
        "index.html",
        "login.html",
        "internal.html",
        "internal-plan.html",
        "consumer.html",
        "404.html",
        "styles.css",
        "app.js",
        "Dockerfile",
        "docker-compose.yml",
        "nginx/default.conf",
        "content/UNIFIED_PLAN.md",
        "artifacts/PROOF_INDEX.txt",
        "WEB_ARCHITECTURE_CANONICAL.md",
        "assets/blackbox-boxmark.svg",
        "assets/generated/blackbox-3d-box-ticker-logo.svg",
    ],
)
def test_uiux_required_paths_exist(name: str) -> None:
    assert (WEB / name).is_file(), f"missing {WEB / name}"


def test_index_has_sign_in_and_ticker_logo() -> None:
    text = (WEB / "index.html").read_text(encoding="utf-8")
    assert "login.html" in text
    assert "assets/generated/blackbox-3d-box-ticker-logo.svg" in text
    assert "landing-minimal" in text
    assert "not wired" not in text.lower()


def test_login_wires_app_and_form() -> None:
    text = (WEB / "login.html").read_text(encoding="utf-8")
    assert "app.js" in text
    assert 'id="login-form"' in text
    assert "BlackboxPortal.login" in text or "blackbox_portal_session" in (
        WEB / "app.js"
    ).read_text(encoding="utf-8")


def test_unified_plan_generated_file() -> None:
    p = WEB / "content" / "UNIFIED_PLAN.md"
    text = p.read_text(encoding="utf-8")
    assert "BLACK BOX unified plan" in text
    assert "Part 1 — Development plan" in text
    assert "Part 2 — Web UI architecture" in text
    assert len(text) > 50_000


def test_internal_plan_page_loads_unified_md() -> None:
    text = (WEB / "internal-plan.html").read_text(encoding="utf-8")
    assert "UNIFIED_PLAN.md" in text
    assert "protectPage" in text
    assert "internal_admin" in text


def test_internal_protects_internal_admin() -> None:
    text = (WEB / "internal.html").read_text(encoding="utf-8")
    assert 'requiredRole: "internal_admin"' in text
    assert "panel-runtime" in text
    assert "panel-devplan" in text
    assert "development_plan.md" in text
    assert "current_directive.md" in text
    assert "panel-training" in text


def test_consumer_protects_consumer_user() -> None:
    text = (WEB / "consumer.html").read_text(encoding="utf-8")
    assert 'requiredRole: "consumer_user"' in text


def test_app_js_exports_portal_api() -> None:
    text = (WEB / "app.js").read_text(encoding="utf-8")
    assert "BlackboxPortal" in text
    assert "connectEventSource" in text
    assert "/api/v1" in text


def test_nginx_baseline_hardening() -> None:
    text = (WEB / "nginx/default.conf").read_text(encoding="utf-8")
    assert "server_tokens off" in text
    assert "TLSv1.2" in text and "TLSv1.3" in text
    assert "X-Content-Type-Options" in text
    assert "X-Frame-Options" in text
    assert "Referrer-Policy" in text
    assert "Permissions-Policy" in text


def test_dockerfile_uses_explicit_copy_not_leaky_nginx_root() -> None:
    """Ensure site root is not a blind COPY that publishes nginx/ under html."""
    text = (WEB / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY nginx/default.conf" in text
    assert "COPY index.html" in text
    assert "COPY . /usr/share/nginx/html" not in text
