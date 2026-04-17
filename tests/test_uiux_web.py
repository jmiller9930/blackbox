"""Static checks for UIUX.Web deliverables (Phases 1–4 shell)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WEB = REPO / "UIUX.Web"


def test_unified_plan_build_script_exists() -> None:
    assert (REPO / "scripts" / "build_unified_portal_plan.py").is_file()


def test_docker_compose_sets_context_engine_env() -> None:
    text = (WEB / "docker-compose.yml").read_text(encoding="utf-8")
    assert "BLACKBOX_CONTEXT_ROOT" in text
    assert "BLACKBOX_REPO_ROOT" in text


def test_api_server_exposes_context_engine_route() -> None:
    text = (WEB / "api_server.py").read_text(encoding="utf-8")
    assert "/api/v1/context-engine/status" in text


def test_api_server_exposes_runtime_policy_checkin_post() -> None:
    text = (WEB / "api_server.py").read_text(encoding="utf-8")
    assert "/api/v1/renaissance/runtime-policy-checkin" in text
    assert "REN_RUNTIME_CHECKIN_TOKEN" in text
    assert "apply_runtime_policy_checkin" in text


@pytest.mark.parametrize(
    "name",
    [
        "index.html",
        "login.html",
        "internal.html",
        "anna.html",
        "docs.html",
        "docs-anna-language.html",
        "docs-system-usage.html",
        "docs-ui-context.html",
        "docs-web-architecture.html",
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
        "assets/blackboxlogo.png",
        "assets/blackbox-boxmark.svg",
        "assets/generated/blackbox-3d-box-ticker-logo.svg",
    ],
)
def test_uiux_required_paths_exist(name: str) -> None:
    assert (WEB / name).is_file(), f"missing {WEB / name}"


def test_index_has_sign_in_and_logo_asset() -> None:
    text = (WEB / "index.html").read_text(encoding="utf-8")
    assert "login.html" in text
    assert "assets/blackboxlogo.png" in text
    assert "landing-minimal" in text
    assert "not wired" not in text.lower()


def test_login_wires_app_and_form() -> None:
    text = (WEB / "login.html").read_text(encoding="utf-8")
    assert "app.js" in text
    assert 'id="login-form"' in text
    assert "forgot-password.html" in text
    assert "register.html" in text
    assert "portalPathForRole" in text
    assert "login-continue-portal" in text
    assert "login-role-picker" not in text
    assert "auth-dev-details" in text
    assert "BlackboxPortal.login" in text or "blackbox_portal_session" in (
        WEB / "app.js"
    ).read_text(encoding="utf-8")


def test_dashboard_baseline_jupiter_rule_row_colors() -> None:
    text = (WEB / "dashboard.html").read_text(encoding="utf-8")
    assert "classifyBaselineJupiterNarrRow" in text
    assert "tc-narr-gate" in text
    assert "tc-narr-ok" in text
    assert "tc-narr-stop" in text


def test_dashboard_baseline_no_trade_amber_outline_only() -> None:
    text = (WEB / "dashboard.html").read_text(encoding="utf-8")
    assert ".tc-tr-baseline .tc-no-trade.tc-no-trade-amber" in text
    assert "tc-verdict-no-trade-amber" in text
    assert "noTradeVerdict" in text


def test_dashboard_trade_chain_tile_correlates_trade_id_and_mei() -> None:
    text = (WEB / "dashboard.html").read_text(encoding="utf-8")
    assert "tcTileCorrelateHtml" in text
    assert "tc-tile-correlate" in text
    assert "axisMid" in text


def test_dashboard_dv070_kitchen_assign_per_row_and_generalized_endpoint() -> None:
    """DV-070 — assign control visible per candidate row; no legacy Jupiter-only POST in UI."""
    text = (WEB / "dashboard.html").read_text(encoding="utf-8")
    assert "dash-rv4-cand-assign-btn" in text
    assert "Assign to runtime" in text
    assert "/api/v1/renaissance/kitchen-runtime-assignment" in text
    assert "kitchen-assign-jupiter" not in text
    assert "rv4-btn-kitchen-assign-runtime" not in text


def test_dashboard_dv074a_ledger_strip_present() -> None:
    text = (WEB / "dashboard.html").read_text(encoding="utf-8")
    assert "rv4-kitchen-ledger-strip" in text
    assert "ledger_tail" in text


def test_dashboard_kitchen_runtime_three_line_truth() -> None:
    """Kitchen assigned vs live runtime vs sync_state — not a single collapsed line."""
    text = (WEB / "dashboard.html").read_text(encoding="utf-8")
    assert "rv4-runtime-policy-summary" in text
    assert "rv4-kitchen-assigned-policy-value" in text
    assert "rv4-live-runtime-policy-value" in text
    assert "rv4-sync-state-value" in text


def test_dashboard_dv071_paste_reset_after_submit() -> None:
    """DV-071 — paste buffer cleared and paste mode closed after completed paste evaluation."""
    text = (WEB / "dashboard.html").read_text(encoding="utf-8")
    assert "rv4IntakeResetPasteAfterSubmit" in text
    assert "wasPasteSubmit" in text
    assert "rv4IntakeLastPasteRunCompletedOk" in text


def test_app_js_three_dev_roles_and_staff_helpers() -> None:
    text = (WEB / "app.js").read_text(encoding="utf-8")
    assert "internal_member" in text
    assert "INTERNAL_STAFF_ROLES" in text
    assert "isInternalAdminRole" in text
    assert "isInternalStaffRole" in text
    assert "team: {" in text
    assert "seans: {" in text
    assert "tradebuddy" in text
    assert "dev-tradebuddy-seans" in text
    assert "devPasswordMatches" in text
    assert "altPasswords" in text


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
    assert 'href="./anna.html"' not in text
    assert 'href="#panel-docs-hub"' in text
    assert 'id="docs-slack-hashtag-pill"' in text
    assert "slack_hashtag_language.md" in text
    assert 'id="panel-system-language"' in text
    assert 'id="system-language-modal"' in text
    assert "Slack hashtags" in text or "Slack hashtags &amp; commands" in text
    assert "System language workspace" in text
    assert 'id="panel-market"' not in text
    assert 'id="panel-pyth"' in text
    assert 'id="panel-agent-hub"' in text
    assert 'id="agent-modal"' in text
    assert 'id="pyth-health-pill"' in text
    assert 'id="pyth-db-pill"' in text
    assert 'id="pyth-view-btn"' in text
    assert "Runtime status" in text
    assert "/api/v1/system/status" in text
    assert "id=\"system-status-pill\"" in text
    assert "id=\"control-plane-pill\"" in text
    assert "id=\"data-plane-pill\"" in text
    assert "id=\"ui-api-pill\"" in text
    assert "id=\"agent-workers-pill\"" in text
    assert 'id="context-engine-pill"' in text
    assert "/api/v1/context-engine/status" in text
    assert "id=\"status-diagnostics-modal\"" in text


def test_anna_page_is_dedicated_workspace() -> None:
    text = (WEB / "anna.html").read_text(encoding="utf-8")
    assert "INTERNAL_STAFF_ROLES" in text
    assert '<h1 class="portal-title">Anna</h1>' in text
    assert "Operator portal" in text
    assert "sidebar-list__link--current" in text
    assert "preparePortalBoot" in text
    assert "panel-anna" in text
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


def test_docs_hub_and_reader_pages_exist() -> None:
    docs = (WEB / "docs.html").read_text(encoding="utf-8")
    assert '<h1 class="portal-title">Docs</h1>' in docs
    assert "How to interact with Anna using natural language" in docs
    assert "How to operate BLACK BOX today" in docs
    assert "Slack hashtag" in docs
    assert "slack_hashtag_language.md" in docs
    assert "Why the web UI exists" in docs
    assert "Web architecture and portal contract" in docs
    anna = (WEB / "docs-anna-language.html").read_text(encoding="utf-8")
    assert "How to interact with Anna using natural language" in anna
    assert "Natural-language topics" in anna
    usage = (WEB / "docs-system-usage.html").read_text(encoding="utf-8")
    assert "How to operate BLACK BOX today" in usage
    context = (WEB / "docs-ui-context.html").read_text(encoding="utf-8")
    assert "Why the web UI exists" in context
    arch = (WEB / "docs-web-architecture.html").read_text(encoding="utf-8")
    assert "Web architecture and portal contract" in arch


def test_internal_header_links_external_preview_and_admin_users() -> None:
    """Top nav exposes unified plan, consumer preview, and admin user directory (not only sidebar)."""
    text = (WEB / "internal.html").read_text(encoding="utf-8")
    assert 'href="./internal-plan.html"' in text
    assert "portal-nav__unified-plan" in text
    assert "Unified plan" in text
    assert 'href="./consumer.html?preview=1"' in text
    assert "portal-nav__external" in text
    assert ">External</a" in text or ">External</a>" in text.replace("\n", "")
    assert 'href="./internal-users.html"' in text
    assert "portal-nav__admin-users" in text
    assert "Admin users" in text


def test_internal_portal_devplan_collapsible_and_sidebar_active_styles() -> None:
    """Development plan is a closed-by-default details panel; sidebar active pill CSS exists."""
    internal = (WEB / "internal.html").read_text(encoding="utf-8")
    assert 'id="devplan-details"' in internal
    assert "devplan-details" in internal
    assert "sidebar-list__link--active" in internal
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    assert ".sidebar-list__link.sidebar-list__link--active" in css
    assert ".ops-overview" in css
    assert ".ops-chart" in css


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
    assert "/etc/nginx/ssl/active.crt" in text and "/etc/nginx/ssl/active.key" in text
    assert "TLSv1.2" in text and "TLSv1.3" in text
    assert "X-Content-Type-Options" in text
    assert "X-Frame-Options" in text
    assert "Referrer-Policy" in text
    assert "Permissions-Policy" in text


def test_dockerfile_uses_explicit_copy_not_leaky_nginx_root() -> None:
    """Ensure site root is not a blind COPY that publishes nginx/ under html."""
    text = (WEB / "Dockerfile").read_text(encoding="utf-8")
    assert "docker-entrypoint-web.sh" in text
    assert "COPY nginx/default.conf" in text
    assert "COPY index.html" in text
    assert "anna.html" in text
    assert "docs.html" in text
    assert "intelligence-method.html" in text
    assert "text-scale.js" in text
    assert "COPY . /usr/share/nginx/html" not in text


def test_intelligence_method_page_and_api_route() -> None:
    """Operator surface: method page + dev-server fallback route (nginx serves static copy)."""
    p = WEB / "intelligence-method.html"
    assert p.is_file()
    t = p.read_text(encoding="utf-8")
    assert "Learning stack" in t
    assert "MIT training flow" in t
    assert "decision_traces" in t
    assert "Learning storage" in t
    assert "dash-intel-eff" in t
    assert "Learning proof" in t
    assert "intelligence-method.html" in t
    api = (WEB / "api_server.py").read_text(encoding="utf-8")
    assert "/intelligence-method.html" in api
