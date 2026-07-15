"""Tests for company enrichment."""
from unittest.mock import patch

from src.enrichment import enrich_companies
from src.models import RawCompany


@patch(
    "tools.email_tool.EmailTool.hunter_domain_contacts",
    return_value=[{"email": "sales@example.com", "source": "hunter"}],
)
def test_enrichment_uses_hunter_when_real_website_has_no_email(mock_hunter):
    raw = RawCompany(
        company_name="Example Co",
        country="US",
        website="https://example.com",
        datasource="importyeti_apify",
    )
    verified = [
        {
            "raw": raw,
            "website": {
                "url": "https://example.com",
                "reachable": True,
                "emails": [],
                "phones": [],
                "social": {},
            },
        }
    ]

    companies = enrich_companies(verified, {"hunter": {"api_key": "test-key"}})

    assert companies[0].email == "sales@example.com"
    assert companies[0].email_citation == "Hunter.io domain search"
    assert companies[0].contact_name is None
    assert companies[0].contact_name_confidence == 0.0
    assert "Hunter.io" in (companies[0].notes or "")
    assert "not a verified person" in (companies[0].notes or "")
    mock_hunter.assert_called_once_with("example.com")


@patch(
    "tools.email_tool.EmailTool.hunter_domain_contacts",
    return_value=[
        {
            "email": "jane.doe@example.com",
            "first_name": "Jane",
            "last_name": "Doe",
            "position": "Procurement Manager",
            "source": "hunter",
        }
    ],
)
def test_enrichment_uses_structured_hunter_person_fields(mock_hunter):
    raw = RawCompany(
        company_name="Example Co",
        country="US",
        website="https://example.com",
        datasource="importyeti_apify",
    )
    verified = [
        {
            "raw": raw,
            "website": {
                "url": "https://example.com",
                "reachable": True,
                "emails": [],
                "phones": [],
                "social": {},
            },
        }
    ]

    companies = enrich_companies(verified, {"hunter": {"api_key": "test-key"}})

    assert companies[0].email == "jane.doe@example.com"
    assert companies[0].email_citation == "Hunter.io domain search"
    assert companies[0].contact_name == "Jane Doe"
    assert companies[0].contact_title == "Procurement Manager"
    assert companies[0].contact_name_confidence > 0
    assert "structured Hunter.io fields" in (companies[0].notes or "")
    mock_hunter.assert_called_once_with("example.com")


@patch(
    "tools.email_tool.EmailTool.hunter_domain_contacts",
    return_value=[
        {
            "email": "jane.doe@example.com",
            "first_name": "Jane",
            "last_name": "Doe",
            "position": "Procurement Manager",
            "source": "hunter",
        }
    ],
)
def test_enrichment_queries_hunter_when_website_email_is_generic(mock_hunter):
    raw = RawCompany(
        company_name="Example Co",
        country="US",
        website="https://example.com",
        datasource="importyeti_apify",
    )
    verified = [
        {
            "raw": raw,
            "website": {
                "url": "https://example.com",
                "reachable": True,
                "emails": ["sales@example.com"],
                "phones": [],
                "social": {},
            },
        }
    ]

    companies = enrich_companies(verified, {"hunter": {"api_key": "test-key"}})

    assert companies[0].email == "jane.doe@example.com"
    assert companies[0].email_citation == "Hunter.io domain search"
    assert companies[0].contact_name == "Jane Doe"
    assert companies[0].contact_title == "Procurement Manager"
    assert "Department/generic email" not in (companies[0].notes or "")
    mock_hunter.assert_called_once_with("example.com")
