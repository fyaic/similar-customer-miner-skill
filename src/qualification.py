"""Product evidence and business-role hints, separate from buyer qualification.

Official-page reviews are supplied by the operator/agent. This module validates
their scope and provenance; it never claims to fetch or authenticate a page.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit


def tokens(text):
    words = re.findall(r'\w+', unicodedata.normalize('NFKC', str(text)).lower())
    return [w[:-1] if len(w) > 3 and w.endswith('s') and not w.endswith(('ss', 'us', 'is')) else w for w in words]


def phrase_in(phrase, text):
    query, words = tokens(phrase), tokens(text)
    return bool(query) and any(words[i:i+len(query)] == query for i in range(len(words)-len(query)+1))


def positive_phrase(phrase, text):
    # Negated/ambiguous sentences require review rather than automatic acceptance.
    return any(phrase_in(phrase, sentence) and not re.search(
        r"\b(no|not|never|without|discontinued|ceased)\b|n't\b|不再|不销售", sentence.lower())
        for sentence in re.split(r'[.!?;\n。；]', text))


def variants(tag, aliases):
    return [tag, *next((v for k, v in aliases.items() if tokens(k) == tokens(tag)), [])]


def validate_aliases(aliases):
    if not isinstance(aliases, dict) or len(aliases) > 100:
        raise ValueError('product_aliases must be a mapping with at most 100 products')
    for key, values in aliases.items():
        if not isinstance(key, str) or not tokens(key) or not isinstance(values, list) or len(values) > 10 or any(
                not isinstance(v, str) or not tokens(v) or len(v) > 150 for v in values):
            raise ValueError('product_aliases values must be lists of up to 10 nonempty phrases')


def host(value):
    return (urlsplit(value if '://' in value else 'https://'+value).hostname or '').lower().removeprefix('www.').rstrip('.')


def load_reviews(path, aliases):
    if not path:
        return {}
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict) or data.get('schema_version') != 1 or not isinstance(data.get('reviews'), list):
        raise ValueError('Product evidence requires schema_version=1 and reviews list')
    reviews = {}
    for item in data['reviews']:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k].strip() for k in
                ['seed_id', 'domain', 'product', 'decision', 'source_url', 'excerpt', 'checked_at', 'reviewer', 'reason']):
            raise ValueError('Product review is missing required provenance fields')
        url = urlsplit(item['source_url'])
        if url.scheme != 'https' or url.username or url.password or host(item['domain']) != host(item['source_url']):
            raise ValueError('Product evidence must cite HTTPS on the exact company domain')
        checked = datetime.fromisoformat(item['checked_at'])
        if checked.tzinfo is None or not 0 <= (datetime.now(timezone.utc)-checked).total_seconds() <= 90*86400:
            raise ValueError('Product evidence must be timezone-aware and within the past 90 days')
        if item['decision'] not in {'relevant', 'unrelated'}:
            raise ValueError('Product review decision must be relevant or unrelated')
        if item['decision'] == 'relevant' and not any(positive_phrase(v, item['excerpt']) for v in variants(item['product'], aliases)):
            raise ValueError('Positive product review needs a supporting product phrase in the excerpt')
        key = (item['seed_id'], host(item['domain']), tuple(tokens(item['product'])))
        if key in reviews:
            raise ValueError('Duplicate/conflicting product reviews for the same seed/domain/product')
        reviews[key] = item
    return reviews


def assess_product(company, profile, aliases=None, reviews=None):
    aliases, reviews = aliases or {}, reviews or {}
    if not profile.product_tags:
        return 'anchor_only', 'Company-anchor discovery; no product target supplied', None
    # Reviewed decisions apply only to the exact seed/domain/product. All target
    # products must be explicitly rejected before excluding a multi-product buyer.
    negative = []
    for tag in profile.product_tags:
        review = reviews.get((profile.customer_id, host(company.website or ''), tuple(tokens(tag))))
        if review:
            if review['decision'] == 'relevant':
                return 'reviewed_match', review['reason'], review
            negative.append(review)
    text = ' '.join([company.main_products or '', *company.industry_tags])
    for tag in profile.product_tags:
        if any(tokens(r['product']) == tokens(tag) for r in negative):
            continue
        for i, phrase in enumerate(variants(tag, aliases)):
            if positive_phrase(phrase, text):
                return ('matched' if i == 0 else 'matched_alias'), 'Provider text contains: '+phrase, None
    if len(negative) == len(profile.product_tags):
        return 'reviewed_unrelated', '; '.join(r['reason'] for r in negative), negative[0]
    return 'needs_review', 'Product evidence missing or ambiguous; absence is not proof of irrelevance', None


def apply_assessment(company, profile, aliases=None, reviews=None):
    status, reason, review = assess_product(company, profile, aliases, reviews)
    company.product_match_status = status
    company.product_match_reason = reason
    company.product_evidence_citation = review['source_url'] if review else company.main_products_citation or company.industry_tags_citation
    company.product_evidence_checked_at = review['checked_at'] if review else None
    company.product_evidence_reviewer = review['reviewer'] if review else None
    company.product_evidence_excerpt = review['excerpt'] if review else None
    return status


def apply_business_role(company):
    text = ' '.join([company.main_products or '', *company.industry_tags])
    roles = []
    for label, pattern in [('distributor', r'\bdistributor\w*\b'), ('wholesaler', r'\bwholesal\w*\b'),
                           ('retailer', r'\bretail\w*\b'), ('manufacturer', r'\bmanufactur\w*\b'),
                           ('importer_claim', r'\bimporter\w*\b')]:
        if any(re.search(pattern, sentence, re.I) and not re.search(
                r"\b(no|not|never|without|discontinued|ceased)\b|n't\b", sentence, re.I)
                for sentence in re.split(r'[.!?;\n]', text)):
            roles.append(label)
    company.business_role = ', '.join(roles) or 'unknown'
    company.business_role_citation = (company.main_products_citation or company.industry_tags_citation) if roles else None
    company.buyer_qualification = 'unverified'  # A business-role word is not buying intent or import proof.
