"""Tests for profiler module."""
from src.models import Customer
from src.profiler import profile_customers


def test_profile_customers():
    customers = [
        Customer(
            id="1",
            name="Test Co",
            main_products="shower faucet / ceramic tile",
            hs_codes=["848180", "690490"],
            region_positioning="全美最强",
            annual_shipment_frequency="30",
            customer_revenue="50 million",
        )
    ]
    profiles = profile_customers(customers)
    assert len(profiles) == 1
    profile = profiles[0]
    assert set(profile.hs_chapters) == {"84", "69"}
    assert len(profile.search_queries) >= 3
    assert profile.value_route == "mixed"
