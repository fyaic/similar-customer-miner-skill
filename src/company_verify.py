"""Verify company existence and enrich registration details."""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

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

    Per-company verification is network-bound, so companies are verified in a
    thread pool (pipeline.max_workers). Order of the returned list matches the
    input order; the BOL cost gate (max_verify_candidates) applies to input order
    exactly as in the sequential version.
    """
    oc_tool = OpenCorporatesTool(config, cache_dir=get_cache_dir(config))
    bol_tool = ImportYetiTool(config, cache_dir=get_cache_dir(config))
    scraper = WebScraper(config)
    is_live = config.get("runtime", {}).get("mode") == "live"
    disc = config.get("discovery", {})
    max_verify = disc.get("max_verify_candidates", 30)
    country = (config.get("pipeline", {}).get("target_countries", ["US"]) or ["US"])[0]
    max_workers = max(1, int(config.get("pipeline", {}).get("max_workers", 8) or 1))

    bol_stats = {"attempted": 0, "verified": 0, "failed": 0, "skipped_cost": 0, "circuit_open": False}
    # Circuit breaker: stop after Apify account hard-limit. An Event so workers
    # in flight see it immediately instead of queueing more doomed BOL runs.
    bol_disabled = threading.Event()

    def _verify_one(item: Tuple[int, RawCompany]) -> Tuple[int, Dict[str, Any], Dict[str, int]]:
        idx, company = item
        record: Dict[str, Any] = {"raw": company, "verification": {}, "website": {}, "bol": {}}
        delta = {"attempted": 0, "verified": 0, "failed": 0, "skipped_cost": 0}

        # BOL import verification (live only, cost-gated, graceful, circuit-broken)
        if is_live and bol_tool.token and not bol_disabled.is_set():
            if idx < max_verify:
                delta["attempted"] += 1
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
                        delta["verified"] += 1
                except Exception as exc:
                    logger.warning("BOL verify failed for %s: %s", company.company_name, exc)
                    record["bol"] = {"verified": False, "error": str(exc)}
                    delta["failed"] += 1
                    # Trip the circuit on account-level hard limit / forbidden — further
                    # calls would only waste time failing identically.
                    if any(s in str(exc).lower() for s in ("hard limit", "403", "forbidden", "feature-disabled")):
                        if not bol_disabled.is_set():
                            bol_disabled.set()
                            logger.warning("BOL circuit opened (account limit/403); skipping remaining BOL verifies")
            else:
                delta["skipped_cost"] += 1

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

        return idx, record, delta

    results: List[Optional[Dict[str, Any]]] = [None] * len(companies)
    work = list(enumerate(companies))
    if len(companies) > 1 and max_workers > 1:
        logger.info("Company verify running with %d workers", max_workers)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            outcomes = list(pool.map(_verify_one, work))
    else:
        outcomes = [_verify_one(item) for item in work]

    for idx, record, delta in outcomes:
        results[idx] = record
        for key, value in delta.items():
            bol_stats[key] += value
    bol_stats["circuit_open"] = bol_disabled.is_set()

    verified = [r for r in results if r is not None]
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
