"""OpenCorporates company verification tool."""
import logging
import os
from typing import Any, Dict, Optional

import requests

from src.secret_errors import SecretError, SecretMissingError, raise_for_status_classified
from src.utils import cache_key, read_cache, write_cache

logger = logging.getLogger("similar_customer_miner")

OC_BASE = "https://api.opencorporates.com/v0.4/companies/search"


class OpenCorporatesTool:
    """Tool for verifying company registration."""

    def __init__(self, config: Dict[str, Any], cache_dir: Optional[str] = None):
        self.config = config
        self.token = config.get("opencorporates", {}).get("api_token") or os.getenv("OPENCORPORATES_API_TOKEN")
        self.cache_dir = cache_dir

    def verify(self, company_name: str, country: Optional[str] = None) -> Dict[str, Any]:
        """Search OpenCorporates for a company. Skip if no token configured."""
        if not self.token:
            err = SecretMissingError("opencorporates", env_var="OPENCORPORATES_API_TOKEN")
            logger.debug("OpenCorporates skipped: %s", err)
            return {"verified": False, "error": err.kind}

        cache_key_val = cache_key("opencorporates", company_name, country)
        cached = read_cache(self.cache_dir, cache_key_val, ttl_days=30) if self.cache_dir else None
        if cached:
            return cached

        params: Dict[str, Any] = {"q": company_name, "format": "json", "api_token": self.token}
        if country:
            params["jurisdiction_code"] = _country_to_jurisdiction(country)

        try:
            resp = requests.get(OC_BASE, params=params, timeout=20)
            raise_for_status_classified("opencorporates", resp)
            data = resp.json()
            result = _parse_response(data)
            if self.cache_dir:
                write_cache(self.cache_dir, cache_key_val, result)
            return result
        except SecretError as exc:
            logger.warning("OpenCorporates verify failed for %s: %s", company_name, exc)
            return {"verified": False, "error": exc.kind, "secret_error": exc.to_dict()}
        except Exception as exc:
            logger.warning("OpenCorporates verify failed for %s: %s", company_name, exc)
            return {"verified": False, "error": str(exc)}


def _country_to_jurisdiction(country: str) -> Optional[str]:
    mapping = {"US": "us", "USA": "us", "United States": "us", "GB": "gb", "UK": "gb"}
    return mapping.get(country.upper())


def _parse_response(data: Dict[str, Any]) -> Dict[str, Any]:
    companies = data.get("results", {}).get("companies", [])
    if not companies:
        return {"verified": False, "matches": 0}
    first = companies[0].get("company", {})
    return {
        "verified": True,
        "matches": len(companies),
        "company_name": first.get("name"),
        "company_number": first.get("company_number"),
        "jurisdiction": first.get("jurisdiction_code"),
        "status": first.get("current_status"),
        "registered_address": first.get("registered_address_in_full"),
        "incorporation_date": first.get("incorporation_date"),
        "source_url": first.get("opencorporates_url"),
    }
