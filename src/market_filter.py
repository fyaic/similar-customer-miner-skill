"""Macro market filter using UN Comtrade."""
import logging
from typing import Any, Dict, List

from src.models import CustomerProfile
from src.utils import get_cache_dir
from tools.comtrade_tool import ComtradeTool

logger = logging.getLogger("similar_customer_miner")


def rank_markets(profiles: List[CustomerProfile], config: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Rank top import markets by HS code. Limited to a few representative codes in MVP."""
    tool = ComtradeTool(config, cache_dir=get_cache_dir(config))
    results: Dict[str, List[Dict[str, Any]]] = {}

    # Collect unique HS4 codes up to a limit
    unique_hs: List[str] = []
    seen: set = set()
    for profile in profiles:
        for hs in profile.hs_codes:
            hs4 = hs[:4] if len(hs) >= 4 else hs
            if hs4 not in seen:
                seen.add(hs4)
                unique_hs.append(hs4)
    unique_hs = unique_hs[:5]

    for hs in unique_hs:
        try:
            data = tool.get_market_size(hs)
            results[hs] = data
        except Exception as exc:
            logger.warning("Market filter failed for HS %s: %s", hs, exc)
            results[hs] = []
    return results
