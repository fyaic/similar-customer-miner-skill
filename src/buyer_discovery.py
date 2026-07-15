"""Discover candidate buyers via a dual-channel discovery layer.

Channels (run per profile, results merged + deduped):
  1. Apify keyword/HS search actor  -> ImportYetiTool.keyword_search (importer list)
  2. Web search (keyless DuckDuckGo) -> web_discovery.search_importers

The BOL (bill-of-lading) actor is NOT a discovery source anymore; it is a
verifier and lives in company_verify. Candidates that match a seed/industry-leader
name or domain are excluded so output is genuinely "similar NEW buyers", not the
seed companies themselves.
"""
import logging
from typing import Any, Dict, List, Set

from src.models import CustomerProfile, RawCompany
from src.utils import get_cache_dir, normalize_company_name
from tools import web_discovery
from tools.email_tool import domain_from_url
from tools.importyeti_tool import ImportYetiTool

logger = logging.getLogger("similar_customer_miner")


def discover_buyers(
    profiles: List[CustomerProfile],
    config: Dict[str, Any],
) -> List[RawCompany]:
    """Discover candidate companies for each customer profile (dual channel)."""
    tool = ImportYetiTool(config, cache_dir=get_cache_dir(config))
    disc = config.get("discovery", {})
    apify_on = disc.get("apify_enabled", True)
    web_on = disc.get("web_search_enabled", True)
    max_results = config.get("pipeline", {}).get("max_results_per_customer", 30)
    min_shipments = config.get("pipeline", {}).get("min_shipments", 5)
    country = (config.get("pipeline", {}).get("target_countries", ["US"]) or ["US"])[0]
    is_live = config.get("runtime", {}).get("mode") == "live"

    seed_keys = _seed_keys(profiles)
    all_companies: List[RawCompany] = []
    seen_names: Set[str] = set()
    seen_domains: Set[str] = set()
    stats = {"apify": 0, "web_search": 0, "demo": 0, "excluded_seed": 0, "deduped": 0}

    for profile in profiles:
        candidates: List[Dict[str, Any]] = []

        if not is_live:
            # Offline demo/test channel: built-in importer pool, deterministic, no
            # network and no env-token leakage. Live web/Apify runs only in mode=live.
            for query in (profile.search_queries[:3] or [profile.customer_name or ""]):
                if not query:
                    continue
                rows = tool._demo_results(query, min_shipments, max_results)
                candidates.extend(rows)
                stats["demo"] += len(rows)
        else:
            # Channel 1: Apify keyword/HS search (graceful — account limit / 403 tolerated)
            if apify_on:
                for query in (profile.search_queries[:3] or [profile.customer_name or ""]):
                    if not query:
                        continue
                    try:
                        rows = tool.keyword_search(
                            query, country=country, min_shipments=min_shipments, limit=max_results
                        )
                        for r in rows:
                            r.setdefault("datasource", "apify_kw")
                        candidates.extend(rows)
                        stats["apify"] += len(rows)
                    except Exception as exc:
                        logger.warning("Apify keyword discovery failed for %s: %s", query, exc)

            # Channel 2: Web search (keyless) — also supplies the official website/domain
            if web_on:
                try:
                    web_rows = web_discovery.search_importers(profile, country=country, config=config)
                    candidates.extend(web_rows)
                    stats["web_search"] += len(web_rows)
                except Exception as exc:
                    logger.warning("Web discovery failed for %s: %s", profile.customer_id, exc)

        # Merge: exclude seeds, dedup by normalized name + domain
        for item in candidates:
            name = item.get("company_name")
            if not name:
                continue
            nkey = normalize_company_name(name) or name.lower().strip()
            website = item.get("website")
            dkey = (domain_from_url(website) or "").lower() if website else ""

            if nkey in seed_keys or (dkey and dkey in seed_keys):
                stats["excluded_seed"] += 1
                continue
            if nkey in seen_names or (dkey and dkey in seen_domains):
                stats["deduped"] += 1
                continue
            seen_names.add(nkey)
            if dkey:
                seen_domains.add(dkey)

            all_companies.append(RawCompany(
                company_name=name,
                country=item.get("country", country),
                website=website,
                total_shipments=item.get("total_shipments"),
                recent_shipment_date=item.get("recent_shipment_date"),
                product_description=item.get("product_description"),
                hs_codes=item.get("hs_codes", []),
                industry_tags=item.get("industry_tags", []),
                revenue=item.get("revenue"),
                estimated_shipping_spend=item.get("estimated_shipping_spend"),
                procurement_proxy_notes=item.get("procurement_proxy_notes"),
                suppliers=item.get("suppliers", []),
                source_url=item.get("source_url"),
                source_seed=profile.customer_id,
                datasource=item.get("datasource", "web_search"),
            ))

    logger.info(
        "Discovered %d candidates (apify=%d web=%d, excluded_seed=%d deduped=%d)",
        len(all_companies), stats["apify"], stats["web_search"],
        stats["excluded_seed"], stats["deduped"],
    )
    config.setdefault("_run_stats", {})["discovery"] = stats
    return all_companies


def _seed_keys(profiles: List[CustomerProfile]) -> Set[str]:
    """Collect normalized names to exclude (seed customers + industry leaders + competitors)."""
    keys: Set[str] = set()
    for p in profiles:
        names = [p.customer_name, getattr(p, "industry_leader", None)]
        names += list(getattr(p, "seed_exclude_names", []) or [])
        for raw in names:
            nk = normalize_company_name(raw) if raw else None
            if nk:
                keys.add(nk)
    return keys
