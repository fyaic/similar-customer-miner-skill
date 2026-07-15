"""Validate emails, phones, and social links."""
import logging
from typing import Any, Dict, List

from src.models import SimilarCompany
from tools.email_tool import EmailTool
from tools.social_tool import SocialTool

logger = logging.getLogger("similar_customer_miner")


def validate_companies(companies: List[SimilarCompany], config: Dict[str, Any]) -> List[SimilarCompany]:
    """Validate contact information for each company."""
    email_tool = EmailTool(config)
    social_tool = SocialTool(config)

    for company in companies:
        # Email format validation
        if company.email:
            normalized = email_tool.format_email(company.email)
            if normalized:
                company.email = normalized
                company.email_confidence = max(company.email_confidence, 0.6)
            else:
                company.email_confidence = 0.2
        else:
            company.email_confidence = 0.0

        # Social reachability recheck for non-demo data; demo static links are trusted.
        is_demo = company.notes and "importyeti_demo" in company.notes
        if not is_demo:
            links = {
                "linkedin": company.linkedin,
                "facebook": company.facebook,
                "twitter": company.twitter,
                "youtube": company.youtube,
            }
            reachable = social_tool.check_links(links)
            for platform, url in links.items():
                if not url:
                    continue
                conf_attr = f"{platform}_confidence"
                citation_attr = f"{platform}_citation"
                if reachable.get(platform):
                    setattr(company, conf_attr, min(0.9, getattr(company, conf_attr, 0.0) + 0.15))
                else:
                    setattr(company, conf_attr, 0.2)
                    current_citation = getattr(company, citation_attr)
                    if current_citation:
                        setattr(company, citation_attr, f"{current_citation} (unreachable)")

    return companies
