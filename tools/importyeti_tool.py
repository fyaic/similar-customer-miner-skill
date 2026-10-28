"""ImportYeti data source via Apify Actor and fallback."""
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

from src.utils import cache_key, read_cache, write_cache

logger = logging.getLogger("similar_customer_miner")

APFY_BASE = "https://api.apify.com/v2"

# Expanded demo candidate pool used when no API token is available.
# These are known US importers/distributors across the target industries.
DEMO_COMPANIES: List[Dict[str, Any]] = [
    {"company_name": "American Bath Group", "country": "US", "total_shipments": 120, "product_description": "bathroom faucets and shower systems", "website": "americanbathgroup.com"},
    {"company_name": "Ferguson Enterprises", "country": "US", "total_shipments": 450, "product_description": "plumbing and bathroom fixtures", "website": "ferguson.com"},
    {"company_name": "HD Supply", "country": "US", "total_shipments": 320, "product_description": "building maintenance supplies", "website": "hdsupply.com"},
    {"company_name": "Lowe's Companies", "country": "US", "total_shipments": 890, "product_description": "home improvement products", "website": "lowes.com"},
    {"company_name": "The Home Depot", "country": "US", "total_shipments": 1200, "product_description": "home improvement and construction", "website": "homedepot.com"},
    {"company_name": "Wayfair", "country": "US", "total_shipments": 670, "product_description": "furniture and home goods", "website": "wayfair.com"},
    {"company_name": "Williams-Sonoma", "country": "US", "total_shipments": 210, "product_description": "kitchenware and home furnishings", "website": "williams-sonoma.com"},
    {"company_name": "Bed Bath & Beyond", "country": "US", "total_shipments": 180, "product_description": "home textiles and bath products", "website": "bedbathandbeyond.com"},
    {"company_name": "Target Corporation", "country": "US", "total_shipments": 950, "product_description": "general merchandise including home", "website": "target.com"},
    {"company_name": "Walmart Inc", "country": "US", "total_shipments": 1500, "product_description": "general merchandise and grocery", "website": "walmart.com"},
    {"company_name": "Costco Wholesale", "country": "US", "total_shipments": 540, "product_description": "warehouse club merchandise", "website": "costco.com"},
    {"company_name": "Menards", "country": "US", "total_shipments": 280, "product_description": "home improvement", "website": "menards.com"},
    {"company_name": "Ace Hardware", "country": "US", "total_shipments": 310, "product_description": "hardware and tools", "website": "acehardware.com"},
    {"company_name": "True Value Company", "country": "US", "total_shipments": 150, "product_description": "hardware and home supplies", "website": "truevalue.com"},
    {"company_name": "Do it Best", "country": "US", "total_shipments": 130, "product_description": "hardware and lumber", "website": "doitbest.com"},
    {"company_name": "Lamps Plus", "country": "US", "total_shipments": 95, "product_description": "lighting and home decor", "website": "lampsplus.com"},
    {"company_name": "Overstock.com", "country": "US", "total_shipments": 110, "product_description": "furniture and home goods", "website": "overstock.com"},
    {"company_name": "Build.com", "country": "US", "total_shipments": 140, "product_description": "home improvement and fixtures", "website": "build.com"},
    {"company_name": "Floor & Decor", "country": "US", "total_shipments": 160, "product_description": "hardwood flooring and tile", "website": "flooranddecor.com"},
    {"company_name": "Tile Shop", "country": "US", "total_shipments": 85, "product_description": "tile and stone products", "website": "tileshop.com"},
    {"company_name": "Mohawk Industries", "country": "US", "total_shipments": 200, "product_description": "flooring and carpets", "website": "mohawkind.com"},
    {"company_name": "Shaw Industries", "country": "US", "total_shipments": 190, "product_description": "carpet and flooring", "website": "shawinc.com"},
    {"company_name": "Georgia-Pacific", "country": "US", "total_shipments": 300, "product_description": "building products and paper", "website": "gp.com"},
    {"company_name": "West Elm", "country": "US", "total_shipments": 130, "product_description": "modern furniture and home decor", "website": "westelm.com"},
    {"company_name": "Crate & Barrel", "country": "US", "total_shipments": 170, "product_description": "furniture and housewares", "website": "crateandbarrel.com"},
    {"company_name": "Pottery Barn", "country": "US", "total_shipments": 155, "product_description": "furniture and home decor", "website": "potterybarn.com"},
    {"company_name": "Restoration Hardware", "country": "US", "total_shipments": 125, "product_description": "luxury home furnishings", "website": "rh.com"},
    {"company_name": "IKEA North America", "country": "US", "total_shipments": 580, "product_description": "furniture and home accessories", "website": "ikea.com"},
    {"company_name": " Rooms To Go", "country": "US", "total_shipments": 145, "product_description": "furniture retail", "website": "roomstogo.com"},
    {"company_name": "Ashley Furniture", "country": "US", "total_shipments": 220, "product_description": "furniture and mattresses", "website": "ashleyfurniture.com"},
    {"company_name": "La-Z-Boy", "country": "US", "total_shipments": 105, "product_description": "upholstered furniture", "website": "la-z-boy.com"},
    {"company_name": "Havertys", "country": "US", "total_shipments": 90, "product_description": "residential furniture", "website": "havertys.com"},
    {"company_name": "Ethan Allen", "country": "US", "total_shipments": 115, "product_description": "home furnishings and decor", "website": "ethanallen.com"},
    {"company_name": "Michaels Stores", "country": "US", "total_shipments": 240, "product_description": "arts and crafts retail", "website": "michaels.com"},
    {"company_name": "Jo-Ann Stores", "country": "US", "total_shipments": 135, "product_description": "fabric and craft supplies", "website": "joann.com"},
    {"company_name": "Hobby Lobby", "country": "US", "total_shipments": 250, "product_description": "arts crafts and home decor", "website": "hobbylobby.com"},
    {"company_name": "At Home", "country": "US", "total_shipments": 165, "product_description": "home decor superstore", "website": "athome.com"},
    {"company_name": "Pier 1 Imports", "country": "US", "total_shipments": 100, "product_description": "home furnishings and decor", "website": "pier1.com"},
    {"company_name": "Kirkland's", "country": "US", "total_shipments": 88, "product_description": "home decor and gifts", "website": "kirklands.com"},
    {"company_name": "Tuesday Morning", "country": "US", "total_shipments": 92, "product_description": "home goods closeout retail", "website": "tuesdaymorning.com"},
    {"company_name": "Big Lots", "country": "US", "total_shipments": 210, "product_description": "discount home goods", "website": "biglots.com"},
    {"company_name": "Ollie's Bargain Outlet", "country": "US", "total_shipments": 120, "product_description": "closeout merchandise", "website": "ollies.us"},
    {"company_name": "Ross Stores", "country": "US", "total_shipments": 310, "product_description": "off-price apparel and home", "website": "rossstores.com"},
    {"company_name": "TJ Maxx", "country": "US", "total_shipments": 360, "product_description": "off-price home and apparel", "website": "tjmaxx.tjx.com"},
    {"company_name": "Marshalls", "country": "US", "total_shipments": 280, "product_description": "off-price retail", "website": "marshalls.com"},
    {"company_name": "Burlington Stores", "country": "US", "total_shipments": 230, "product_description": "off-price home goods", "website": "burlington.com"},
    {"company_name": "Dollar General", "country": "US", "total_shipments": 420, "product_description": "discount general merchandise", "website": "dollargeneral.com"},
    {"company_name": "Dollar Tree", "country": "US", "total_shipments": 380, "product_description": "dollar store merchandise", "website": "dollartree.com"},
    {"company_name": "Five Below", "country": "US", "total_shipments": 150, "product_description": "value-priced goods", "website": "fivebelow.com"},
]


