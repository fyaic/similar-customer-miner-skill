"""Social media link helpers."""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("similar_customer_miner")


class SocialTool:
    """Check social media link reachability."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.timeout = config.get("social", {}).get("timeout", 5)

    def check_links(self, links: Dict[str, str]) -> Dict[str, bool]:
        """Return reachability status for each link. Platforms are checked
        concurrently — each check is an independent HEAD/GET request."""
        items = [(platform, url) for platform, url in links.items()]
        if not items:
            return {}
        if len(items) == 1:
            return {items[0][0]: self._reachable(items[0][1])}
        with ThreadPoolExecutor(max_workers=min(4, len(items))) as pool:
            statuses = list(pool.map(lambda item: self._reachable(item[1]), items))
        return {platform: status for (platform, _), status in zip(items, statuses)}

    def _reachable(self, url: Optional[str]) -> bool:
        if not url:
            return False
        try:
            resp = requests.head(url, timeout=self.timeout, allow_redirects=True)
            return resp.status_code < 400
        except Exception:
            try:
                resp = requests.get(url, timeout=self.timeout, allow_redirects=True)
                return resp.status_code < 400
            except Exception:
                return False
