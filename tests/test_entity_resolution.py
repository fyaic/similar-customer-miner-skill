"""Tests for entity resolution module."""
from src.models import SimilarCompany
from src.entity_resolution import deduplicate_companies


def test_deduplicate_companies():
    companies = [
        SimilarCompany(company_name="ABC Inc.", country="US", email="a@abc.com", email_confidence=0.7),
        SimilarCompany(company_name="ABC Incorporated", country="US", email="b@abc.com", email_confidence=0.8),
        SimilarCompany(company_name="XYZ LLC", country="US"),
    ]
    unique = deduplicate_companies(companies)
    assert len(unique) == 2
    names = {c.company_name for c in unique}
    assert "ABC Inc." in names or "ABC Incorporated" in names
    assert "XYZ LLC" in names
