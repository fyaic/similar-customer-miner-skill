"""Generate customer profiles from Customer objects."""
import logging
import re
from typing import Dict, List, Optional

from src.models import Customer, CustomerProfile
from src.utils import bucket_number, clean_text, split_values

logger = logging.getLogger("similar_customer_miner")


def profile_customers(customers: List[Customer]) -> List[CustomerProfile]:
    """Generate profiles for all customers."""
    return [_profile_one(c) for c in customers]


def _profile_one(customer: Customer) -> CustomerProfile:
    hs_codes = customer.hs_codes or []
    hs_chapters = list({code[:2] for code in hs_codes if len(code) >= 2})

    product_tags = _extract_product_tags(customer.main_products)
    industry_tags = _infer_industry_tags(hs_codes, product_tags)
    regions, channels = _parse_region_positioning(customer.region_positioning)

    profile = CustomerProfile(
        customer_id=customer.id,
        customer_name=customer.name,
        industry_tags=industry_tags,
        product_tags=product_tags,
        hs_codes=hs_codes,
        hs_chapters=hs_chapters,
        target_regions=regions,
        target_channels=channels,
        scale_bucket=bucket_number(customer.customer_revenue) or bucket_number(customer.leader_revenue),
        shipment_freq_bucket=_bucket_frequency(customer.annual_shipment_frequency),
        purchase_bucket=bucket_number(customer.annual_china_purchase),
        value_route=_classify_value_route(customer.business_positioning),
        search_queries=_build_search_queries(customer, product_tags, hs_codes),
        industry_leader=customer.industry_leader,
        seed_exclude_names=_seed_exclude_names(customer),
    )
    return profile


def _seed_exclude_names(customer: Customer) -> List[str]:
    """Names that must not appear as 'similar new buyers' (they are the seeds)."""
    names: List[str] = []
    for raw in (customer.name, customer.industry_leader):
        if raw:
            names.append(str(raw))
    if customer.local_competitors:
        names.extend(split_values(customer.local_competitors, separators=["/", ",", ";", "|", "、", "，"]))
    return [n.strip() for n in names if n and n.strip()]


def _extract_product_tags(text: Optional[str]) -> List[str]:
    if not text:
        return []
    # Split by common separators and keep meaningful tokens
    parts = split_values(text, separators=["/", ",", ";", "|", "、", "，"])
    tags: List[str] = []
    for part in parts:
        part = re.sub(r"[^\w\s-]", "", part).strip().lower()
        if len(part) >= 2:
            tags.append(part)
    return tags


def _infer_industry_tags(hs_codes: List[str], product_tags: List[str]) -> List[str]:
    tags: set = set()
    # HS chapter hints
    chapter_map = {
        "39": "plastics",
        "61": "apparel",
        "62": "apparel",
        "63": "textiles",
        "64": "footwear",
        "69": "ceramics",
        "73": "steel/hardware",
        "74": "copper",
        "76": "aluminum",
        "82": "tools",
        "83": "hardware",
        "84": "machinery",
        "85": "electronics",
        "87": "vehicles",
        "94": "furniture",
        "95": "toys",
        "96": "daily necessities",
    }
    for code in hs_codes:
        chapter = code[:2]
        if chapter in chapter_map:
            tags.add(chapter_map[chapter])
    # Keyword hints
    keyword_map = {
        "shower": "bathroom/sanitary",
        "faucet": "bathroom/sanitary",
        "tile": "building materials",
        "ceramic": "building materials",
        "toy": "toys",
        "textile": "textiles",
        "fabric": "textiles",
        "garden": "gardening",
        "bag": "bags/luggage",
        "appliance": "home appliances",
        "kitchen": "kitchenware",
        "hardware": "hardware",
        "machinery": "machinery",
    }
    for tag in product_tags:
        for keyword, industry in keyword_map.items():
            if keyword in tag:
                tags.add(industry)
    return list(tags)


def _parse_region_positioning(text: Optional[str]) -> tuple[List[str], List[str]]:
    if not text:
        return ["US"], []
    text_lower = str(text).lower()
    regions: List[str] = ["US"]
    channels: List[str] = []
    if "全美" in text_lower or "nationwide" in text_lower or "whole" in text_lower:
        regions.append("nationwide")
    if "加州" in text_lower or "california" in text_lower or "ca" in text_lower:
        regions.append("California")
    if "佛州" in text_lower or "florida" in text_lower or "fl" in text_lower:
        regions.append("Florida")
    if "德州" in text_lower or "texas" in text_lower or "tx" in text_lower:
        regions.append("Texas")
    if "纽约" in text_lower or "new york" in text_lower:
        regions.append("New York")
    if "渠道" in text_lower or "channel" in text_lower:
        channels.append("distributor")
    if "商超" in text_lower or "retail" in text_lower:
        channels.append("retail")
    if "电商" in text_lower or "e-commerce" in text_lower or "online" in text_lower:
        channels.append("e-commerce")
    return regions, channels


def _bucket_frequency(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).lower()
    match = re.search(r"\d+", text)
    if not match:
        return clean_text(value)
    num = int(match.group())
    if "月" in text or "month" in text:
        num = num * 12
    if num >= 100:
        return "高频(100+/年)"
    if num >= 50:
        return "中高频(50-100/年)"
    if num >= 20:
        return "中频(20-50/年)"
    if num >= 5:
        return "低频(5-20/年)"
    return "极低频(<5/年)"


def _classify_value_route(text: Optional[str]) -> str:
    if not text:
        return "mixed"
    text_lower = str(text).lower()
    if "价值" in text_lower or "value" in text_lower or "高端" in text_lower:
        return "value"
    if "规模" in text_lower or "volume" in text_lower or "便宜" in text_lower or "低价" in text_lower:
        return "volume"
    return "mixed"


def _build_search_queries(
    customer: Customer,
    product_tags: List[str],
    hs_codes: List[str],
) -> List[str]:
    """Build ImportYeti-style search queries."""
    queries: List[str] = []

    # Product keyword queries
    if customer.main_products:
        main = clean_text(customer.main_products)
        if main:
            queries.append(main)
            parts = split_values(main, separators=["/", ",", ";", "|", "、"])
            for part in parts[:3]:
                queries.append(part.strip())

    # Tag-based queries
    for tag in product_tags[:3]:
        queries.append(tag)

    # HS-based queries
    for code in hs_codes[:2]:
        if len(code) >= 4:
            queries.append(f"hs {code}")
        queries.append(code)

    # Deduplicate while preserving order
    seen: set = set()
    unique: List[str] = []
    for q in queries:
        key = q.lower()
        if key not in seen and len(q) >= 2:
            seen.add(key)
            unique.append(q)
    return unique[:6]