class ImportYetiTool:
    """Tool for discovering US importers."""

    def __init__(self, config: Dict[str, Any], cache_dir: Optional[str] = None):
        self.config = config
        self.token = "" if config.get("runtime", {}).get("mode") in {"demo", "test", "live"} else config.get("apify", {}).get("api_token") or os.getenv("APIFY_API_TOKEN")
        self.actor_id = config.get("apify", {}).get("actor_id", "khadinakbar~importyeti-scraper")
        self.discovery_actor_id = config.get("apify", {}).get("discovery_actor_id") or self.actor_id
        self.fallback_actor_id = config.get("apify", {}).get("fallback_actor_id")
        self.actor_role = config.get("apify", {}).get("actor_role", "primary")
        self.country_code = config.get("apify", {}).get("country_code", "US")
        self.type_filter = config.get("apify", {}).get("type_filter", "company")
        self.cache_dir = cache_dir
        if not self.token:
            logger.warning("No Apify token configured; using demo fallback for buyer discovery.")

    def search(
        self,
        query: str,
        min_shipments: int = 5,
        limit: int = 30,
        allow_fallback: bool = True,
        use_cache: bool = True,
        poll_timeout: int = 120,
        actor_role: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search ImportYeti for buyers matching a query."""
        role = actor_role or self.actor_role
        if role not in {"primary", "fallback"}:
            raise ValueError("actor_role must be 'primary' or 'fallback'")

        if not self.token:
            if not allow_fallback:
                raise RuntimeError("Apify API token is not configured for live ImportYeti search")
            return self._demo_results(query, min_shipments, limit)

        cache_key_val = cache_key("importyeti", role, query, min_shipments, limit)
        cached = read_cache(self.cache_dir, cache_key_val, ttl_days=1) if use_cache and self.cache_dir else None
        if cached:
            logger.info("Using cached ImportYeti results for %s", query)
            return cached

        try:
            if role == "fallback":
                results = self._call_fallback_actor(query, limit=limit, poll_timeout=poll_timeout)
            else:
                results = self._call_apify(query, min_shipments, limit, poll_timeout=poll_timeout)
            if use_cache and self.cache_dir:
                write_cache(self.cache_dir, cache_key_val, results)
            return results
        except Exception as exc:
            if not allow_fallback:
                raise
            logger.warning("Apify ImportYeti failed: %s. Using demo fallback.", exc)
            return self._demo_results(query, min_shipments, limit)

    def keyword_search(
        self,
        query: str,
        country: str = "US",
        min_shipments: int = 5,
        limit: int = 30,
        poll_timeout: int = 120,
    ) -> List[Dict[str, Any]]:
        """Discovery channel: search an Apify actor by product/HS keyword for importers.

        Returns a list of mapped importer dicts (datasource='apify_kw'). Raises on
        any failure (e.g. Apify monthly hard-limit 403) so the caller can fall back
        to the web-search channel — this method never returns demo data.
        """
        if not self.token:
            raise RuntimeError("Apify API token is not configured for keyword discovery")
        actor_id = self.discovery_actor_id
        payload = self._build_discovery_input(query, country, min_shipments, limit)
        run = self._start_actor_run_with_payload(actor_id, payload)
        run_id = run.get("id")
        if not run_id:
            raise RuntimeError("Apify keyword actor did not return a run id")
        run_data = self._poll_run(run_id, max_wait=poll_timeout, actor_id=actor_id)
        dataset_id = run_data.get("defaultDatasetId")
        if not dataset_id:
            raise RuntimeError("Apify keyword run succeeded without a default dataset id")
        raw_items = self._read_dataset_raw(dataset_id, limit)
        rows = [_map_discovery_item(it) for it in raw_items]
        # Keep US importers (companies), drop foreign suppliers.
        rows = [r for r in rows if r.get("company_name") and (r.get("country") or "US").upper() in ("US", "USA")]
        for r in rows:
            r["datasource"] = "apify_kw"
        return rows

    def verify_import(
        self,
        company: str,
        country: str = "US",
        limit: int = 3,
        poll_timeout: int = 120,
    ) -> List[Dict[str, Any]]:
        """Verifier channel: query the BOL actor for a discovered company's import
        records. Used by company_verify, NOT for discovery. Raises on failure."""
        return self._call_fallback_actor(company, limit=limit, poll_timeout=poll_timeout)

    def check_auth(self) -> Dict[str, Any]:
        """Verify Apify authentication without exposing the token."""
        if not self.token:
            raise RuntimeError("Apify API token is not configured")
        url = f"{APFY_BASE}/users/me"
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json().get("data", {})

    def get_actor_metadata(self, actor_id: Optional[str] = None) -> Dict[str, Any]:
        """Fetch configured Actor metadata before starting a bounded run."""
        if not self.token:
            raise RuntimeError("Apify API token is not configured")
        url = f"{APFY_BASE}/acts/{actor_id or self.actor_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json().get("data", {})

    def live_smoke(
        self,
        query: str,
        min_shipments: int = 1,
        limit: int = 1,
        poll_timeout: int = 120,
        actor_role: str = "primary",
    ) -> Dict[str, Any]:
        """Run one strict, bounded live ImportYeti smoke without demo fallback."""
        if limit < 1 or limit > 3:
            raise ValueError("Live smoke limit must be between 1 and 3")

        if actor_role == "fallback":
            return self._live_smoke_fallback_actor(query, limit=limit, poll_timeout=poll_timeout)
        if actor_role != "primary":
            raise ValueError("actor_role must be 'primary' or 'fallback'")

        auth = self.check_auth()
        actor = self.get_actor_metadata(self.actor_id)
        run = self._start_actor_run(query, min_shipments, limit)
        run_id = run.get("id")
        if not run_id:
            raise RuntimeError("Apify did not return a run id")

        run_data = self._poll_run(run_id, max_wait=poll_timeout)
        dataset_id = run_data.get("defaultDatasetId")
        if not dataset_id:
            raise RuntimeError("Apify run succeeded without a default dataset id")

        raw_items = self._read_dataset_raw(dataset_id, limit)
        mapped_items = [_map_item(item) for item in raw_items]
        raw_item_keys = sorted({key for item in raw_items for key in item.keys()})
        return {
            "auth": {"ok": True, "id": auth.get("id")},
            "actor": {
                "id": actor.get("id") or self.actor_id,
                "name": actor.get("name"),
                "title": actor.get("title"),
                "role": "primary",
            },
            "run_id": run_id,
            "run_status": run_data.get("status"),
            "run_status_message": run_data.get("statusMessage"),
            "dataset_id": dataset_id,
            "raw_item_count": len(raw_items),
            "raw_item_keys": raw_item_keys,
            "mapped_company_count": len([item for item in mapped_items if item.get("company_name")]),
            "mapped_items": mapped_items,
        }

    def _live_smoke_fallback_actor(
        self,
        company: str,
        limit: int = 1,
        poll_timeout: int = 120,
    ) -> Dict[str, Any]:
        """Run configured fallback Apify Actor for one company query."""
        if not self.fallback_actor_id:
            raise RuntimeError("Apify fallback_actor_id is not configured")

        auth = self.check_auth()
        actor = self.get_actor_metadata(self.fallback_actor_id)
        run_data, raw_items, mapped_items = self._run_fallback_actor(company, limit, poll_timeout)
        dataset_id = run_data.get("defaultDatasetId")
        raw_item_keys = sorted({key for item in raw_items for key in item.keys()})
        return {
            "auth": {"ok": True, "id": auth.get("id")},
            "actor": {
                "id": actor.get("id") or self.fallback_actor_id,
                "name": actor.get("name"),
                "title": actor.get("title"),
                "role": "fallback",
            },
            "run_id": run_data.get("id"),
            "run_status": run_data.get("status"),
            "run_status_message": run_data.get("statusMessage"),
            "dataset_id": dataset_id,
            "raw_item_count": len(raw_items),
            "raw_item_keys": raw_item_keys,
            "mapped_company_count": len([item for item in mapped_items if item.get("company_name")]),
            "mapped_items": mapped_items,
        }

    def _call_fallback_actor(
        self,
        company: str,
        limit: int,
        poll_timeout: int = 120,
    ) -> List[Dict[str, Any]]:
        """Call configured fallback BOL Actor and return mapped dataset rows."""
        _run_data, _raw_items, mapped_items = self._run_fallback_actor(company, limit, poll_timeout)
        return mapped_items

    def _run_fallback_actor(
        self,
        company: str,
        limit: int,
        poll_timeout: int,
    ) -> tuple[Dict[str, Any], List[Dict[str, Any]], List[Dict[str, Any]]]:
        if not self.fallback_actor_id:
            raise RuntimeError("Apify fallback_actor_id is not configured")
        payload = {"companies": [company], "includeSummary": True, "maxItems": limit}
        run = self._start_actor_run_with_payload(self.fallback_actor_id, payload)
        run_id = run.get("id")
        if not run_id:
            raise RuntimeError("Apify fallback Actor did not return a run id")

        run_data = self._poll_run(run_id, max_wait=poll_timeout, actor_id=self.fallback_actor_id)
        dataset_id = run_data.get("defaultDatasetId")
        if not dataset_id:
            raise RuntimeError("Apify fallback run succeeded without a default dataset id")

        raw_items = self._read_dataset_raw(dataset_id, limit)
        mapped_items = [_map_item(item) for item in raw_items]
        return run_data, raw_items, mapped_items

    def _call_apify(
        self,
        query: str,
        min_shipments: int,
        limit: int,
        poll_timeout: int = 120,
    ) -> List[Dict[str, Any]]:
        run = self._start_actor_run(query, min_shipments, limit)
        run_id = run.get("id")
        if not run_id:
            raise RuntimeError("Apify did not return a run id")

        # Poll for run completion.
        run_data = self._poll_run(run_id, max_wait=poll_timeout)
        dataset_id = run_data.get("defaultDatasetId")
        if not dataset_id:
            raise RuntimeError("Apify run succeeded without a default dataset id")
        return self._read_dataset(dataset_id, limit)

    def _start_actor_run(self, query: str, min_shipments: int, limit: int) -> Dict[str, Any]:
        payload = self._build_actor_input(query, min_shipments, limit)
        return self._start_actor_run_with_payload(self.actor_id, payload)

    def _start_actor_run_with_payload(self, actor_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{APFY_BASE}/acts/{actor_id}/runs"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        logger.info("Calling Apify actor %s", actor_id)
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json().get("data", {})

    def _build_discovery_input(self, query: str, country: str, min_shipments: int, limit: int) -> Dict[str, Any]:
        """Build input for the discovery actor.

        Default is zen-studio/importyeti-scraper (maintained, high-volume), whose
        schema is {query, searchType, type, maxResults, minShipments, mostRecentShipment}.
        Falls back to the legacy searchQueries schema for other configured actors.
        """
        actor = (self.discovery_actor_id or "").lower()
        if "zen-studio" in actor:
            return {
                "query": query,
                "searchType": "search",
                "type": "company",          # US importers/consignees, not foreign suppliers
                "maxResults": limit,
                "minShipments": min_shipments,
                "mostRecentShipment": "12mo",  # active importers only
            }
        return self._build_actor_input(query, min_shipments, limit)

    def _build_actor_input(self, query: str, min_shipments: int, limit: int) -> Dict[str, Any]:
        """Build input using khadinakbar/importyeti-scraper's public schema (legacy)."""
        payload: Dict[str, Any] = {
            "searchQueries": [query],
            "maxResultsPerQuery": limit,
            "minShipments": min_shipments,
        }
        if self.country_code:
            payload["countryCode"] = self.country_code
        if self.type_filter:
            payload["typeFilter"] = self.type_filter
        return payload

    def _poll_run(self, run_id: str, max_wait: int = 120, actor_id: Optional[str] = None) -> Dict[str, Any]:
        url = f"{APFY_BASE}/acts/{actor_id or self.actor_id}/runs/{run_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        start = time.time()
        while time.time() - start < max_wait:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json().get("data", {})
            status = data.get("status")
            if status in {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}:
                if status != "SUCCEEDED":
                    raise RuntimeError(f"Apify run {status}: {data}")
                return data
            time.sleep(2)
        raise RuntimeError("Apify run timed out")

    def _read_dataset(self, dataset_id: str, limit: int) -> List[Dict[str, Any]]:
        return [_map_item(item) for item in self._read_dataset_raw(dataset_id, limit)]

    def _read_dataset_raw(self, dataset_id: str, limit: int) -> List[Dict[str, Any]]:
        url = f"{APFY_BASE}/datasets/{dataset_id}/items"
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"limit": limit, "format": "json", "clean": "true"}
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _demo_results(self, query: str, min_shipments: int, limit: int) -> List[Dict[str, Any]]:
        """Return structurally valid demo candidates ranked by query relevance."""
        q = query.lower()
        query_tokens = [t for t in q.split() if len(t) >= 2]
        filtered = [c for c in DEMO_COMPANIES if c["total_shipments"] >= min_shipments]

        def relevance(c: Dict[str, Any]) -> int:
            score = 0
            desc = c.get("product_description", "").lower()
            name = c["company_name"].lower()
            for token in query_tokens:
                if token in desc:
                    score += 2
                if token in name:
                    score += 1
            return score

        ranked = sorted(filtered, key=relevance, reverse=True)
        results = [dict(c) for c in ranked[:limit]]
        for r in results:
            r["datasource"] = "importyeti_demo"
            r["source_url"] = "https://www.importyeti.com"
            r["recent_shipment_date"] = None
            r["suppliers"] = []
            # Derive plausible scale values for demo/placeholder data
            shipments = r.get("total_shipments") or 0
            r["revenue"] = _estimate_revenue(shipments)
            # Honest field split (demo values are synthetic; label them as proxy).
            r["estimated_shipping_spend"] = _estimate_china_purchase(shipments)
            r["procurement_proxy_notes"] = "Demo estimate, not verified procurement value"
            r["customs_china_purchase"] = None
        return results


