"""
DV-067 — Explicit Kitchen → Jupiter assignment (audit file + optional SeanV3 HTTP).

Jupiter only accepts **approved policy slot ids** (see ``vscode-test/seanv3/jupiter_policy_runtime.mjs``).
Kitchen intake produces **TypeScript**; the runtime twin for proof is slot ``jup_kitchen_mechanical_v1``.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from renaissance_v4.policy_intake.storage import read_json, submission_dir

# Candidate policy_id from canonical intake (must match fixture / merged policy id).
MECHANICAL_CANDIDATE_POLICY_ID = "kitchen_mechanical_always_long_v1"
JUPITER_MECHANICAL_SLOT = "jup_kitchen_mechanical_v1"


def assignment_json_path(repo: Path) -> Path:
    return repo.resolve() / "renaissance_v4" / "state" / "kitchen_jupiter_assignment.json"


def read_assignment(repo: Path) -> dict[str, Any] | None:
    p = assignment_json_path(repo)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def assign_mechanical_candidate_to_jupiter(
    repo: Path,
    submission_id: str,
    *,
    http_base: str | None = None,
    operator_token: str | None = None,
) -> dict[str, Any]:
    """
    Validate passing intake for the mechanical candidate id, persist assignment, optionally POST to SeanV3.
    """
    repo = repo.resolve()
    rep_path = submission_dir(repo, submission_id) / "report" / "intake_report.json"
    rep = read_json(rep_path)
    if not isinstance(rep, dict) or not rep.get("pass"):
        return {"ok": False, "error": "submission_not_passing", "submission_id": submission_id}
    cid = str(rep.get("candidate_policy_id") or "").strip()
    if cid != MECHANICAL_CANDIDATE_POLICY_ID:
        return {
            "ok": False,
            "error": "candidate_not_mechanical_proof_policy",
            "detail": f"Only candidate_policy_id {MECHANICAL_CANDIDATE_POLICY_ID!r} can be assigned (runtime twin is {JUPITER_MECHANICAL_SLOT}).",
            "candidate_policy_id": cid,
        }
    et = str(rep.get("execution_target") or "jupiter").strip().lower()
    if et != "jupiter":
        return {"ok": False, "error": "execution_target_must_be_jupiter", "execution_target": et}

    body: dict[str, Any] = {
        "schema": "kitchen_jupiter_assignment_v1",
        "submission_id": submission_id,
        "candidate_policy_id": cid,
        "jupiter_policy_slot": JUPITER_MECHANICAL_SLOT,
        "note": "Runtime uses shipped SeanV3 module; Kitchen TS intake proves parity path.",
    }

    http_ok: bool | None = None
    http_detail: str | None = None
    base = (http_base or os.environ.get("KITCHEN_JUPITER_CONTROL_BASE") or "").strip()
    tok = (operator_token or os.environ.get("KITCHEN_JUPITER_OPERATOR_TOKEN") or "").strip()
    if base and tok:
        url = base.rstrip("/") + "/api/v1/jupiter/active-policy"
        payload = json.dumps({"policy": JUPITER_MECHANICAL_SLOT}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {tok}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                http_ok = resp.status == 200
                http_detail = raw[:2000]
        except urllib.error.HTTPError as e:
            http_ok = False
            http_detail = (e.read() or b"").decode("utf-8", errors="replace")[:2000]
        except OSError as e:
            http_ok = False
            http_detail = str(e)[:2000]
    else:
        http_ok = None
        http_detail = "KITCHEN_JUPITER_CONTROL_BASE and KITCHEN_JUPITER_OPERATOR_TOKEN not both set — assignment file only."

    body["jupiter_http_post_ok"] = http_ok
    body["jupiter_http_detail"] = http_detail

    p = assignment_json_path(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")

    return {"ok": True, **body}
