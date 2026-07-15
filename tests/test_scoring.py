"""Tests for scoring module."""
from src.models import CustomerProfile, SimilarCompany
from src.scoring import score_companies


def test_score_companies():
    config = {"pipeline": {"grade_thresholds": {"A": 0.8, "B": 0.5}}}
    profiles = [
        CustomerProfile(
            customer_id="1",
            customer_name="Anchor",
            hs_codes=["8481"],
            product_tags=["shower", "faucet"],
            target_regions=["US"],
        )
    ]
    companies = [
        SimilarCompany(
            company_name="American Bath Group",
            company_name_confidence=0.9,
            country="US",
            country_confidence=0.85,
            hs_codes=["8481"],
            hs_codes_confidence=0.9,
            main_products="shower systems",
            main_products_confidence=0.7,
            shipment_frequency="120 shipments (recent)",
            shipment_frequency_confidence=0.7,
            revenue="$1B - $10B",
            revenue_confidence=0.7,
            email_confidence=0.6,
            phone_confidence=0.6,
            linkedin_confidence=0.6,
            facebook_confidence=0.6,
        )
    ]
    scored = score_companies(companies, profiles, config)
    assert len(scored) == 1
    assert 0 <= scored[0].similarity_score <= 1
    assert 0 <= scored[0].overall_confidence <= 1
    assert scored[0].grade in {"A", "B", "C"}


def _make_company(name: str, conf: float) -> SimilarCompany:
    """Create a SimilarCompany with all weighted confidences set to `conf`."""
    return SimilarCompany(
        company_name=name,
        company_name_confidence=conf,
        website_confidence=conf,
        estimated_shipping_spend_confidence=conf,
        shipment_frequency_confidence=conf,
        revenue_confidence=conf,
        contact_name_confidence=conf,
        email_confidence=conf,
        phone_confidence=conf,
        linkedin_confidence=conf,
        facebook_confidence=conf,
        twitter_confidence=conf,
        youtube_confidence=conf,
    )


def test_grade_sorting():
    config = {"pipeline": {"grade_thresholds": {"A": 0.8, "B": 0.5}}}
    profiles = [CustomerProfile(customer_id="1", customer_name="Anchor")]
    companies = [
        _make_company("A-Co", 0.9),   # overall >= 0.8
        _make_company("B-Co", 0.6),   # overall ~0.6
        _make_company("C-Co", 0.0),   # overall very low
    ]
    scored = score_companies(companies, profiles, config)
    # ABC grade semantics unchanged (pure confidence). These synthetic companies have
    # no website/email VALUES, so priority_score is 0 for all and the secondary sort
    # key (grade) preserves the A, B, C order.
    grades = [c.grade for c in scored]
    assert grades == ["A", "B", "C"]