def _estimate_revenue(shipments: int) -> str:
    if shipments >= 800:
        return "$50B - $600B"
    if shipments >= 400:
        return "$10B - $50B"
    if shipments >= 200:
        return "$1B - $10B"
    if shipments >= 100:
        return "$500M - $1B"
    return "$100M - $500M"


def _estimate_china_purchase(shipments: int) -> str:
    if shipments >= 800:
        return "$1B - $5B"
    if shipments >= 400:
        return "$500M - $1B"
    if shipments >= 200:
        return "$100M - $500M"
    if shipments >= 100:
        return "$50M - $100M"
    return "$10M - $50M"


def _normalize_hs_codes(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        raw_codes = value
    else:
        raw_codes = str(value).replace("|", ";").replace(",", ";").split(";")
    codes: List[str] = []
    for code in raw_codes:
        text = str(code).strip()
        if text and text not in codes:
            codes.append(text)
    return codes


def _format_usd_amount(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"${amount:,.0f}"


def _shipping_spend_label(item: Dict[str, Any]) -> Optional[str]:
    amount = _format_usd_amount(item.get("est_shipping_spend_usd"))
    if not amount:
        raw_amount = item.get("est_shipping_spend_raw")
        amount = str(raw_amount).strip() if raw_amount not in (None, "") else None
    if not amount:
        return None
    return f"Estimated shipping spend: {amount} (not verified procurement value)"


def _map_discovery_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Map a zen-studio importyeti-scraper search row to our candidate dict.

    Search rows carry name/type/countryCode/address/totalShipments/mostRecentShipment
    (no website or HS codes — those come from domain_resolver + BOL verify downstream).
    """
    name = item.get("name") or item.get("companyName") or item.get("company_name")
    slug = item.get("slug") or item.get("id")
    return {
        "company_name": name,
        "country": item.get("countryCode") or item.get("country") or "US",
        "total_shipments": item.get("totalShipments") or item.get("total_shipments"),
        "recent_shipment_date": item.get("mostRecentShipment") or item.get("recent_shipment_date"),
        "product_description": None,
        "hs_codes": _normalize_hs_codes(item.get("hs_codes") or item.get("hsCodes")),
        "industry_tags": [],
        "website": item.get("website"),
        "source_url": item.get("url") or (f"https://www.importyeti.com/company/{slug}" if slug else "https://www.importyeti.com"),
        "suppliers": [],
        "datasource": "apify_kw",
    }


def _map_item(item: Dict[str, Any]) -> Dict[str, Any]:
    hs_codes = _normalize_hs_codes(item.get("hs_codes"))
    hs_chapters = _normalize_hs_codes(item.get("hs_chapters"))
    return {
        "company_name": item.get("companyName") or item.get("target_name") or item.get("company_name"),
        "country": item.get("countryCode") or item.get("country") or "US",
        "total_shipments": item.get("totalShipments") or item.get("total_shipments"),
        "recent_shipment_date": (
            item.get("mostRecentShipment")
            or item.get("most_recent_shipment_date")
            or item.get("arrival_date")
            or item.get("recentShipmentDate")
            or item.get("recent_shipment_date")
        ),
        "product_description": (
            item.get("productDescription")
            or item.get("product_description")
        ),
        "hs_codes": hs_codes,
        "industry_tags": [f"HS {chapter}" for chapter in hs_chapters],
        # Honest field split: BOL shipping spend is a proxy, never customs procurement value.
        "estimated_shipping_spend": _shipping_spend_label(item),
        "procurement_proxy_notes": (
            "Estimated shipping spend (BOL), not verified customs procurement value"
            if _shipping_spend_label(item) else None
        ),
        "customs_china_purchase": None,  # no verified customs source available this run
        "suppliers": item.get("suppliers", []),
        "source_url": (
            item.get("profileUrl")
            or item.get("target_url")
            or item.get("source_url")
            or item.get("url")
        ),
        "website": item.get("website"),
        "datasource": "importyeti_apify",
    }
