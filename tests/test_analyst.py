"""Focused tests for the 3 highest-risk analyst paths:
1. LLM failure handling — _call_llm() returns {} on error/bad JSON
2. Deduplication — content_hash seen recently → article skipped
3. Tier assignment — _assign_tier() boundary conditions
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from analyst.filter import _assign_tier, is_noise, score_severity
from analyst.llm import call_llm


# ---------------------------------------------------------------------------
# 1. LLM failure handling
# ---------------------------------------------------------------------------

class TestCallLLM:
    def test_returns_empty_dict_on_groq_exception(self):
        """If Groq raises, call_llm returns {} and does not propagate the exception."""
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("network error")
        result = call_llm(client, "test prompt", "llama-3.3-70b-versatile")
        assert result == {}

    def test_returns_empty_dict_on_invalid_json(self):
        """If Groq returns non-JSON content, call_llm returns {}."""
        client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "not valid json {{{"
        client.chat.completions.create.return_value.choices = [mock_choice]
        result = call_llm(client, "test prompt", "llama-3.3-70b-versatile")
        assert result == {}

    def test_returns_parsed_dict_on_success(self):
        """Happy path: valid JSON response is returned as a dict."""
        client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"is_noise": false, "reason": "civil unrest"}'
        client.chat.completions.create.return_value.choices = [mock_choice]
        result = call_llm(client, "test prompt", "llama-3.3-70b-versatile")
        assert result == {"is_noise": False, "reason": "civil unrest"}

    def test_is_noise_defaults_false_on_llm_failure(self):
        """When LLM fails, is_noise() returns (False, 'No reason provided').

        NOTE: This is the known silent-failure mode tracked in TODOS.md (TODO-1).
        False means the article is treated as a real event and scored at severity 3.
        This test documents current behavior — update when TODO-1 is fixed.
        """
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("timeout")
        noise, reason = is_noise(client, "Title", "Summary", "US", ["news"])
        assert noise is False
        assert reason == "No reason provided"

    def test_score_severity_defaults_to_3_on_llm_failure(self):
        """When LLM fails, score_severity() returns severity=3 (ROUTINE tier).

        This is the known silent-failure mode — a timeout silently creates a
        ROUTINE event. Documented in TODOS.md TODO-1.
        """
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("timeout")
        severity, tier, rationale = score_severity(client, "Title", "Summary", "US", ["news"])
        assert severity == 3
        assert tier == "ROUTINE"
        assert rationale == "No rationale provided"


# ---------------------------------------------------------------------------
# 2. Deduplication — _load_recent_content_hashes and run_analysis skip logic
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_article_with_known_hash_is_skipped(self):
        """An article whose content_hash was already analyzed is skipped without LLM calls."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        # run_analysis fetches unanalyzed articles
        row = {
            "article_id": "abc123",
            "content_hash": "known_hash",
            "title": "Test",
            "summary": "Summary",
            "country": "US",
            "categories": '["news"]',
        }
        mock_cur.fetchall.side_effect = [
            [row],          # SELECT * FROM articles WHERE analyzed = 0
            [{"content_hash": "known_hash"}],  # _load_recent_content_hashes
        ]

        with patch("analyst.filter.get_conn", return_value=mock_conn), \
             patch("analyst.filter.Groq") as mock_groq_cls:
            mock_client = MagicMock()
            mock_groq_cls.return_value = mock_client

            from analyst.filter import run_analysis
            result = run_analysis(api_key="fake", dry_run=True)

        # Article was deduplicated — no LLM calls, no scored events
        mock_client.chat.completions.create.assert_not_called()
        assert result["analyzed"] == 0
        assert result["noise"] == 0

    def test_new_hash_is_processed(self):
        """An article with an unseen content_hash is sent to the LLM."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        row = {
            "article_id": "abc123",
            "content_hash": "new_hash",
            "title": "Riot in City",
            "summary": "Protesters clashed with police",
            "country": "FR",
            "categories": '["civil unrest"]',
        }
        mock_cur.fetchall.side_effect = [
            [row],   # unanalyzed articles
            [],      # no recent hashes
        ]

        noise_response = MagicMock()
        noise_response.message.content = '{"is_noise": false, "reason": "civil unrest event"}'
        severity_response = MagicMock()
        severity_response.message.content = '{"severity": 7, "rationale": "Active riot"}'

        with patch("analyst.filter.get_conn", return_value=mock_conn), \
             patch("analyst.filter.Groq") as mock_groq_cls:
            mock_client = MagicMock()
            mock_groq_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value.choices = [noise_response]
            # Second call returns severity
            mock_client.chat.completions.create.side_effect = [
                MagicMock(choices=[noise_response]),
                MagicMock(choices=[severity_response]),
            ]

            from analyst.filter import run_analysis
            result = run_analysis(api_key="fake", dry_run=True)

        assert mock_client.chat.completions.create.call_count == 2
        assert result["analyzed"] == 1
        assert result["priority"] == 1  # severity 7 → PRIORITY


# ---------------------------------------------------------------------------
# 3. Tier assignment boundary conditions
# ---------------------------------------------------------------------------

class TestAssignTier:
    @pytest.mark.parametrize("severity,expected_tier", [
        (1, "ROUTINE"),
        (4, "ROUTINE"),
        (5, "PRIORITY"),
        (7, "PRIORITY"),
        (8, "FLASH"),
        (10, "FLASH"),
    ])
    def test_tier_boundaries(self, severity: int, expected_tier: str):
        assert _assign_tier(severity) == expected_tier

    def test_severity_clamped_to_1_on_zero(self):
        """score_severity clamps int(result.get('severity', 3)) to range [1, 10]."""
        client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"severity": 0, "rationale": "edge case"}'
        client.chat.completions.create.return_value.choices = [mock_choice]
        severity, tier, _ = score_severity(client, "T", "S", "US", [])
        assert severity == 1
        assert tier == "ROUTINE"

    def test_severity_clamped_to_10_on_overflow(self):
        """score_severity clamps values above 10 to 10."""
        client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '{"severity": 99, "rationale": "overflow"}'
        client.chat.completions.create.return_value.choices = [mock_choice]
        severity, tier, _ = score_severity(client, "T", "S", "US", [])
        assert severity == 10
        assert tier == "FLASH"
