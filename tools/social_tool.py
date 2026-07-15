"""Social media link helpers."""
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("similar_customer_miner")


class SocialTool:
    """Check social media link reachability."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def check_links(self, links: Dict[str, str]) -> Dict[str, bool]:
        """Return reachability status for each link."""
        results = {}
        for platform, url in links.items():
            results[platform] = self._reachable(url)
        return results

    def _reachable(self, url: Optional[str]) -> bool:
        if not url:
            return False
        try:
            resp = requests.head(url, timeout=10, allow_redirects=True)
            return resp.status_code < 400
        except Exception:
            try:
                resp = requests.get(url, timeout=10, allow_redirects=True)
                return resp.status_code < 400
            except Exception:
                return False
