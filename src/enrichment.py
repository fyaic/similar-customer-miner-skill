"""Enrich candidate companies with contacts, social links, and revenue."""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from src.models import RawCompany, SimilarCompany
from tools.email_tool import EmailTool, domain_from_url, is_generic_email
from tools.social_tool import SocialTool
from tools.web_scraper import WebScraper

logger = logging.getLogger("similar_customer_miner")

# Static public contact/social pointers for well-known US retailers/distributors.
# Used only as demo enrichment when no website is available and no API key is configured.
STATIC_ENRICHMENT: Dict[str, Dict[str, Any]] = {
    "walmart.com": {"linkedin": "https://www.linkedin.com/company/walmart", "facebook": "https://www.facebook.com/walmart"},
    "homedepot.com": {"linkedin": "https://www.linkedin.com/company/the-home-depot", "facebook": "https://www.facebook.com/homedepot"},
    "lowes.com": {"linkedin": "https://www.linkedin.com/company/lowe's", "facebook": "https://www.facebook.com/lowes"},
    "target.com": {"linkedin": "https://www.linkedin.com/company/target", "facebook": "https://www.facebook.com/target"},
    "costco.com": {"linkedin": "https://www.linkedin.com/company/costco-wholesale", "facebook": "https://www.facebook.com/Costco"},
    "wayfair.com": {"linkedin": "https://www.linkedin.com/company/wayfair", "facebook": "https://www.facebook.com/wayfair"},
    "ferguson.com": {"linkedin": "https://www.linkedin.com/company/ferguson-enterprises", "facebook": "https://www.facebook.com/FergusonShowrooms"},
    "williams-sonoma.com": {"linkedin": "https://www.linkedin.com/company/williams-sonoma-inc", "facebook": "https://www.facebook.com/WilliamsSonoma"},
    "ikea.com": {"linkedin": "https://www.linkedin.com/company/ikea", "facebook": "https://www.facebook.com/IKEAUSA"},
    "michaels.com": {"linkedin": "https://www.linkedin.com/company/michaels-stores", "facebook": "https://www.facebook.com/MichaelsStores"},
    "hobbylobby.com": {"linkedin": "https://www.linkedin.com/company/hobby-lobby", "facebook": "https://www.facebook.com/HobbyLobby"},
    "dollargeneral.com": {"linkedin": "https://www.linkedin.com/company/dollar-general", "facebook": "https://www.facebook.com/dollargeneral"},
    "dollartree.com": {"linkedin": "https://www.linkedin.com/company/dollar-tree", "facebook": "https://www.facebook.com/DollarTree"},
    "biglots.com": {"linkedin": "https://www.linkedin.com/company/big-lots", "facebook": "https://www.facebook.com/BigLots"},
    "rossstores.com": {"linkedin": "https://www.linkedin.com/company/ross-stores", "facebook": "https://www.facebook.com/rossdressforless"},
}


