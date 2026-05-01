"""Tests for llm_adapter.py — uses mocked HTTP, no real Ollama call."""

import json
import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from llm_adapter import (
    extract_decision_json,
    validate_parsed_decision,
    normalize_llm_decision,
    call_ollama,
    LLMCallResult,
)


def test_extract_decision_json_from_fence():
    text = 'some reasoning\n```json\n{"action": "NO_TRADE", "thesis": "weak"}\n```'
    result = extract_decision_json(text)
    assert result is not None
    assert result["action"] == "NO_TRADE"


def test_extract_decision_json_raw():
    text = 'I think {"action": "ENTER_LONG", "thesis": "trend up"} makes sense.'
    result = extract_decision_json(text)
    assert result is not None
    assert result["action"] == "ENTER_LONG"


def test_extract_decision_json_returns_none_when_missing():
    text = "No JSON here at all."
    result = extract_decision_json(text)
    assert result is None


def test_validate_parsed_decision_normalizes_uppercase():
    parsed = {"action": "enter_long", "confidence": "medium"}
    err = validate_parsed_decision(parsed)
    assert err == ""
    assert parsed["action"] == "ENTER_LONG"


def test_validate_parsed_decision_rejects_invalid_action():
    parsed = {"action": "BUY", "confidence": "low"}
    err = validate_parsed_decision(parsed)
    assert "invalid action" in err


def test_validate_parsed_decision_defaults_bad_confidence():
    parsed = {"action": "HOLD", "confidence": "very_high"}
    err = validate_parsed_decision(parsed)
    assert err == ""
    assert parsed["confidence"] == "low"  # defaulted


def test_normalize_llm_decision_full():
    parsed = {
        "action": "NO_TRADE",
        "thesis": "RSI neutral, no edge.",
        "invalidation": "RSI breaks above 65 with volume.",
        "confidence": "low",
        "supporting": ["price_flat"],
        "conflicting": ["rsi_borderline"],
        "risk_notes": "Stand down.",
    }
    fields = normalize_llm_decision(
        parsed,
        case_id="test_001",
        step_index=0,
        symbol="SOL-PERP",
        raw_output='{"action":"NO_TRADE"}',
        latency_ms=150,
    )
    assert fields["action"] == "NO_TRADE"
    assert fields["confidence_band_v1"] == "low"
    assert "RSI neutral" in fields["thesis_v1"]
    assert isinstance(fields["supporting_indicators_v1"], list)
    assert fields["llm_latency_ms_v1"] == 150


def test_normalize_llm_decision_fills_missing_thesis():
    parsed = {"action": "HOLD"}
    fields = normalize_llm_decision(
        parsed,
        case_id="test_002",
        step_index=1,
        symbol="SOL-PERP",
        raw_output="",
        latency_ms=0,
    )
    assert "HOLD" in fields["thesis_v1"]


def _mock_ollama_response(action: str, thesis: str = "test thesis") -> mock.MagicMock:
    """Return a mock urllib response with a valid Ollama JSON response."""
    response_body = json.dumps({
        "response": json.dumps({
            "action": action,
            "thesis": thesis,
            "invalidation": "test invalidation",
            "confidence": "medium",
        }),
        "done": True,
    }).encode("utf-8")

    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = response_body
    mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = mock.MagicMock(return_value=False)
    return mock_resp


def test_call_ollama_success(monkeypatch):
    mock_resp = _mock_ollama_response("NO_TRADE")
    with mock.patch("urllib.request.urlopen", return_value=mock_resp):
        result = call_ollama(
            base_url="http://fake:11434",
            model="qwen2.5:7b",
            prompt="test prompt",
            timeout_seconds=5,
        )
    assert result.success is True
    assert result.parsed["action"] == "NO_TRADE"


def test_call_ollama_network_failure(monkeypatch):
    import urllib.error
    with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        result = call_ollama(
            base_url="http://fake:11434",
            model="qwen2.5:7b",
            prompt="test",
            timeout_seconds=1,
        )
    assert result.success is False
    assert "URLError" in result.error


def test_call_ollama_bad_json_in_response(monkeypatch):
    mock_resp = mock.MagicMock()
    mock_resp.read.return_value = b'{"response": "no json here", "done": true}'
    mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = mock.MagicMock(return_value=False)
    with mock.patch("urllib.request.urlopen", return_value=mock_resp):
        result = call_ollama(
            base_url="http://fake:11434",
            model="qwen2.5:7b",
            prompt="test",
            timeout_seconds=1,
        )
    assert result.success is False
    assert "No valid JSON" in result.error
