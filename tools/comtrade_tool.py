"""UN Comtrade macro market filter tool."""
import logging
import os
from typing import Any, Dict, List, Optional

import requests

from src.secret_errors import SecretError, SecretMissingError, raise_for_status_classified
from src.utils import cache_key, read_cache, write_cache

logger = logging.getLogger("similar_customer_miner")

COMTRADE_URL = "https://comtradeapi.un.org/data/v1/get/C/A/2023/{}"


class ComtradeTool:
    """Tool for macro market size queries."""

    def __init__(self, config: Dict[str, Any], cache_dir: Optional[str] = None):
        self.config = config
        self.subscription_key = (
            config.get("comtrade", {}).get("subscription_key")
            or os.getenv("COMTRADE_SUBSCRIPTION_KEY")
            or ""
        )
        self.cache_dir = cache_dir

    def get_market_size(self, hs_code: str, reporter: str = "842", years: int = 1) -> List[Dict[str, Any]]:
        """Return top importing markets for an HS code."""
        if not self.subscription_key:
            err = SecretMissingError("comtrade", env_var="COMTRADE_SUBSCRIPTION_KEY")
            logger.debug("UN Comtrade skipped: %s", err)
            return []

        # MVP: query US imports from China for the HS chapter
        hs_short = hs_code[:4] if len(hs_code) >= 4 else hs_code
        cache_key_val = cache_key("comtrade", hs_short, reporter, years)
        cached = read_cache(self.cache_dir, cache_key_val, ttl_days=7) if self.cache_dir else None
        if cached:
            return cached

        try:
            results = self._call_comtrade(hs_short, reporter)
            if self.cache_dir:
                write_cache(self.cache_dir, cache_key_val, results)
            return results
        except SecretError as exc:
            logger.warning("UN Comtrade call failed for HS %s: %s", hs_code, exc)
            return []
        except Exception as exc:
            logger.warning("UN Comtrade call failed for HS %s: %s", hs_code, exc)
            return []

    def _call_comtrade(self, hs_code: str, reporter: str) -> List[Dict[str, Any]]:
        url = COMTRADE_URL.format(hs_code)
        headers = {}
        if self.subscription_key:
            headers["Ocp-Apim-Subscription-Key"] = self.subscription_key
        params = {"reporterCode": reporter, "partnerCode": "156", "flowCode": "1"}
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        raise_for_status_classified("comtrade", resp)
        data = resp.json()
        dataset = data.get("dataset", [])
        results = []
        for item in dataset:
            results.append({
                "reporter": item.get("reporterDesc"),
                "partner": item.get("partnerDesc"),
                "hs_code": item.get("cmdCode"),
                "trade_value_usd": item.get("primaryValue"),
                "weight_kg": item.get("netWgt"),
                "year": item.get("period"),
            })
        return results
