"""Fact-check candidate companies."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

from src.models import SimilarCompany
from src.utils import get_cache_dir
from tools.google_factcheck_tool import GoogleFactCheckTool

logger = logging.getLogger("similar_customer_miner")


def fact_check_companies(
    companies: List[SimilarCompany],
    config: Optional[Dict[str, Any]] = None,
) -> List[SimilarCompany]:
    """Run fact-check rules and optional external claim checks."""
    fc_tool: Optional[GoogleFactCheckTool] = None
    fc_enabled = bool(
        config
        and config.get("google", {}).get("fact_check_enabled", False)
        and (config.get("google", {}).get("fact_check_api_key") or os.getenv("GOOGLE_FACT_CHECK_API_KEY"))
    )
    fc_min_confidence = config.get("google", {}).get("min_confidence", 0.7) if config else 0.7
    if fc_enabled:
        fc_tool = GoogleFactCheckTool(config, cache_dir=get_cache_dir(config))

    for company in companies:
        checks = []
        notes: List[str] = []
        if company.notes:
            notes.append(company.notes)

        # Company existence
        if company.company_name and len(company.company_name) > 2:
            checks.append(True)
        else:
            checks.append(False)

        # Purchase <= revenue * 0.7
        revenue_num = _extract_number(company.revenue)
        purchase_num = _extract_number(company.china_purchase)
        if revenue_num and purchase_num:
            checks.append(purchase_num <= revenue_num * 0.7)
        else:
            checks.append(True)  # cannot verify

        # Contact reachable: email or social
        has_contact = bool(company.email) or bool(company.phone) or bool(company.linkedin)
        checks.append(has_contact)

        # HS consistency
        checks.append(len(company.hs_codes) > 0)

        # Region consistency
        checks.append(company.country and company.country.upper() in {"US", "USA", "United States"})

        # Optional Google Fact Check lookup for external claim reviews.
        # Only run for high-confidence leads to keep API usage reasonable.
        if fc_tool and company.company_name and (company.overall_confidence or 0) >= fc_min_confidence:
            _check_external_claims(company, fc_tool, notes)

        failed = sum(1 for c in checks if c is False)
        if failed == 0:
            company.fact_check_status = "passed"
        elif failed <= 2:
            company.fact_check_status = "pending"
        else:
            company.fact_check_status = "failed"

        if notes:
            company.notes = "; ".join(notes)

    return companies


def _check_external_claims(
    company: SimilarCompany,
    fc_tool: GoogleFactCheckTool,
    notes: List[str],
) -> None:
    """Look up published external claim reviews via Google Fact Check API.

    Results are supplemental citations only. They do not prove revenue,
    procurement, customs, or other business metrics.
    """
    claims: List[str] = []
    if company.revenue:
        claims.append(company.revenue)
    if company.china_purchase:
        claims.append(company.china_purchase)

    if not claims:
        return

    # Build one bounded external-claim query combining company name and key numbers.
    claim_summary = " ".join(claims)
    query = f"{company.company_name} {claim_summary}".strip()

    try:
        reviews = fc_tool.search_claims(query, language="en", page_size=5)
        if reviews:
            ratings = [r["textual_rating"] for r in reviews if r.get("textual_rating")]
            publishers = [r["publisher"] for r in reviews if r.get("publisher")]
            notes.append(
                f"External claim review search found {len(reviews)} supplemental review(s) "
                f"(not revenue/procurement proof): ratings={ratings}; publishers={publishers}"
            )
            for review in reviews:
                url = review.get("review_url")
                publisher = review.get("publisher") or "google-fact-check"
                if url and publisher:
                    company.all_citations.setdefault(f"external_claim_review_{publisher}", url)
    except Exception as exc:
        logger.warning("External claim review lookup failed for %s: %s", company.company_name, exc)


def _extract_claim_number(value: Optional[str]) -> str:
    """Extract a concise numeric claim from a string like '$50B - $600B'."""
    if not value:
        return ""
    text = str(value).lower().replace(",", "").replace("$", "").strip()
    # Find the first number with unit
    match = re.search(r"\d+(?:\.\d+)?\s*[bmk]?", text)
    if not match:
        return ""
    return match.group()


def _extract_number(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    text = str(value).lower().replace(",", "").replace("$", "").strip()
    # Look for billion/million/thousand
    multiplier = 1.0
    if "billion" in text or "b" in text.split():
        multiplier = 1_000_000_000
    elif "million" in text or "m" in text.split():
        multiplier = 1_000_000
    elif "thousand" in text or "k" in text.split():
        multiplier = 1_000
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    return float(match.group()) * multiplier