def enrich_companies(
    verified: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> List[SimilarCompany]:
    """Convert verified raw companies into enriched SimilarCompany objects."""
    scraper = WebScraper(config)
    email_tool = EmailTool(config)
    social_tool = SocialTool(config)
    # Cost guard: cap Hunter domain lookups per run so a big candidate set cannot
    # exhaust the (free-tier) monthly quota. The counter is shared across worker
    # threads and guarded by a lock; which candidates consume the budget is
    # first-come-first-served under concurrency, but the cap itself is exact.
    hunter_budget = [config.get("discovery", {}).get("hunter_max_lookups", 25)]
    hunter_used = [0]
    hunter_lock = threading.Lock()
    max_workers = max(1, int(config.get("pipeline", {}).get("max_workers", 8) or 1))

    def _enrich_one(record: Dict[str, Any]) -> SimilarCompany:
        raw: RawCompany = record["raw"]
        website_data = record.get("website", {})
        is_demo = raw.datasource == "importyeti_demo"

        # Only scrape real (non-demo) websites, and only if company_verify hasn't
        # already attempted it (avoid double-scraping the same URL).
        if raw.website and not is_demo and "reachable" not in website_data:
            try:
                website_data = scraper.scrape(raw.website)
            except Exception as exc:
                logger.warning("Enrichment scrape failed for %s: %s", raw.company_name, exc)
                website_data = {"reachable": False}

        return _build_similar_company(
            raw, website_data, email_tool, social_tool, hunter_budget, hunter_used, hunter_lock
        )

    if len(verified) > 1 and max_workers > 1:
        logger.info("Enrichment running with %d workers", max_workers)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            enriched = list(pool.map(_enrich_one, verified))
    else:
        enriched = [_enrich_one(record) for record in verified]

    cap = config.get("discovery", {}).get("hunter_max_lookups", 25)
    if hunter_used[0]:
        config.setdefault("_run_stats", {})["hunter_lookups"] = hunter_used[0]
        logger.info("Hunter domain lookups used this run: %d (cap %d)", hunter_used[0], cap)
    return enriched


def _build_similar_company(
    raw: RawCompany,
    website_data: Dict[str, Any],
    email_tool: EmailTool,
    social_tool: SocialTool,
    hunter_budget: Optional[List[int]] = None,
    hunter_used: Optional[List[int]] = None,
    hunter_lock: Optional[threading.Lock] = None,
) -> SimilarCompany:
    emails = list(website_data.get("emails", []))
    phones = list(website_data.get("phones", []))
    social = dict(website_data.get("social", {}))
    email_source_by_value: Dict[str, str] = {}
    for email in emails:
        formatted = email_tool.format_email(email)
        if formatted:
            email_source_by_value.setdefault(formatted, "website")

    website = website_data.get("url") or raw.website
    domain = domain_from_url(website) if website else None
    is_demo = raw.datasource == "importyeti_demo"

    notes: List[str] = []
    if is_demo:
        notes.append("Data source: importyeti_demo (demo fallback - not real ImportYeti results)")

    # Apply static enrichment for known domains (demo data only)
    static_used = False
    if domain and domain in STATIC_ENRICHMENT:
        static = STATIC_ENRICHMENT[domain]
        for key, value in static.items():
            if key not in social or not social[key]:
                social[key] = value
                static_used = True
    if static_used:
        notes.append("Social links from static public pointers (unverified)")

    # For real datasource results, use Hunter.io when no email exists or every
    # discovered email is generic/departmental. Demo fallback avoids bulk API consumption.
    hunter_contacts: List[Dict[str, Any]] = []
    should_query_hunter = (not emails) or all(is_generic_email(email) for email in emails)
    # Atomic check-and-increment of the shared Hunter budget (lock is None only
    # in single-threaded/test usage).
    budget_ok = True
    if domain and should_query_hunter and not is_demo and hunter_budget is not None and hunter_used is not None:
        if hunter_lock is not None:
            with hunter_lock:
                budget_ok = hunter_used[0] < hunter_budget[0]
                if budget_ok:
                    hunter_used[0] += 1
        else:
            budget_ok = hunter_used[0] < hunter_budget[0]
            if budget_ok:
                hunter_used[0] += 1
    if domain and should_query_hunter and not is_demo and budget_ok:
        hunter_contacts = email_tool.hunter_domain_contacts(domain)
        hunter_emails = [contact.get("email") for contact in hunter_contacts if contact.get("email")]
        if hunter_emails:
            known_emails = {email_tool.format_email(email) for email in emails}
            for email in hunter_emails:
                formatted = email_tool.format_email(email)
                if not formatted:
                    continue
                email_source_by_value[formatted] = "hunter"
                if formatted not in known_emails:
                    emails.append(formatted)
                    known_emails.add(formatted)
            notes.append("Emails discovered via Hunter.io domain search")

    # For demo fallback, infer a generic contact email from the domain so the
    # output remains structurally complete. This is clearly flagged as inferred.
    if is_demo and domain and not emails:
        inferred_email = f"info@{domain}"
        emails.append(inferred_email)
        email_source_by_value[inferred_email] = "domain_inference"
        notes.append("Email inferred from domain pattern (info@domain)")

    # Validate social links for non-demo data; demo static links are trusted.
    if is_demo:
        active_social = social
    else:
        social_reachable = social_tool.check_links(social)
        active_social = {k: v for k, v in social.items() if social_reachable.get(k)}
        dropped = set(social.keys()) - set(active_social.keys())
        if dropped:
            notes.append(f"Unreachable social links dropped: {', '.join(sorted(dropped))}")

    # Build first contact only from structured person fields, never email local parts.
    contact_name: Optional[str] = None
    contact_title: Optional[str] = None
    contact_source: Optional[str] = None
    for contact in hunter_contacts:
        email = contact.get("email") or ""
        first_name = (contact.get("first_name") or "").strip()
        last_name = (contact.get("last_name") or "").strip()
        if is_generic_email(email) or not (first_name or last_name):
            continue
        formatted_contact_email = email_tool.format_email(email)
        if formatted_contact_email:
            emails = [formatted_contact_email] + [
                existing for existing in emails if email_tool.format_email(existing) != formatted_contact_email
            ]
        contact_name = " ".join(part for part in [first_name, last_name] if part)
        contact_title = contact.get("position") or None
        contact_source = "Hunter.io structured person fields"
        notes.append("Contact person from structured Hunter.io fields")
        break

    if emails and is_generic_email(emails[0]):
        notes.append("Department/generic email captured as contact channel, not a verified person")

    # Frequency string
    shipment_frequency = None
    if raw.total_shipments is not None:
        shipment_frequency = f"{raw.total_shipments} shipments (recent)"

    # Confidence calibration
    # Demo data is structurally complete but synthetic; real data is primary-source but may be sparse.
    # Demo fallback is structurally complete but synthetic; keep confidence
    # moderate-high so it is useful for quantity testing while still honest.
    base_conf = 0.78 if is_demo else 0.70
    inferred_conf = 0.35
    static_conf = 0.50
    scraped_conf = 0.65

    # Citations
    source_citation = raw.source_url or ("importyeti_demo" if is_demo else raw.datasource or "unknown")
    website_citation = website or source_citation

    # Per-field confidence/citation decisions
    company_name_conf = 0.75 if is_demo else 0.90
    country_conf = 0.85
    website_conf = 0.90 if website else 0.0
    main_products_conf = base_conf if raw.product_description else (scraped_conf if website_data.get("description") else 0.0)
    main_products_citation = source_citation if raw.product_description else (website_citation if website_data.get("description") else None)
    hs_codes_conf = base_conf if raw.hs_codes else 0.0
    industry_tags_conf = base_conf if raw.industry_tags else 0.0

    revenue_conf = base_conf if raw.revenue else 0.0
    estimated_spend_conf = 0.5 if raw.estimated_shipping_spend else 0.0  # proxy -> moderate
    customs_purchase_conf = base_conf if raw.customs_china_purchase else 0.0  # 0 this run (no source)
    shipment_frequency_conf = base_conf if raw.total_shipments is not None else 0.3

    contact_name_conf = base_conf if contact_name else 0.0
    contact_title_conf = base_conf if contact_title else 0.0
    contact_citation = contact_source if contact_name else None

    phone_conf = base_conf if phones else 0.0
    phone_citation = website_citation if phones else None

    email_obj = next((email_tool.format_email(email) for email in emails if email_tool.format_email(email)), None)
    email_source = email_source_by_value.get(email_obj or "")
    email_inferred = email_source == "domain_inference"
    email_conf = inferred_conf if email_inferred else (base_conf if emails else 0.0)
    if email_source == "hunter":
        email_citation = "Hunter.io domain search"
    elif email_source == "domain_inference":
        email_citation = "domain pattern inference"
    else:
        email_citation = website_citation if emails else None

    # Social per-platform
    social_conf_map: Dict[str, float] = {}
    social_citation_map: Dict[str, Optional[str]] = {}
    for platform in ("linkedin", "facebook", "twitter", "youtube"):
        url = active_social.get(platform)
        if url:
            if static_used and platform in STATIC_ENRICHMENT.get(domain or "", {}):
                social_conf_map[platform] = static_conf
                social_citation_map[platform] = f"static public pointer ({platform})"
            elif is_demo:
                social_conf_map[platform] = base_conf
                social_citation_map[platform] = website_citation
            else:
                social_conf_map[platform] = scraped_conf
                social_citation_map[platform] = website_citation
        else:
            social_conf_map[platform] = 0.0
            social_citation_map[platform] = None

    all_citations: Dict[str, str] = {"datasource": raw.datasource or "unknown"}
    if raw.source_url:
        all_citations["source_url"] = raw.source_url
    if website:
        all_citations["website"] = website

    company = SimilarCompany(
        source_seed=raw.source_seed,
        source_seed_citation=source_citation,
        source_seed_confidence=1.0 if raw.source_seed else 0.0,
        company_name=raw.company_name,
        company_name_citation=source_citation,
        company_name_confidence=company_name_conf,
        country=raw.country,
        country_citation=source_citation,
        country_confidence=country_conf,
        region=raw.region,
        region_citation=source_citation,
        region_confidence=base_conf if raw.region else 0.0,
        website=website,
        website_citation=website_citation,
        website_confidence=website_conf,
        main_products=raw.product_description or website_data.get("description"),
        main_products_citation=main_products_citation,
        main_products_confidence=main_products_conf,
        hs_codes=raw.hs_codes,
        hs_codes_citation=source_citation,
        hs_codes_confidence=hs_codes_conf,
        industry_tags=raw.industry_tags,
        industry_tags_citation=source_citation,
        industry_tags_confidence=industry_tags_conf,
        revenue=raw.revenue,
        revenue_citation=source_citation,
        revenue_confidence=revenue_conf,
        china_purchase=None,  # deprecated: no longer populated (was conflating shipping spend)
        china_purchase_citation=None,
        china_purchase_confidence=0.0,
        customs_china_purchase=raw.customs_china_purchase,
        customs_china_purchase_citation=source_citation if raw.customs_china_purchase else None,
        customs_china_purchase_confidence=customs_purchase_conf,
        estimated_shipping_spend=raw.estimated_shipping_spend,
        estimated_shipping_spend_citation=source_citation if raw.estimated_shipping_spend else None,
        estimated_shipping_spend_confidence=estimated_spend_conf,
        procurement_proxy_notes=raw.procurement_proxy_notes,
        shipment_frequency=shipment_frequency,
        shipment_frequency_citation=source_citation,
        shipment_frequency_confidence=shipment_frequency_conf,
        contact_name=contact_name,
        contact_name_citation=contact_citation,
        contact_name_confidence=contact_name_conf,
        contact_title=contact_title,
        contact_title_citation=contact_citation,
        contact_title_confidence=contact_title_conf,
        phone=phones[0] if phones else None,
        phone_citation=phone_citation,
        phone_confidence=phone_conf,
        email=email_obj,
        email_citation=email_citation,
        email_confidence=email_conf,
        linkedin=active_social.get("linkedin"),
        linkedin_citation=social_citation_map.get("linkedin"),
        linkedin_confidence=social_conf_map.get("linkedin", 0.0),
        facebook=active_social.get("facebook"),
        facebook_citation=social_citation_map.get("facebook"),
        facebook_confidence=social_conf_map.get("facebook", 0.0),
        twitter=active_social.get("twitter"),
        twitter_citation=social_citation_map.get("twitter"),
        twitter_confidence=social_conf_map.get("twitter", 0.0),
        youtube=active_social.get("youtube"),
        youtube_citation=social_citation_map.get("youtube"),
        youtube_confidence=social_conf_map.get("youtube", 0.0),
        all_citations=all_citations,
        notes="; ".join(notes) if notes else None,
    )
    return company
