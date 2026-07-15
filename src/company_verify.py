"""Verify company existence and enrich registration details."""
import logging
from typing import Any, Dict, List

from src.models import RawCompany
from src.utils import get_cache_dir
from tools.importyeti_tool import ImportYetiTool
from tools.opencorporates_tool import OpenCorporatesTool
from tools.web_scraper import WebScraper

logger = logging.getLogger("similar_customer_miner")


def verify_companies(companies: List[RawCompany], config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Verify each candidate via BOL import records, OpenCorporates, website reachability.

    The BOL (bill-of-lading) actor is used here as a VERIFIER — confirms a discovered
    candidate genuinely imports and backfills shipments/HS/shipping-spend. It is no
    longer a discovery source. BOL is cost-gated and fails gracefully (e.g. Apify
    monthly hard-limit).
    """
    oc_tool = OpenCorporatesTool(config, cache_dir=get_cache_dir(config))
    bol_tool = ImportYetiTool(config, cache_dir=get_cache_dir(config))
    scraper = WebScraper(config)
    is_live = config.get("runtime", {}).get("mode") == "live"
    disc = config.get("discovery", {})
    max_verify = disc.get("max_verify_candidates", 30)
    country = (config.get("pipeline", {}).get("target_countries", ["US"]) or ["US"])[0]
    bol_stats = {"attempted": 0, "verified": 0, "failed": 0, "skipped_cost": 0, "circuit_open": False}
    bol_disabled = False  # circuit breaker: stop after Apify account hard-limit
    verified: List[Dict[str, Any]] = []

    for idx, company in enumerate(companies):
        record: Dict[str, Any] = {"raw": company, "verification": {}, "website": {}, "bol": {}}

        # BOL import verification (live only, cost-gated, graceful, circuit-broken)
        if is_live and bol_tool.token and not bol_disabled:
            if idx < max_verify:
                bol_stats["attempted"] += 1
                try:
                    rows = bol_tool.verify_import(company.company_name, country=country, limit=3)
                    summary = _summarize_bol(rows)
                    record["bol"] = summary
                    if summary.get("total_shipments"):
                        company.total_shipments = company.total_shipments or summary["total_shipments"]
                        if summary.get("hs_codes") and not company.hs_codes:
                            company.hs_codes = summary["hs_codes"]
                        if summary.get("estimated_shipping_spend"):
                            company.estimated_shipping_spend = summary["estimated_shipping_spend"]
                            company.procurement_proxy_notes = (
                                "Estimated shipping spend (BOL), not verified customs procurement value"
                            )
                        bol_stats["verified"] += 1
                except Exception as exc:
                    logger.warning("BOL verify failed for %s: %s", company.company_name, exc)
                    record["bol"] = {"verified": False, "error": str(exc)}
                    bol_stats["failed"] += 1
                    # Trip the circuit on account-level hard limit / forbidden — further
                    # calls would only waste time failing identically.
                    if any(s in str(exc).lower() for s in ("hard limit", "403", "forbidden", "feature-disabled")):
                        bol_disabled = True
                        bol_stats["circuit_open"] = True
                        logger.warning("BOL circuit opened (account limit/403); skipping remaining BOL verifies")
            else:
                bol_stats["skipped_cost"] += 1

        try:
            oc_result = oc_tool.verify(company.company_name, company.country)
            record["verification"] = oc_result
        except Exception as exc:
            logger.warning("OpenCorporates verify failed for %s: %s", company.company_name, exc)
            record["verification"] = {"verified": False, "error": str(exc)}

        # Website check if URL is explicitly available and not demo data
        if company.website and company.datasource != "importyeti_demo":
            try:
                scrape = scraper.scrape(company.website)
                record["website"] = scrape
            except Exception as exc:
                logger.warning("Website check failed for %s: %s", company.website, exc)
                record["website"] = {"reachable": False, "error": str(exc)}

        verified.append(record)

    config.setdefault("_run_stats", {})["bol_verify"] = bol_stats
    logger.info("BOL verify: %s", bol_stats)
    return verified


def _summarize_bol(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Condense BOL actor rows into a verification summary for one company."""
    if not rows:
        return {"verified": False}
    total = 0
    hs: List[str] = []
    spend = None
    recent = None
    for r in rows:
        ts = r.get("total_shipments")
        if isinstance(ts, (int, float)):
            total += int(ts)
        for c in (r.get("hs_codes") or []):
            if c not in hs:
                hs.append(c)
        spend = spend or r.get("estimated_shipping_spend")
        recent = recent or r.get("recent_shipment_date")
    return {
        "verified": True,
        "total_shipments": total or None,
        "hs_codes": hs,
        "estimated_shipping_spend": spend,
        "recent_shipment_date": recent,
    }
