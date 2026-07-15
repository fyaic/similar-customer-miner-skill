"""Score similarity, confidence, and grade candidates."""
import logging
from typing import Any, Dict, List, Optional

from rapidfuzz import fuzz

from src.models import CustomerProfile, SimilarCompany
from src.utils import bucket_number

logger = logging.getLogger("similar_customer_miner")

SIMILARITY_WEIGHTS = {
    "hs": 0.30,
    "product": 0.20,
    "region": 0.15,
    "scale": 0.15,
    "frequency": 0.10,
    "value_route": 0.10,
}

FIELD_CONFIDENCE_WEIGHTS = {
    "company_name": 0.18,
    "website": 0.15,
    "shipment_frequency": 0.12,
    "estimated_shipping_spend": 0.10,
    "revenue": 0.05,
    "contact_name": 0.08,
    "email": 0.08,
    "phone": 0.04,
    "social": 0.10,
    "other": 0.10,
}


def score_companies(
    companies: List[SimilarCompany],
    profiles: List[CustomerProfile],
    config: Dict[str, Any],
) -> List[SimilarCompany]:
    """Score all companies against seed profiles."""
    grade_a = config.get("pipeline", {}).get("grade_thresholds", {}).get("A", 0.8)
    grade_b = config.get("pipeline", {}).get("grade_thresholds", {}).get("B", 0.5)

    for company in companies:
        best_profile = _find_best_profile(company, profiles)
        company.similarity_score = _compute_similarity(company, best_profile)
        company.fit_score = _fit_score(company, best_profile)
        company.priority_score = _priority_score(company)
        company.overall_confidence = _compute_overall_confidence(company)

        # ABC grade stays a pure confidence signal (unchanged semantics).
        if company.overall_confidence >= grade_a:
            company.grade = "A"
        elif company.overall_confidence >= grade_b:
            company.grade = "B"
        else:
            company.grade = "C"

    # Primary sort by priority_score (worth-contacting), then grade, then fit.
    companies.sort(key=lambda c: (-c.priority_score, {"A": 0, "B": 1, "C": 2}.get(c.grade, 3), -c.fit_score))
    return companies


def _fit_score(company: SimilarCompany, profile: Optional[CustomerProfile]) -> float:
    """How well the candidate matches the target profile (0-1). Reuses jaccard."""
    if not profile:
        return 0.0
    hs_sim = _jaccard_similarity(set(company.hs_codes or []), set(profile.hs_codes or []))
    ind_sim = _jaccard_similarity(set(company.industry_tags or []), set(profile.industry_tags or []))
    prod_sim = _text_similarity(company.main_products or "", " ".join(profile.product_tags or []))
    # If the candidate carries no comparable profile signal, keep fit low (honest, not fake-high).
    return round(0.5 * hs_sim + 0.3 * ind_sim + 0.2 * prod_sim, 3)


def _priority_score(company: SimilarCompany) -> float:
    """Worth-contacting: import strength + fit + reachability (0-1)."""
    fit = company.fit_score or 0.0
    strength = _norm_shipments(_shipments_from_frequency(company.shipment_frequency))
    reach = _reachability(company)
    return round(0.4 * fit + 0.35 * strength + 0.25 * reach, 3)


def _shipments_from_frequency(freq: Optional[str]) -> int:
    """SimilarCompany carries shipment_frequency as a string like '120 shipments'."""
    if not freq:
        return 0
    import re
    m = re.search(r"\d+", str(freq))
    return int(m.group()) if m else 0


def _norm_shipments(total: Optional[int]) -> float:
    if not total:
        return 0.0
    # log-ish normalization: 5->~0.2, 50->~0.5, 500+->~1.0
    import math
    return round(min(1.0, math.log10(total + 1) / 3.0), 3)


def _reachability(company: SimilarCompany) -> float:
    score = 0.0
    if company.website:
        score += 0.3
    if company.email:
        score += 0.3
    if company.contact_name:
        score += 0.2
    if company.linkedin or company.facebook or company.twitter or company.youtube:
        score += 0.2
    return round(min(1.0, score), 3)


def _find_best_profile(company: SimilarCompany, profiles: List[CustomerProfile]) -> Optional[CustomerProfile]:
    if not profiles:
        return None
    if company.source_seed:
        for p in profiles:
            if p.customer_id == company.source_seed:
                return p
    # Fallback to first profile
    return profiles[0]


def _compute_similarity(company: SimilarCompany, profile: Optional[CustomerProfile]) -> float:
    if not profile:
        return 0.0

    hs_sim = _jaccard_similarity(set(company.hs_codes), set(profile.hs_codes))
    product_sim = _text_similarity(
        company.main_products or "",
        " ".join(profile.product_tags),
    )
    region_sim = _region_similarity(company.country, profile.target_regions)
    scale_sim = _bucket_similarity(
        bucket_number(company.revenue),
        profile.scale_bucket,
    )
    freq_sim = _bucket_similarity(
        _freq_bucket(company.shipment_frequency),
        profile.shipment_freq_bucket,
    )
    route_sim = 1.0 if (company.notes and profile.value_route and profile.value_route in (company.notes or "").lower()) else 0.5

    score = (
        SIMILARITY_WEIGHTS["hs"] * hs_sim
        + SIMILARITY_WEIGHTS["product"] * product_sim
        + SIMILARITY_WEIGHTS["region"] * region_sim
        + SIMILARITY_WEIGHTS["scale"] * scale_sim
        + SIMILARITY_WEIGHTS["frequency"] * freq_sim
        + SIMILARITY_WEIGHTS["value_route"] * route_sim
    )
    return round(min(1.0, max(0.0, score)), 3)


def _compute_overall_confidence(company: SimilarCompany) -> float:
    values = {
        "company_name": company.company_name_confidence,
        "website": company.website_confidence,
        "shipment_frequency": company.shipment_frequency_confidence,
        "estimated_shipping_spend": company.estimated_shipping_spend_confidence,
        "revenue": company.revenue_confidence,
        "contact_name": company.contact_name_confidence,
        "email": company.email_confidence,
        "phone": company.phone_confidence,
        "social": _aggregate_social_confidence(company),
        "other": 0.3,
    }
    total = 0.0
    weight_sum = 0.0
    for field, weight in FIELD_CONFIDENCE_WEIGHTS.items():
        total += values.get(field, 0.0) * weight
        weight_sum += weight
    return round(total / weight_sum, 3) if weight_sum else 0.0


def _aggregate_social_confidence(company: SimilarCompany) -> float:
    confidences = [
        company.linkedin_confidence,
        company.facebook_confidence,
        company.twitter_confidence,
        company.youtube_confidence,
    ]
    present = [c for c in confidences if c > 0]
    if not present:
        return 0.0
    return round(sum(present) / len(present), 3)


def _jaccard_similarity(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return fuzz.token_set_ratio(a.lower(), b.lower()) / 100.0


def _region_similarity(country: Optional[str], regions: List[str]) -> float:
    if not country:
        return 0.3
    if country.upper() in {"US", "USA", "United States"}:
        return 1.0
    return 0.2


def _bucket_similarity(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.3
    return 1.0 if a == b else 0.5


def _freq_bucket(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    import re
    match = re.search(r"\d+", text)
    if not match:
        return None
    num = int(match.group())
    if num >= 100:
        return "高频(100+/年)"
    if num >= 50:
        return "中高频(50-100/年)"
    if num >= 20:
        return "中频(20-50/年)"
    if num >= 5:
        return "低频(5-20/年)"
    return "极低频(<5/年)"
