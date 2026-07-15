"""Simple web scraper for company websites."""
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("similar_customer_miner")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SimilarCustomerMiner/1.0)"}

SOCIAL_PATTERNS = {
    "linkedin": r'linkedin\.com/company/[^\s"<>]+',
    "facebook": r'facebook\.com/[^\s"<>]+',
    "twitter": r'twitter\.com/[^\s"<>]+',
    "youtube": r'youtube\.com/[^\s"<>]+',
}


class WebScraper:
    """Scrape company websites for contacts and social links."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.timeout = config.get("web_scraper", {}).get("timeout", 15)
        self.retries = config.get("web_scraper", {}).get("retries", 2)
        self.delay = config.get("web_scraper", {}).get("delay_seconds", 1.0)
        self.headers = config.get("web_scraper", {}).get("user_agent", HEADERS["User-Agent"])

    def scrape(self, url: str) -> Dict[str, Any]:
        """Scrape a single URL and extract structured data."""
        url = _normalize_url(url)
        if not url:
            return {"reachable": False, "error": "invalid url"}

        for attempt in range(self.retries + 1):
            try:
                resp = requests.get(url, headers={"User-Agent": self.headers}, timeout=self.timeout)
                resp.raise_for_status()
                return self._extract(resp.text, url)
            except Exception as exc:
                logger.warning("Scrape attempt %d failed for %s: %s", attempt + 1, url, exc)
                if attempt < self.retries:
                    import time
                    time.sleep(self.delay)
        return {"reachable": False, "error": "request failed"}

    def _extract(self, html: str, base_url: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n", strip=True)

        emails = self._extract_emails(text)
        phones = self._extract_phones(text)
        social = self._extract_social(text, base_url)
        description = self._extract_description(soup)

        return {
            "reachable": True,
            "url": base_url,
            "title": soup.title.get_text(strip=True) if soup.title else None,
            "description": description,
            "emails": emails,
            "phones": phones,
            "social": social,
            "text": text[:5000],
        }

    def _extract_emails(self, text: str) -> List[str]:
        pattern = r'[\w.-]+@[\w.-]+\.\w+'
        found = set(re.findall(pattern, text))
        return list(sorted(e.lower() for e in found if "example" not in e.lower() and "test" not in e.lower()))

    def _extract_phones(self, text: str) -> List[str]:
        pattern = r'[\+]?[1-9][\d\s\-\(\)]{8,}'
        found = set(re.findall(pattern, text))
        cleaned = []
        for phone in found:
            digits = re.sub(r"\D", "", phone)
            if len(digits) >= 10:
                cleaned.append(phone.strip())
        return cleaned

    def _extract_social(self, text: str, base_url: str) -> Dict[str, str]:
        social: Dict[str, str] = {}
        for platform, pattern in SOCIAL_PATTERNS.items():
            matches = re.findall(pattern, text)
            if matches:
                social[platform] = urljoin(base_url, matches[0])
        return social

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        # Try meta description
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"].strip()
        # Fallback to first paragraph
        for p in soup.find_all("p"):
            text = p.get_text(strip=True)
            if len(text) > 50:
                return text
        return None


def _normalize_url(url: str) -> Optional[str]:
    url = str(url).strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        return None
    return url
