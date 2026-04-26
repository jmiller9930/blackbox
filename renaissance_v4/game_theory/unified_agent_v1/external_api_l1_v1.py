"""
GT_DIRECTIVE_026AI addendum — L1 / operator fields for external API status (no secrets).
"""

from __future__ import annotations

OPENAI_BILLING_SETTINGS_URL_V1 = "https://platform.openai.com/settings/organization/billing"

PRIMARY_BLOCKER_PRIORITY_V1: tuple[str, ...] = (
    "external_disabled_v1",
    "missing_api_key_v1",
    "insufficient_funds_v1",
    "quota_exceeded_v1",
    "rate_limited_v1",
    "provider_unavailable_v1",
    "budget_exceeded_v1",
    "token_limit_exceeded_v1",
    "provider_error_v1",
    "no_escalation_reason_v1",
    "schema_validation_failed_v1",
)


def operator_message_english_for_blocker_v1(blocker_code: str | None) -> str:
    c = str(blocker_code or "").strip()
    m = {
        "missing_api_key_v1": "External review skipped: OpenAI API key not configured.",
        "external_disabled_v1": "External review skipped: external API disabled in configuration.",
        "insufficient_funds_v1": "External review skipped: OpenAI credits exhausted.",
        "quota_exceeded_v1": "External review skipped: OpenAI quota exceeded.",
        "rate_limited_v1": "External review skipped: rate limited by provider.",
        "provider_unavailable_v1": "External review skipped: provider unavailable.",
        "provider_error_v1": "External review skipped: provider returned an error.",
        "budget_exceeded_v1": "External review skipped: run budget exceeded.",
        "token_limit_exceeded_v1": "External review skipped: run budget exceeded (token cap).",
        "no_escalation_reason_v1": "External review skipped: no escalation reason matched policy.",
        "schema_validation_failed_v1": "External review failed: response did not pass validation; local path continues.",
    }
    return m.get(c, f"External review not used: {c or 'unknown'}.")


def pick_primary_blocker_v1(blockers: list[str] | None) -> str | None:
    s = {str(x) for x in (blockers or [])}
    for p in PRIMARY_BLOCKER_PRIORITY_V1:
        if p in s:
            return p
    return next(iter(s)) if s else None


def external_api_action_url_v1_for_blocker(blocker_code: str | None) -> str | None:
    c = str(blocker_code or "").strip()
    if c in ("insufficient_funds_v1", "quota_exceeded_v1"):
        return OPENAI_BILLING_SETTINGS_URL_V1
    return None


def _status_english_v1(
    review_accepted: bool,
    primary_blocker: str | None,
) -> str:
    if review_accepted:
        return "external_review_completed_advisory"
    pb = str(primary_blocker or "").strip()
    if pb == "insufficient_funds_v1":
        return "External reasoning disabled — insufficient OpenAI funds"
    if pb == "quota_exceeded_v1":
        return "External reasoning disabled — OpenAI quota exceeded"
    if pb in ("budget_exceeded_v1", "token_limit_exceeded_v1"):
        return "External reasoning disabled — run budget exceeded"
    if pb == "rate_limited_v1":
        return "External reasoning disabled — rate limited"
    if pb == "provider_unavailable_v1":
        return "External reasoning disabled — provider unavailable"
    if pb:
        return "local_only_external_skipped"
    return "local_only"


def l1_fields_from_router_decision_v1(decision: dict | None) -> dict[str, object | None]:
    d = decision if isinstance(decision, dict) else {}
    block_s = str(d.get("external_api_block_reason_v1") or "").strip() or None
    url = d.get("external_api_action_url_v1")
    if not url and block_s:
        url = external_api_action_url_v1_for_blocker(block_s)
    return {
        "external_api_status_v1": d.get("external_api_status_v1"),
        "external_api_block_reason_v1": block_s,
        "external_api_action_url_v1": str(url) if url else None,
    }


def finalize_router_decision_addendum_v1(
    decision: dict[str, object],
    *,
    policy_permitted_http_call: bool,
    http_attempted: bool,
    review_accepted: bool,
    blockers: list[str],
    router_final_route: str,
    api_failure_detail_sanitized: str | None,
) -> None:
    """
    Mutates ``decision`` in place. Single attempt only (no retry loop).
    Degrades to ``local_only`` or ``external_failed_fallback_local``; never blocks the Student path.
    """
    pb = pick_primary_blocker_v1(list(blockers))
    decision["external_api_attempted_v1"] = bool(http_attempted)
    decision["external_api_allowed_v1"] = bool(policy_permitted_http_call)
    decision["external_api_failure_reason_v1"] = (
        (api_failure_detail_sanitized or None) if http_attempted and not review_accepted else None
    )
    decision["external_review_skipped_or_failed_v1"] = not review_accepted
    decision["external_api_block_reason_v1"] = pb
    decision["operator_message_english_v1"] = (
        "External review completed; advisory only (deterministic engine remains authority)."
        if review_accepted
        else (operator_message_english_for_blocker_v1(pb) if pb else "External review was not used; local reasoning continues.")
    )
    decision["external_api_status_v1"] = _status_english_v1(review_accepted, pb)
    decision["external_api_action_url_v1"] = external_api_action_url_v1_for_blocker(pb)
    if review_accepted:
        decision["final_route_v1"] = "external_review"
    elif http_attempted:
        decision["final_route_v1"] = "external_failed_fallback_local"
    else:
        decision["final_route_v1"] = str(router_final_route or "local_only")
