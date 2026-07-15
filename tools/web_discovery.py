"""Web-search based buyer discovery.

Discovers candidate US importers/distributors by keyword/HS/industry search,
using a keyless DuckDuckGo HTML endpoint (no SERP API key required). This is
the discovery channel that runs in-process alongside the Apify keyword channel;
it also yields an official website per candidate, which doubles as the domain
source for the downstream Hunter contact lookup.

Design notes:
- No API key needed; runs anywhere `requests` works.
- Aggregator/marketplace/directory domains are filtered out so we keep real
  company sites (the ones that actually have a domain + contacts).
- Every candidate carries a source_url citation and datasource="web_search".
"""
import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs, unquote

import requests

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except Exception:  # pragma: no cover
    _HAS_BS4 = False

logger = logging.getLogger("similar_customer_miner")

DDG_ENDPOINTS = [
    "https://html.duckduckgo.com/html/",
    "https://lite.duckduckgo.com/lite/",
]
BING_ENDPOINT = "https://www.bing.com/search"

# Rotate user agents to reduce keyless-search throttling.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36",
]
DEFAULT_UA = USER_AGENTS[0]


def _pick_ua(seed: int) -> str:
    return USER_AGENTS[seed % len(USER_AGENTS)]

# Domains that are marketplaces / directories / social / reference — NOT the
# buyer's own company site. Excluded so candidates are real importer companies.
AGGREGATOR_DOMAINS = {
    "amazon.com", "ebay.com", "alibaba.com", "aliexpress.com", "made-in-china.com",
    "walmart.com", "etsy.com", "wayfair.com", "homedepot.com", "lowes.com",
    "linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com",
    "youtube.com", "pinterest.com", "reddit.com", "quora.com",
    "wikipedia.org", "wiktionary.org", "britannica.com",
    "importyeti.com", "panjiva.com", "volza.com", "importgenius.com",
    "tradewheel.com", "thomasnet.com", "kompass.com", "zoominfo.com",
    "dnb.com", "bloomberg.com", "crunchbase.com", "yelp.com", "bbb.org",
    "indeed.com", "glassdoor.com", "google.com", "bing.com", "duckduckgo.com",
    "yellowpages.com", "manta.com", "europages.com", "globalsources.com",
    "dhgate.com", "temu.com", "target.com", "costco.com", "ebc.net",
    "trademo.com", "seair.co.in", "exportgenius.in", "eximpedia.com",
    "tridge.com", "statista.com", "ibisworld.com", "medium.com",
    "go4worldbusiness.com", "exporthub.com", "ec21.com", "tradeindia.com",
    "indiamart.com", "hktdc.com", "wikipedia.org",
    # logistics / freight forwarders (not the buyer), news, jobs
    "breakthrubev.com", "flexport.com", "freightos.com", "dhl.com", "fedex.com",
    "ups.com", "maersk.com", "expeditors.com", "chrobinson.com", "shipbob.com",
}

# Whole TLD suffixes that are never a US B2B buyer's own company site.
AGGREGATOR_TLDS = (".gov", ".edu", ".mil", ".int", ".org.cn", ".gov.cn")

# Query templates: US importer/distributor discovery for a given product/HS/industry.
QUERY_TEMPLATES = [
    "{kw} importer United States",
    "{kw} wholesale distributor USA",
    "{kw} supplier importer America company",
]
HS_TEMPLATE = "HS {code} importer United States buyers"


