"""Core data models for similar-customer-miner."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Customer:
    """Input customer record."""

    id: str
    name: Optional[str] = None
    business_positioning: Optional[str] = None
    region_positioning: Optional[str] = None
    main_products: Optional[str] = None
    hs_codes: List[str] = field(default_factory=list)
    value_weight_ratio: Optional[str] = None
    industry_leader: Optional[str] = None
    leader_revenue: Optional[str] = None
    local_competitors: Optional[str] = None
    market_size: Optional[str] = None
    annual_shipment_frequency: Optional[str] = None
    annual_china_purchase: Optional[str] = None
    customer_revenue: Optional[str] = None
    shipping_modes: List[str] = field(default_factory=list)
    profit_level: Optional[str] = None
    margin_per_shipment: Optional[str] = None


@dataclass
class CustomerProfile:
    """Generated profile from a customer record."""

    customer_id: str
    customer_name: Optional[str] = None
    industry_tags: List[str] = field(default_factory=list)
    product_tags: List[str] = field(default_factory=list)
    hs_codes: List[str] = field(default_factory=list)
    hs_chapters: List[str] = field(default_factory=list)
    target_regions: List[str] = field(default_factory=list)
    target_channels: List[str] = field(default_factory=list)
    scale_bucket: Optional[str] = None
    shipment_freq_bucket: Optional[str] = None
    purchase_bucket: Optional[str] = None
    value_route: Optional[str] = None
    search_queries: List[str] = field(default_factory=list)
    # Names to exclude from discovery output (this customer + industry leader + competitors).
    industry_leader: Optional[str] = None
    seed_exclude_names: List[str] = field(default_factory=list)


@dataclass
class RawCompany:
    """Candidate company discovered from a data source."""

    company_name: str
    country: Optional[str] = None
    region: Optional[str] = None
    website: Optional[str] = None
    main_products: Optional[str] = None
    hs_codes: List[str] = field(default_factory=list)
    industry_tags: List[str] = field(default_factory=list)
    revenue: Optional[str] = None
    china_purchase: Optional[str] = None  # deprecated alias; kept for back-compat, no longer populated
    customs_china_purchase: Optional[str] = None       # verified customs procurement value only
    estimated_shipping_spend: Optional[str] = None      # BOL proxy, NOT procurement value
    procurement_proxy_notes: Optional[str] = None       # explains proxy nature
    total_shipments: Optional[int] = None
    recent_shipment_date: Optional[str] = None
    product_description: Optional[str] = None
    suppliers: List[str] = field(default_factory=list)
    source_url: Optional[str] = None
    source_seed: Optional[str] = None
    datasource: Optional[str] = None


@dataclass
class SimilarCompany:
    """Final enriched and scored similar company.

    Every exported scalar/list field has a matching `_citation` and
    `_confidence` so downstream reviewers can trace and trust each value.
    """

    # Identifiers
    source_seed: Optional[str] = None
    source_seed_citation: Optional[str] = None
    source_seed_confidence: float = 0.0

    # Core company fields
    company_name: Optional[str] = None
    company_name_citation: Optional[str] = None
    company_name_confidence: float = 0.0

    country: Optional[str] = None
    country_citation: Optional[str] = None
    country_confidence: float = 0.0

    region: Optional[str] = None
    region_citation: Optional[str] = None
    region_confidence: float = 0.0

    website: Optional[str] = None
    website_citation: Optional[str] = None
    website_confidence: float = 0.0

    main_products: Optional[str] = None
    main_products_citation: Optional[str] = None
    main_products_confidence: float = 0.0

    hs_codes: List[str] = field(default_factory=list)
    hs_codes_citation: Optional[str] = None
    hs_codes_confidence: float = 0.0

    industry_tags: List[str] = field(default_factory=list)
    industry_tags_citation: Optional[str] = None
    industry_tags_confidence: float = 0.0

    # Financial / operational
    revenue: Optional[str] = None
    revenue_citation: Optional[str] = None
    revenue_confidence: float = 0.0

    china_purchase: Optional[str] = None  # deprecated alias; retained for back-compat only
    china_purchase_citation: Optional[str] = None
    china_purchase_confidence: float = 0.0

    # Verified customs procurement value (only filled with a real customs source).
    customs_china_purchase: Optional[str] = None
    customs_china_purchase_citation: Optional[str] = None
    customs_china_purchase_confidence: float = 0.0

    # BOL-derived shipping-spend proxy (explicitly NOT procurement value).
    estimated_shipping_spend: Optional[str] = None
    estimated_shipping_spend_citation: Optional[str] = None
    estimated_shipping_spend_confidence: float = 0.0
    procurement_proxy_notes: Optional[str] = None

    shipment_frequency: Optional[str] = None
    shipment_frequency_citation: Optional[str] = None
    shipment_frequency_confidence: float = 0.0

    # Contact fields (split per field for full traceability)
    contact_name: Optional[str] = None
    contact_name_citation: Optional[str] = None
    contact_name_confidence: float = 0.0

    contact_title: Optional[str] = None
    contact_title_citation: Optional[str] = None
    contact_title_confidence: float = 0.0

    phone: Optional[str] = None
    phone_citation: Optional[str] = None
    phone_confidence: float = 0.0

    email: Optional[str] = None
    email_citation: Optional[str] = None
    email_confidence: float = 0.0
    email_verified: bool = False
    email_verification_status: str = 'not_checked'
    email_verification_raw_status: str = 'not_checked'
    email_is_catch_all: Optional[bool] = None
    email_is_safe_to_send: Optional[bool] = None
    email_verified_at: Optional[str] = None
    email_verification_citation: Optional[str] = None
    product_match_status: str = 'unreviewed'
    product_match_reason: Optional[str] = None
    product_evidence_citation: Optional[str] = None
    product_evidence_checked_at: Optional[str] = None
    product_evidence_reviewer: Optional[str] = None
    product_evidence_excerpt: Optional[str] = None
    business_role: str = 'unknown'  # Provider text hint, not independently verified.
    business_role_citation: Optional[str] = None
    import_evidence_status: str = 'not_checked'
    import_evidence_citation: Optional[str] = None
    buyer_qualification: str = 'unverified'
    contact_role_fit: Optional[bool] = None  # Title heuristic only, not employment verification

    # Social links (per-platform citation/confidence)
    linkedin: Optional[str] = None
    linkedin_citation: Optional[str] = None
    linkedin_confidence: float = 0.0

    facebook: Optional[str] = None
    facebook_citation: Optional[str] = None
    facebook_confidence: float = 0.0

    twitter: Optional[str] = None
    twitter_citation: Optional[str] = None
    twitter_confidence: float = 0.0

    youtube: Optional[str] = None
    youtube_citation: Optional[str] = None
    youtube_confidence: float = 0.0

    # Aggregate scores and review state
    similarity_score: float = 0.0
    fit_score: float = 0.0        # how well the candidate matches the target profile (0-1)
    priority_score: float = 0.0   # worth-contacting: import strength + fit + reachability (0-1)
    overall_confidence: float = 0.0
    grade: str = "C"
    fact_check_status: str = "pending"

    all_citations: Dict[str, str] = field(default_factory=dict)
    notes: Optional[str] = None
