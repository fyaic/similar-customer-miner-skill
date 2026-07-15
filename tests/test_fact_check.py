"""Tests for fact_check module."""
from unittest.mock import Mock, patch

from src.fact_check import fact_check_companies
from src.models import SimilarCompany


def test_fact_check():
    companies = [
        SimilarCompany(company_name="Valid Co", country="US", email="a@example.com", hs_codes=["1234"]),
        SimilarCompany(company_name="Bad", country="US", revenue="100", china_purchase="200", hs_codes=[]),
    ]
    checked = fact_check_companies(companies)
    assert checked[0].fact_check_status in {"passed", "pending"}
    assert checked[1].fact_check_status == "failed"


@patch("src.fact_check.GoogleFactCheckTool")
def test_google_reviews_are_supplemental_external_claim_reviews(mock_tool_cls):
    mock_tool = Mock()
    mock_tool.search_claims.return_value = [
        {
            "textual_rating": "Unverified",
            "publisher": "Claim Review Org",
            "review_url": "https://example.com/review",
        }
    ]
    mock_tool_cls.return_value = mock_tool
    company = SimilarCompany(
        company_name="Valid Co",
        country="US",
        email="a@example.com",
        hs_codes=["1234"],
        revenue="$10M",
        overall_confidence=0.95,
    )

    checked = fact_check_companies(
        [company],
        {"google": {"fact_check_enabled": True, "fact_check_api_key": "test-key", "min_confidence": 0.1}},
    )

    assert checked[0].fact_check_status == "passed"
    assert "External claim review search" in (checked[0].notes or "")
    assert "not revenue/procurement proof" in (checked[0].notes or "")
    assert checked[0].all_citations["external_claim_review_Claim Review Org"] == "https://example.com/review"