def search_importers(
    profile: Any,
    country: str = "US",
    config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Discover candidate importer companies for one customer profile.

    Returns a list of dicts compatible with buyer_discovery's RawCompany mapping.
    """
    config = config or {}
    disc = config.get("discovery", {})
    max_queries = disc.get("web_max_queries", 4)
    per_query = disc.get("web_results_per_query", 8)
    max_candidates = disc.get("web_max_candidates_per_profile", 20)
    delay = disc.get("web_delay_seconds", 1.0)

    queries = _build_queries(profile, max_queries)
    seen_domains: Dict[str, Dict[str, Any]] = {}

    for query in queries:
        try:
            results = _ddg_search(query, limit=per_query, delay=delay)
        except Exception as exc:
            logger.warning("web_discovery query failed (%s): %s", query, exc)
            continue
        for res in results:
            domain = res["domain"]
            if domain in seen_domains:
                continue
            candidate = {
                "company_name": res["company_name"],
                "country": country,
                "website": res["website"],
                "product_description": None,
                "hs_codes": list(getattr(profile, "hs_codes", []) or []),
                "industry_tags": list(getattr(profile, "industry_tags", []) or []),
                "revenue": None,
                "total_shipments": None,
                "recent_shipment_date": None,
                "suppliers": [],
                "source_url": res["website"],
                "datasource": "web_search",
                "discovery_query": query,
            }
            seen_domains[domain] = candidate
            if len(seen_domains) >= max_candidates:
                break
        if len(seen_domains) >= max_candidates:
            break

    candidates = list(seen_domains.values())
    logger.info("web_discovery: %d candidates from %d queries", len(candidates), len(queries))
    return candidates


def _build_queries(profile: Any, max_queries: int) -> List[str]:
    """Build US-importer search queries from a profile's keywords + HS codes."""
    def _is_english(s: str) -> bool:
        # US-importer web queries only work in English; skip CJK/non-latin terms.
        return bool(s) and all(ord(ch) < 128 for ch in s) and re.search(r"[a-zA-Z]", s) is not None

    keywords: List[str] = []
    for q in (getattr(profile, "search_queries", None) or []):
        s = str(q).strip()
        if re.fullmatch(r"(hs\s*)?\d{2,}", s.lower()):  # bare HS handled by HS template
            continue
        if _is_english(s):
            keywords.append(s)
    if not keywords:  # Chinese product names -> use English industry tags derived by profiler
        keywords = [t for t in (getattr(profile, "industry_tags", []) or []) if _is_english(t)]
    if not keywords:
        keywords = [t for t in (getattr(profile, "product_tags", []) or []) if _is_english(t)]

    queries: List[str] = []
    for kw in keywords[:2]:
        for tmpl in QUERY_TEMPLATES[:2]:
            queries.append(tmpl.format(kw=kw))
    for code in (getattr(profile, "hs_codes", []) or [])[:1]:
        if len(str(code)) >= 4:
            queries.append(HS_TEMPLATE.format(code=code))

    # dedup preserve order
    seen: set = set()
    unique: List[str] = []
    for q in queries:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            unique.append(q)
    return unique[:max_queries] or [f"{kw} importer United States" for kw in keywords[:max_queries]]


def _ddg_search(query: str, limit: int = 8, delay: float = 1.0, retries: int = 3) -> List[Dict[str, str]]:
    """Keyless web search with retry/backoff + UA rotation. Tries DDG (html, lite)
    then Bing as fallback. Treats 403/429 as retryable (throttling)."""
    attempt = 0
    last_exc: Optional[Exception] = None
    for endpoint in DDG_ENDPOINTS:
        for _ in range(retries):
            attempt += 1
            ua = _pick_ua(attempt)
            try:
                resp = requests.post(
                    endpoint,
                    data={"q": query, "kl": "us-en"},
                    headers={"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"},
                    timeout=20,
                )
                if resp.status_code in (403, 429, 503):
                    last_exc = requests.HTTPError(f"{resp.status_code} throttled")
                    time.sleep(delay * (2 ** _) + 0.5 * attempt)  # backoff + jitter
                    continue
                resp.raise_for_status()
                hits = _parse_ddg_html(resp.text, limit)
                time.sleep(delay)
                if hits:
                    return hits
                break  # 200 but no hits -> try next endpoint
            except Exception as exc:
                last_exc = exc
                time.sleep(delay * (2 ** _))
    # Bing fallback
    try:
        return _bing_search(query, limit, delay)
    except Exception as exc:
        last_exc = exc
    if last_exc:
        raise last_exc
    return []


def _bing_search(query: str, limit: int, delay: float) -> List[Dict[str, str]]:
    """Keyless Bing HTML fallback."""
    resp = requests.get(
        BING_ENDPOINT,
        params={"q": query, "cc": "US", "setlang": "en"},
        headers={"User-Agent": _pick_ua(1), "Accept-Language": "en-US,en;q=0.9"},
        timeout=20,
    )
    resp.raise_for_status()
    time.sleep(delay)
    out: List[Dict[str, str]] = []
    seen: set = set()
    if _HAS_BS4:
        soup = BeautifulSoup(resp.text, "html.parser")
        for li in soup.select("li.b_algo h2 a"):
            href = li.get("href") or ""
            title = li.get_text(" ", strip=True)
            domain = _registrable_domain(href)
            if not domain or domain in AGGREGATOR_DOMAINS or _is_aggregator(domain) or domain in seen:
                continue
            seen.add(domain)
            out.append({"company_name": _company_name_from(title, domain),
                        "website": f"https://{domain}", "domain": domain})
            if len(out) >= limit:
                break
    return out


def _parse_ddg_html(html: str, limit: int) -> List[Dict[str, str]]:
    """Extract (title, url) pairs from DuckDuckGo HTML and map to companies."""
    pairs: List[tuple] = []
    if _HAS_BS4:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select("a.result__a, a.result-link"):
            href = a.get("href") or ""
            title = a.get_text(" ", strip=True)
            if href:
                pairs.append((title, href))
        if not pairs:  # lite layout: plain result links in table
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http") and "duckduckgo.com" not in href:
                    pairs.append((a.get_text(" ", strip=True), href))
    else:  # regex fallback
        for m in re.finditer(r'result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
            pairs.append((re.sub(r"<[^>]+>", "", m.group(2)).strip(), m.group(1)))

    out: List[Dict[str, str]] = []
    seen: set = set()
    for title, href in pairs:
        url = _clean_ddg_url(href)
        if not url:
            continue
        domain = _registrable_domain(url)
        if not domain or domain in AGGREGATOR_DOMAINS or _is_aggregator(domain):
            continue
        if domain in seen:
            continue
        seen.add(domain)
        out.append({
            "company_name": _company_name_from(title, domain),
            "website": f"https://{domain}",
            "domain": domain,
        })
        if len(out) >= limit:
            break
    return out


def _clean_ddg_url(href: str) -> Optional[str]:
    """DuckDuckGo wraps target links in /l/?uddg=<encoded>. Unwrap it."""
    if href.startswith("//duckduckgo.com/l/") or "uddg=" in href:
        try:
            qs = parse_qs(urlparse(href if href.startswith("http") else "https:" + href).query)
            if "uddg" in qs:
                return unquote(qs["uddg"][0])
        except Exception:
            return None
    if href.startswith("http"):
        return href
    return None


def _registrable_domain(url: str) -> Optional[str]:
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return None
    if not netloc:
        return None
    netloc = netloc.split(":")[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


def _is_aggregator(domain: str) -> bool:
    # catch subdomains of known aggregators and obvious non-company TLDs
    if domain.endswith(AGGREGATOR_TLDS):
        return True
    for agg in AGGREGATOR_DOMAINS:
        if domain == agg or domain.endswith("." + agg):
            return True
    return False


def _company_name_from(title: str, domain: str) -> str:
    """Derive a readable company name from the result title or domain."""
    if title:
        # strip common suffixes after separators
        name = re.split(r"[\|\-–—:·]| – ", title)[0].strip()
        name = re.sub(r"\b(home|homepage|official site|official website|welcome to)\b", "", name, flags=re.I).strip()
        # reject listing/guide-style titles: commas, too many words, generic category words,
        # or year/guide markers — these are page titles, not company names.
        looks_generic = (
            "," in name
            or len(name.split()) > 5
            or re.search(r"importer|distributor|wholesale|supplier|buyers|guide|\b20\d\d\b|products?$|parts?$", name, re.I)
        )
        if 2 <= len(name) <= 50 and not looks_generic:
            return name
    # fallback: domain -> Title Case (e.g. kingmoreimports -> Kingmore Imports)
    core = domain.rsplit(".", 1)[0].replace("-", " ")
    core = re.sub(r"(imports?|llc|inc|usa|co)$", r" \1", core, flags=re.I).strip()
    return core.title()
