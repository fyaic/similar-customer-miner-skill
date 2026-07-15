"""Deduplicate and merge similar companies."""
import logging
from typing import Any, Dict, List

from rapidfuzz import fuzz

from src.models import SimilarCompany
from src.utils import normalize_company_name

logger = logging.getLogger("similar_customer_miner")


def deduplicate_companies(companies: List[SimilarCompany], threshold: float = 90.0) -> List[SimilarCompany]:
    """Deduplicate companies by normalized name fuzzy matching."""
    if not companies:
        return []

    clusters: List[List[SimilarCompany]] = []
    for company in companies:
        norm = normalize_company_name(company.company_name)
        if not norm:
            clusters.append([company])
            continue

        matched = False
        for cluster in clusters:
            cluster_norm = normalize_company_name(cluster[0].company_name)
            if cluster_norm and fuzz.ratio(norm, cluster_norm) >= threshold:
                cluster.append(company)
                matched = True
                break
        if not matched:
            clusters.append([company])

    merged: List[SimilarCompany] = []
    for cluster in clusters:
        merged.append(_merge_cluster(cluster))

    logger.info("Deduplicated %d companies into %d unique", len(companies), len(merged))
    return merged


def _merge_cluster(cluster: List[SimilarCompany]) -> SimilarCompany:
    """Merge a cluster of duplicate companies into one record."""
    base = cluster[0]
    if len(cluster) == 1:
        return base

    best = SimilarCompany(**base.__dict__)
    all_citations: Dict[str, Any] = dict(base.all_citations or {})

    for other in cluster[1:]:
        if other.email and (not best.email or other.email_confidence > best.email_confidence):
            best.email = other.email
            best.email_confidence = other.email_confidence
            best.email_citation = other.email_citation
        if other.phone and (not best.phone or other.phone_confidence > best.phone_confidence):
            best.phone = other.phone
            best.phone_confidence = other.phone_confidence
            best.phone_citation = other.phone_citation
        if other.website and not best.website:
            best.website = other.website
        if other.linkedin and not best.linkedin:
            best.linkedin = other.linkedin
        if other.facebook and not best.facebook:
            best.facebook = other.facebook
        if other.twitter and not best.twitter:
            best.twitter = other.twitter
        if other.youtube and not best.youtube:
            best.youtube = other.youtube
        if other.shipment_frequency and (not best.shipment_frequency or _parse_shipments(other.shipment_frequency) > _parse_shipments(best.shipment_frequency)):
            best.shipment_frequency = other.shipment_frequency
            best.shipment_frequency_confidence = other.shipment_frequency_confidence
            best.shipment_frequency_citation = other.shipment_frequency_citation
        all_citations.update(other.all_citations or {})

    best.all_citations = all_citations
    return best


def _parse_shipments(text: str) -> int:
    import re
    match = re.search(r"\d+", text or "")
    return int(match.group()) if match else 0
