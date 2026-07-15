"""Email discovery and validation helpers."""
import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("similar_customer_miner")

GENERIC_EMAIL_LOCAL_PARTS = {
    "admin",
    "contact",
    "customerservice",
    "hello",
    "help",
    "info",
    "inquiries",
    "orders",
    "sales",
    "service",
    "support",
}


def is_generic_email(email: str) -> bool:
    """Return True for department/generic mailbox addresses."""
    local = (email or "").split("@", 1)[0].strip().lower()
    return local in GENERIC_EMAIL_LOCAL_PARTS


class EmailTool:
    """Discover and validate emails."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.hunter_key = config.get("hunter", {}).get("api_key") or os.getenv("HUNTER_API_KEY")

    def infer_pattern(self, domain: str, known_emails: List[str]) -> Optional[str]:
        """Infer email pattern from known emails for a domain."""
        if not known_emails:
            return None
        local_parts = [e.split("@")[0] for e in known_emails if "@" in e and e.split("@")[1].lower() == domain.lower()]
        if not local_parts:
            return None
        # Simple first/last name heuristics
        patterns = set()
        for lp in local_parts:
            parts = re.split(r"[._-]", lp)
            if len(parts) == 2:
                patterns.add("{first}.{last}")
            elif len(parts) == 1:
                patterns.add("{first}")
        return list(patterns)[0] if patterns else None

    def format_email(self, email: str) -> Optional[str]:
        """Normalize and validate email format."""
        if not email:
            return None
        email = email.strip().lower()
        if re.match(r'^[\w.-]+@[\w.-]+\.\w+$', email):
            return email
        return None

    def validate_format(self, email: str) -> bool:
        return self.format_email(email) is not None

    def hunter_domain_search(self, domain: str) -> List[str]:
        """Search Hunter.io for domain emails."""
        contacts = self.hunter_domain_contacts(domain)
        return [contact["email"] for contact in contacts if contact.get("email")]

    def hunter_domain_contacts(self, domain: str) -> List[Dict[str, Any]]:
        """Search Hunter.io for structured domain email records."""
        if not self.hunter_key:
            return []
        try:
            url = "https://api.hunter.io/v2/domain-search"
            params = {"domain": domain, "api_key": self.hunter_key}
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            contacts: List[Dict[str, Any]] = []
            for email_data in data.get("data", {}).get("emails", []):
                email = email_data.get("value")
                if not email:
                    continue
                contacts.append(
                    {
                        "email": email,
                        "first_name": email_data.get("first_name"),
                        "last_name": email_data.get("last_name"),
                        "position": email_data.get("position"),
                        "confidence": email_data.get("confidence"),
                        "source": "hunter",
                    }
                )
            return contacts
        except Exception as exc:
            logger.warning("Hunter.io domain search failed: %s", exc)
            return []


def domain_from_url(url: Optional[str]) -> Optional[str]:
    """Extract domain from URL or email domain string."""
    if not url:
        return None
    match = re.search(r'([\w.-]+\.\w+)', str(url))
    if not match:
        return None
    domain = match.group(1).lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain
