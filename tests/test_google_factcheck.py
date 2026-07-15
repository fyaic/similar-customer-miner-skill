"""Tests for Google Fact Check tool."""
from unittest.mock import MagicMock, patch

import pytest

from tools.google_factcheck_tool import BASE_URL, GoogleFactCheckTool


@pytest.fixture
def tool(tmp_path):
    config = {"google": {"fact_check_api_key": "test-key", "timeout": 5}}
    return GoogleFactCheckTool(config, cache_dir=str(tmp_path))


def test_tool_skips_without_key(tmp_path):
    config = {"google": {"fact_check_api_key": ""}}
    t = GoogleFactCheckTool(config, cache_dir=str(tmp_path))
    assert t.search_claims("anything") == []


def test_tool_skips_empty_query(tool):
    assert tool.search_claims("") == []
    assert tool.search_claims("   ") == []


@patch("tools.google_factcheck_tool.requests.get")
def test_tool_parses_claims(mock_get, tool):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "claims": [
                {
                    "text": "Company X made $1B",
                    "claimant": "CEO",
                    "claimDate": "2023-01-01",
                    "claimReview": [
                        {
                            "publisher": {"name": "FactCheck.org", "site": "factcheck.org"},
                            "url": "https://factcheck.org/x",
                            "title": "Did Company X make $1B?",
                            "reviewDate": "2023-02-01",
                            "textualRating": "Mostly True",
                            "languageCode": "en",
                        }
                    ],
                }
            ]
        },
    )

    results = tool.search_claims("Company X revenue")
    assert len(results) == 1
    assert results[0]["claim_text"] == "Company X made $1B"
    assert results[0]["textual_rating"] == "Mostly True"
    assert results[0]["publisher"] == "FactCheck.org"

    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert call_args[1]["params"]["key"] == "test-key"
    assert call_args[1]["params"]["query"] == "Company X revenue"


@patch("tools.google_factcheck_tool.requests.get")
def test_tool_returns_empty_on_error(mock_get, tool):
    mock_get.side_effect = Exception("network error")
    assert tool.search_claims("test") == []
