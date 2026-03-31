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
        "internal-users.html",
        "account-settings.html",
        "consumer.html",
        "guide.html",
        "forgot-password.html",
        "reset-password.html",
        "verify-email.html",
        "register.html",
        "404.html",
        "styles.css",
        "app.js",
        "Dockerfile",
        "docker-compose.yml",
        "nginx/default.conf",
        "content/UNIFIED_PLAN.md",
        "artifacts/PROOF_INDEX.txt",
        "WEB_ARCHITECTURE_CANONICAL.md",
        "WEB_UI_REQUIRED_CONTEXT.md",
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
    assert "forgot-password.html" in text
    assert "register.html" in text
    assert "account-settings.html" in text
    assert "login-role-picker" in text
    assert 'data-user="team"' in text and 'data-pass="team"' in text
    assert 'data-user="seans"' in text and 'data-pass="tradbuddy"' in text
    assert "login-continue-portal" in text
    assert "internal-users.html" in text
    assert "BlackboxPortal.login" in text or "blackbox_portal_session" in (
        WEB / "app.js"
    ).read_text(encoding="utf-8")


def test_app_js_three_dev_roles_and_staff_helpers() -> None:
    text = (WEB / "app.js").read_text(encoding="utf-8")
    assert "internal_member" in text
    assert "INTERNAL_STAFF_ROLES" in text
    assert "isInternalAdminRole" in text
    assert "isInternalStaffRole" in text
    assert "team: {" in text
    assert "seans: {" in text
    assert "tradbuddy" in text
    assert "dev-tradbuddy-seans" in text


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
    assert "INTERNAL_STAFF_ROLES" in text


def test_internal_portal_allows_staff_roles() -> None:
    text = (WEB / "internal.html").read_text(encoding="utf-8")
    assert "allowedRoles: window.BlackboxPortal.INTERNAL_STAFF_ROLES" in text
    assert "internal-admin-only" in text
    assert "portal-wait" in text
    assert "preparePortalBoot" in text
    assert "hidePortalBootOverlay" in text
    assert "isInternalAdminRole" in text
    assert "panel-runtime" in text
    assert "panel-devplan" in text
    assert "development_plan.md" in text
    assert "current_directive.md" in text
    assert "internal-users.html" in text
    assert "account-settings.html" in text
    assert "panel-training" in text


def test_system_guide_page_and_portal_nav() -> None:
    guide = (WEB / "guide.html").read_text(encoding="utf-8")
    assert "protectAuthenticated" in guide
    assert "guide-root" in guide
    internal = (WEB / "internal.html").read_text(encoding="utf-8")
    consumer = (WEB / "consumer.html").read_text(encoding="utf-8")
    assert 'href="./guide.html"' in internal
    assert "System guide" in internal
    assert 'href="./guide.html"' in consumer
    assert "System guide" in consumer
    arch = (WEB / "WEB_ARCHITECTURE_CANONICAL.md").read_text(encoding="utf-8")
    assert "/guide" in arch or "`/guide`" in arch
    req = (WEB / "WEB_UI_REQUIRED_CONTEXT.md").read_text(encoding="utf-8")
    assert "BLACK BOX Web UI" in req
    assert "system guide" in req.lower() or "guide" in req.lower()


def test_internal_header_links_external_preview_and_admin_users() -> None:
    """Top nav must expose consumer preview and admin user directory (not only sidebar)."""
    text = (WEB / "internal.html").read_text(encoding="utf-8")
    assert 'href="./consumer.html?preview=1"' in text
    assert "portal-nav__external" in text
    assert ">External</a" in text or ">External</a>" in text.replace("\n", "")
    assert 'href="./internal-users.html"' in text
    assert "portal-nav__admin-users" in text
    assert "Admin users" in text


def test_consumer_allows_internal_preview_gate_in_app_js() -> None:
    text = (WEB / "app.js").read_text(encoding="utf-8")
    assert "protectConsumerPortal" in text
    assert 'q.get("preview") === "1"' in text
    assert "isInternalStaffRole" in text


def test_consumer_protects_consumer_user() -> None:
    """Consumer layout is gated by protectConsumerPortal (consumer_user or internal preview)."""
    text = (WEB / "consumer.html").read_text(encoding="utf-8")
    assert "protectConsumerPortal" in text
    assert "portal-preview-banner" in text
    assert "internal_member" in text


def test_app_js_exports_portal_api() -> None:
    text = (WEB / "app.js").read_text(encoding="utf-8")
    assert "BlackboxPortal" in text
    assert "connectEventSource" in text
    assert "/api/v1" in text
    assert "protectConsumerPortal: protectConsumerPortal" in text
    assert "preparePortalBoot: preparePortalBoot" in text
    assert "hidePortalBootOverlay: hidePortalBootOverlay" in text


def test_app_js_account_self_service_api_paths() -> None:
    text = (WEB / "app.js").read_text(encoding="utf-8")
    assert "protectAuthenticated" in text
    assert "/auth/register" in text
    assert "/auth/password-reset/request" in text
    assert "/auth/email/verify" in text
    assert "/account/me" in text
    assert "/admin/users" in text


def test_account_settings_requires_auth() -> None:
    text = (WEB / "account-settings.html").read_text(encoding="utf-8")
    assert "protectAuthenticated" in text
    assert "account-password-alt" in text
    assert "forgot-password.html" in text


def test_internal_users_requires_internal_admin() -> None:
    text = (WEB / "internal-users.html").read_text(encoding="utf-8")
    assert 'requiredRole: "internal_admin"' in text


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
    assert "guide.html" in text
    assert "COPY . /usr/share/nginx/html" not in text
