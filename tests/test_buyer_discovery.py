"""Tests for the dual-channel buyer discovery module."""
from unittest.mock import patch

from src.models import CustomerProfile
from src.buyer_discovery import discover_buyers


def test_discover_buyers_demo_channel_offline():
    """Non-live mode uses the offline demo importer pool (no network)."""
    config = {
        "runtime": {"mode": "demo"},
        "apify": {"api_token": ""},
        "pipeline": {"max_results_per_customer": 5, "min_shipments": 5},
        "cache": {"enabled": False},
    }
    profiles = [
        CustomerProfile(customer_id="1", customer_name="Test", search_queries=["shower system"], hs_codes=["8481"])
    ]
    companies = discover_buyers(profiles, config)
    assert len(companies) > 0
    assert all(c.company_name for c in companies)
    assert all(c.country == "US" for c in companies)


@patch("src.buyer_discovery.web_discovery.search_importers")
@patch("src.buyer_discovery.ImportYetiTool.keyword_search")
def test_discover_buyers_live_dual_channel_and_seed_exclusion(mock_keyword, mock_web):
    """Live mode merges Apify keyword + web channels, excludes seeds, and never
    queries by the customer's own name (that was the old broken behavior)."""
    # Apify keyword channel returns one importer; web channel returns another + the seed.
    mock_keyword.return_value = [
        {"company_name": "Acme Importers", "country": "US", "total_shipments": 20,
         "website": "https://acmeimporters.com", "datasource": "apify_kw", "source_url": "https://acmeimporters.com"},
    ]
    mock_web.return_value = [
        {"company_name": "Beta Distributors", "country": "US",
         "website": "https://betadist.com", "datasource": "web_search", "source_url": "https://betadist.com"},
        # This one equals the industry leader / seed and must be excluded.
        {"company_name": "Ferguson", "country": "US",
         "website": "https://ferguson.com", "datasource": "web_search", "source_url": "https://ferguson.com"},
    ]
    config = {
        "runtime": {"mode": "live"},
        "apify": {"api_token": "test-token"},
        "pipeline": {"max_results_per_customer": 5, "min_shipments": 1, "target_countries": ["US"]},
        "discovery": {"apify_enabled": True, "web_search_enabled": True},
        "cache": {"enabled": False},
    }
    profiles = [
        CustomerProfile(
            customer_id="1",
            customer_name="MyCustomer",
            search_queries=["shower faucet"],
            hs_codes=["8481"],
            industry_leader="Ferguson",
            seed_exclude_names=["Ferguson", "MyCustomer"],
        )
    ]

    companies = discover_buyers(profiles, config)
    names = {c.company_name for c in companies}

    # Both discovery channels contributed.
    assert "Acme Importers" in names
    assert "Beta Distributors" in names
    # Seed / industry leader excluded -> genuine "new buyers" only.
    assert "Ferguson" not in names
    # Discovery is driven by search_queries (HS/product), never the customer's own name.
    mock_keyword.assert_called_once()
    assert mock_keyword.call_args.args[0] == "shower faucet"
    mock_web.assert_called_once()
