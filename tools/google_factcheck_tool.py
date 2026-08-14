"""Google Fact Check Tools API client.

This tool searches fact-checking organizations' published reviews for a given
query. It is used as a lightweight, free secondary check for high-value claims
about candidate companies (e.g. revenue figures).
"""
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests

from src.secret_errors import SecretError, SecretMissingError, raise_for_status_classified
from src.utils import cache_key, read_cache, write_cache

logger = logging.getLogger("similar_customer_miner")

BASE_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"


class GoogleFactCheckTool:
    """Client for Google Fact Check Tools API."""

    def __init__(self, config: Dict[str, Any], cache_dir: Optional[Union[str, Path]] = None):
        self.config = config
        self.api_key = (
            config.get("google", {}).get("fact_check_api_key")
            or os.getenv("GOOGLE_FACT_CHECK_API_KEY")
        )
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.timeout = config.get("google", {}).get("timeout", 15)

    def search_claims(
        self,
        query: str,
        language: str = "en",
        page_size: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search fact-checked claims matching the query.

        Returns a list of claimReview items. Each item contains:
        - text: the claim text
        - claimant: who made the claim
        - claimDate: when the claim was made
        - claimReview: list of reviews with publisher, url, textualRating, etc.
        """
        if not self.api_key:
            err = SecretMissingError("google", env_var="GOOGLE_FACT_CHECK_API_KEY")
            logger.debug("Google Fact Check skipped: %s", err)
            return []

        if not query or not query.strip():
            return []

        cache_key_val = cache_key("google_factcheck", query, language, page_size)
        cached = read_cache(self.cache_dir, cache_key_val, ttl_days=7) if self.cache_dir else None
        if cached is not None:
            logger.debug("Using cached Google Fact Check results for: %s", query)
            return cached

        try:
            results = self._call_api(query, language, page_size)
            if self.cache_dir:
                write_cache(self.cache_dir, cache_key_val, results)
            return results
        except SecretError as exc:
            logger.warning("Google Fact Check API call failed: %s", exc)
            return []
        except Exception as exc:
            logger.warning("Google Fact Check API call failed: %s", exc)
            return []

    def _call_api(
        self,
        query: str,
        language: str,
        page_size: int,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "query": query,
            "languageCode": language,
            "pageSize": max(1, min(page_size, 50)),
            "key": self.api_key,
        }
        logger.info("Calling Google Fact Check API for query: %s", query)
        resp = requests.get(BASE_URL, params=params, timeout=self.timeout)
        raise_for_status_classified("google", resp)
        data = resp.json()
        claims = data.get("claims", [])
        # Flatten reviews for easier consumption
        flattened: List[Dict[str, Any]] = []
        for claim in claims:
            for review in claim.get("claimReview", []):
                flattened.append({
                    "claim_text": claim.get("text"),
                    "claimant": claim.get("claimant"),
                    "claim_date": claim.get("claimDate"),
                    "publisher": review.get("publisher", {}).get("name"),
                    "publisher_site": review.get("publisher", {}).get("site"),
                    "review_url": review.get("url"),
                    "review_title": review.get("title"),
                    "review_date": review.get("reviewDate"),
                    "textual_rating": review.get("textualRating"),
                    "language": review.get("languageCode"),
                })
        return flattened

    def check_company_claim(
        self,
        company_name: str,
        claim: str,
        language: str = "en",
    ) -> List[Dict[str, Any]]:
        """Convenience method to search for a specific claim about a company."""
        query = f"{company_name} {claim}".strip()
        return self.search_claims(query, language=language, page_size=5)
