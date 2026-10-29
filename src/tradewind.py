"""Trade Wind discovery and enrichment feeding the existing scoring/export model.

Only this path runs in live mode. No legacy credentials, BYOK, or automatic retry.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from src.models import SimilarCompany
from src import scoring
from src.utils import normalize_company_name
from src.tradewind_core.api import Client, estimate, prepare
from src.tradewind_core.security import settings, private_json, redact
from src.tradewind_core.store import Store, credits


def domain(value):
    if not isinstance(value, str) or not value.strip():
        return ''
    value = value.strip()
    parsed = urlparse(value if '://' in value else 'https://' + value)
    host = (parsed.hostname or '').lower().removeprefix('www.').rstrip('.')
    return host if '.' in host and not any(c.isspace() for c in host) else ''


def iso_country(value):
    value = str(value or '').strip().upper()
    return {'USA': 'US', 'UNITED STATES': 'US', 'UNITED STATES OF AMERICA': 'US',
            'UK': 'GB', 'UNITED KINGDOM': 'GB', 'CHINA': 'CN', 'CANADA': 'CA'}.get(value, value)


def unpack(payload, key):
    """Accept documented top-level and data-enveloped responses, never recursive guesses."""
    data = payload.get(key)
    if data is None and isinstance(payload.get('data'), dict):
        data = payload['data'].get(key)
    if isinstance(data, dict):
        return [data]
    return [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []


def company_profile(row):
    return {**row, **(row.get('profile') if isinstance(row.get('profile'), dict) else {})}


def company_domain(row):
    p = company_profile(row)
    return domain(p.get('primary_domain') or p.get('domain') or p.get('website_url') or p.get('website'))


def citation(result):
    p = result.get('response', {})
    return 'Trade Wind; request_id=' + str(p.get('request_id') or 'unavailable') + '; operation=' + result['operation_id']


def put(company, field, value, source, confidence=.65):
    if value is None or value == '' or value == []:
        return
    setattr(company, field, value)
    setattr(company, field + '_citation', source)
    setattr(company, field + '_confidence', confidence)
    company.all_citations[field] = source


def note(company, text):
    if text not in (company.notes or ''):
        company.notes = '; '.join(filter(None, [company.notes, text]))


def emails(row):
    result = []
    values = row.get('emails') or ([row['email']] if row.get('email') else [])
    if isinstance(values, str):
        values = [values]
    for value in values:
        email = value.get('email') or value.get('value') if isinstance(value, dict) else value
        if isinstance(email, str) and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
            result.append(email.lower())
    return list(dict.fromkeys(result))


def generic(email):
    return email.split('@')[0].lower() in {'info','sales','contact','support','hello','admin','office','orders','service','hr','careers','jobs','billing','accounting','noreply','no-reply'}


def apply_company(company, row, source):
    p = company_profile(row)
    current = domain(company.website)
    incoming = company_domain(row)
    if current and incoming and current != incoming:
        note(company, 'Company domain conflict; enrichment retained in evidence, not merged')
        return False
    name = p.get('name') or p.get('company_name')
    if company.company_name and name and normalize_company_name(name) != normalize_company_name(company.company_name):
        note(company, 'Provider company name differs; original name retained: ' + str(name))
    elif not company.company_name:
        put(company, 'company_name', name, source)
    if incoming and not company.website:
        put(company, 'website', 'https://' + incoming, source)
    hq = p.get('hq') if isinstance(p.get('hq'), dict) else {}
    location = p.get('location') if isinstance(p.get('location'), dict) else {}
    country = iso_country(hq.get('country_code') or hq.get('country') or location.get('country_code') or p.get('country_code') or p.get('country'))
    if company.country and country and iso_country(company.country) != country:
        note(company, 'Country conflict; original country retained: ' + country)
    elif country:
        put(company, 'country', country, source)
    put(company, 'region', hq.get('state') or hq.get('city'), source)
    put(company, 'main_products', p.get('description') or p.get('short_description'), source)
    industries = p.get('industries') or p.get('industry')
    if isinstance(industries, str):
        industries = [industries]
    if isinstance(industries, list):
        put(company, 'industry_tags', [x for x in industries if isinstance(x, str)], source)
    if p.get('annual_revenue') is not None:
        value = p['annual_revenue']
        put(company, 'revenue', json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else str(value), source, .5)
        note(company, 'Revenue is a provider estimate; currency/period require review')
    for field in ('linkedin','facebook','twitter','youtube'):
        social = p.get('social_links') or {}
        value = social.get(field+'_url') or social.get(field) if isinstance(social, dict) else None
        if isinstance(value, str) and value.startswith(('http://','https://')):
            put(company, field, value, source, .5)
    found = [e for e in emails(p) if (current or incoming) and domain(e.split('@')[-1]) == (current or incoming)]
    if found and not company.email:
        put(company, 'email', found[0], source, .5)
        note(company, 'Company email channel; not a verified person or verified mailbox')
    phones = p.get('phones') or []
    if phones and not company.phone:
        first = phones[0]
        value = first.get('number') if isinstance(first, dict) else first
        if isinstance(value, str):
            put(company, 'phone', value, source, .5)
    return True


def person_identity(person):
    name = person.get('name') or person.get('full_name') or ' '.join(str(person.get(k) or '') for k in ('first_name','last_name')).strip()
    return name if isinstance(name, str) else ''


def person_matches(person, company):
    pd = domain(person.get('company_domain') or person.get('company_website'))
    cd = domain(company.website)
    pn = person.get('company_name') or person.get('current_employer')
    if pd and cd:
        return pd == cd
    return bool(pn and normalize_company_name(str(pn)) == normalize_company_name(company.company_name))


def role_rank(person):
    """Title heuristics prioritize relevant candidates, never certify authority."""
    title = str(person.get('current_title') or person.get('title') or person.get('position') or '').lower()
    if re.search(r'\b(hr|human resources|recruit\w*|talent|marketing|sales|accountant|finance|investor relations|editor|journalist|writer|legal|engineer\w*)\b', title):
        return -1
    if re.search(r'\b(procure\w*|purchas\w*|sourcing|buyer|buying|supply chain|import\w*|merchandis\w*)\b|采购|供应链', title):
        return 3
    if re.search(r'\b(operations|logistics)\b|运营|物流', title):
        return 2
    if re.search(r'\b(ceo|coo|president|owner|founder|managing director|general manager|executive director)\b|总经理', title):
        return 1
    return 0


def apply_person(company, person, source):
    # Empty Hunter rows and organization channels cannot become named decision-makers.
    if not person_matches(person, company):
        note(company, 'Person/company association missing or conflicting; not merged')
        return False
    rank = role_rank(person)
    if rank <= 0:
        note(company, 'Non-buying or unknown role retained in raw evidence, not selected as main contact')
        return False
    name = person_identity(person)
    personal_emails = [e for e in emails(person) if not generic(e) and domain(e.split('@')[-1]) == domain(company.website)]
    if not name:
        note(company, 'Empty person identity excluded; see raw evidence')
        return False
    if not personal_emails:
        note(company, 'Named person lacks matching personal work email; retained in evidence without binding company email')
        return False
    company.contact_role_fit = True if rank >= 2 else None
    note(company, 'Contact role: '+('procurement/operations title match; authority unverified' if rank >= 2 else 'executive fallback; buying role unverified' if rank == 1 else 'unknown; manual role review required'))
    put(company, 'contact_name', name, source, .6)
    put(company, 'contact_title', person.get('current_title') or person.get('title') or person.get('position'), source, .6)
    email_status = 'unknown'
    for item in person.get('emails') or []:
        if isinstance(item, dict) and str(item.get('email') or item.get('value') or '').lower() == personal_emails[0]:
            email_status = str(item.get('status') or 'unknown').lower()
    put(company, 'email', personal_emails[0], source, .35 if email_status in {'guessed','inferred'} else .6)
    note(company, 'Provider email status: '+email_status+'; not independently verified')
    note(company, 'Candidate person; current employment, decision authority and deliverability require review')
    return True


class Session:
    def __init__(self, config, send=None):
        self.config = config
        cfg = config.get('tradewind', {})
        self.settings = settings(cfg.get('env_file'))
        if not self.settings['key']:
            raise ValueError('Missing TRADEWIND_API_KEY; internal package must retain .credentials/')
        namespace = hashlib.sha256(self.settings['key'].encode()).hexdigest()[:16]
        self.store = Store(cfg.get('state_dir') or self.settings['state'], namespace)
        self.store.set_budget(cfg.get('max_credits', '2'))
        self.client = Client(self.settings, self.store, **({'send': send} if send else {}))
        self.events = []
        self.stop_reason = None
        self.reused = 0
        self.new_credits = Decimal(0)

    def call(self, name, body):
        if self.stop_reason:
            return None
        if redact(body) != body:
            raise ValueError('BYOK/credentials are not accepted in request bodies')
        spec = prepare(name, body)
        digest = hashlib.sha256(json.dumps([name, spec['body']], sort_keys=True).encode()).hexdigest()
        # Cache exact queries for this account. Unknown requests keep the same ID across days.
        rows = self.store.db.execute('SELECT * FROM operations WHERE fingerprint=? ORDER BY created DESC',
            (hashlib.sha256(json.dumps([spec['method'],spec['path'],spec['body'],{}],sort_keys=True,allow_nan=False).encode()).hexdigest(),)).fetchall()
        op_id = None
        ttl = self.config.get('tradewind', {}).get('cache_days', 7)
        for row in rows:
            age = (datetime.now(timezone.utc)-datetime.fromisoformat(row['created'])).total_seconds()/86400
            if row['state'] != 'completed' or not row['billing_known'] or age < ttl:
                op_id = row['id'];break
        op_id = op_id or 'miner:'+digest[:24]+':'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
        try:
            result = self.client.call(name, body, op_id, timeout=45)
        except ValueError as exc:
            self.stop_reason = str(exc)
            self.events.append({'operation':name,'state':'deferred','reason':str(exc)})
            return None
        saved = self.store.get(result['operation_id'])
        result['observed_at'] = saved['created'] if saved else None
        self.events.append({'operation':name, **result})
        if result.get('reused'):
            self.reused += 1
        elif result.get('credits') is not None:
            self.new_credits += Decimal(result['credits'])
        if result['state'] != 'completed':
            self.stop_reason = 'Operation '+op_id+' is '+result['state']+'; inspect billing before retry'
            return None
        return result

    def report(self):
        return {'provider':'tradewind','new_credits_known':str(self.new_credits),
                'reused_requests':self.reused,'budget':self.store.budget(),'stop_reason':self.stop_reason,
                'operations':self.events,'warning':'Local planning budget, not provider hard cap; results are unreviewed candidates'}


def product_match(company, profile):
    """Conservative textual corroboration; no import/buyer inference from a hit."""
    if not profile.product_tags:
        return 'anchor_only'
    text = ' '.join([company.main_products or '', *company.industry_tags]).lower()
    if not text.strip():
        return 'unknown'
    normalize = lambda word: word[:-1] if len(word) > 3 and word.endswith('s') else word
    words = {normalize(w) for w in re.findall(r'[\w]+', text)}
    for tag in profile.product_tags:
        tokens = {normalize(w) for w in re.findall(r'[\w]+', tag.lower())}
        if tokens and tokens <= words:
            return 'matched'
    return 'unconfirmed'


def target_countries(cfg):
    countries = list(dict.fromkeys(iso_country(x) for x in cfg.get('pipeline',{}).get('target_countries',['US'])))
    if not countries or any(not re.fullmatch('[A-Z]{2}', x) for x in countries):
        raise ValueError('target_countries must contain ISO2 codes')
    return countries


def discovery_requests(profile, cfg, limit):
    opts = cfg.get('tradewind', {})
    anchor = profile.customer_name or profile.industry_leader
    strategy = opts.get('discovery_strategy', 'keywords')
    cap = int(opts.get('max_discovery_queries', 2))
    bodies = []
    if profile.product_tags and strategy != 'similar':
        terms = list(dict.fromkeys(profile.product_tags))
        for offset in range(0, len(terms), 3):
            bodies.append({'company': {'keywords': {'include': terms[offset:offset+3]}}, 'similar_to': False})
    if anchor and (not bodies or strategy == 'hybrid'):
        d = domain(anchor)
        anchor_body = {'company': {'domains' if d else 'names': [d or anchor]}, 'similar_to': True}
        # In hybrid mode reserve a slot for the anchor rather than silently drop it.
        bodies = [*bodies[:max(0, cap-1)], anchor_body] if bodies else [anchor_body]
    if not bodies:
        if profile.hs_codes:
            raise ValueError('HS-only input needs product keywords or a company anchor; customs verification does not discover buyers')
        raise ValueError('Seed needs a company name/domain, industry leader, or product keywords')
    countries = target_countries(cfg)
    return [{**body, 'location': {'country_code': countries}, 'page': 1, 'per_page': min(100, limit),
             'waterfall': {'mode': 'first_match', 'source_order': ['hunter']}} for body in bodies[:cap]]


def discovery_body(profile, cfg, limit):
    """Compatibility helper; preview/mine use the complete bounded request list."""
    return discovery_requests(profile, cfg, limit)[0]


def apply_verification(company, verified):
    payload = verified['response']
    data = payload.get('result') or payload.get('data') or {}
    if not isinstance(data, dict):
        data = {}
    subject_matches = str(data.get('email') or '').strip().lower() == str(company.email or '').lower()
    checked_at = verified.get('observed_at')
    fresh = False
    if checked_at:
        age = (datetime.now(timezone.utc)-datetime.fromisoformat(checked_at)).total_seconds()
        fresh = 0 <= age <= 7*86400
    company.email_verification_status = str(data.get('status') or 'unknown') if subject_matches else 'subject_mismatch'
    company.email_verified = bool(subject_matches and fresh and data.get('status') == 'valid'
        and data.get('is_deliverable') is True and data.get('is_catch_all') is False)
    company.email_verification_citation = citation(verified)
    company.email_verified_at = checked_at
    if company.email_verified:
        company.email_confidence = .85
    elif subject_matches and data.get('status') == 'invalid':
        company.email_confidence = .1
    note(company, 'Mailbox check: '+company.email_verification_status+'; catch_all='+str(data.get('is_catch_all'))+'; does not verify employment')


def mine(profiles, config, output_path, send=None):
    """Discover new companies, enrich bounded candidates, preserve partial deliverables."""
    opts = config.get('tradewind', {})
    limit = int(config.get('pipeline', {}).get('max_results_per_customer', 10))
    if not 1 <= limit <= 100:
        raise ValueError('max_results_per_customer must be 1..100')
    # Validate before creating any paid operations.
    validate_options(opts)
    bodies = [(p, body) for p in profiles for body in discovery_requests(p, config, limit)]
    # Scores must use the actual requested market, not the profiler's legacy US default.
    from dataclasses import replace
    scoring_profiles = [replace(p, target_regions=target_countries(config)) for p in profiles]
    session = Session(config, send)
    companies = []
    excluded = {normalize_company_name(n) for p in profiles for n in [p.customer_name,p.industry_leader,*p.seed_exclude_names] if n}
    excluded_domains = {domain(n) for p in profiles for n in [p.customer_name,p.industry_leader,*p.seed_exclude_names] if domain(n)}
    names, domains = set(), set()
    stats = {'excluded_seed':0,'duplicates':0,'country_mismatch':0,'identity_missing':0}
    try:
        for profile, body in bodies:
            result = session.call('company.search', body)
            if not result:
                break
            for row in unpack(result['response'], 'companies'):
                p = company_profile(row)
                name = p.get('name') or p.get('company_name')
                if not isinstance(name,str) or not name.strip():
                    stats['identity_missing'] += 1;continue
                nk, dk = normalize_company_name(name), company_domain(row)
                if nk in excluded or dk and dk in excluded_domains:
                    stats['excluded_seed'] += 1;continue
                if nk in names or dk and dk in domains:
                    stats['duplicates'] += 1;continue
                company = SimilarCompany(source_seed=profile.customer_id,source_seed_confidence=1,
                    source_seed_citation='Input customer profile '+profile.customer_id,
                    all_citations={'datasource':'tradewind','source_url':'https://app.trade-wind.co/api/company/search','request_id':result['response'].get('request_id','')},
                    notes='Trade Wind candidate; company existence and buyer qualification require review')
                apply_company(company, row, citation(result))
                if company.country and iso_country(company.country) not in body['location']['country_code']:
                    stats['country_mismatch'] += 1;continue
                if not company.country:
                    note(company,'Country missing from API response; requested country filter is not independent evidence')
                names.add(nk)
                if dk: domains.add(dk)
                companies.append(company)
        scoring.score_companies(companies, scoring_profiles, config)
        # Bound each seed after merging discovery routes, then spend enrichment on fit.
        selected = []
        for company in sorted(companies, key=lambda c: -c.fit_score):
            if sum(c.source_seed == company.source_seed for c in selected) < limit:
                selected.append(company)
        companies = selected
        quarantined = []
        profile_by_id = {p.customer_id: p for p in profiles}
        enriched_ids = set()
        for company in companies[:int(opts.get('max_enrich', 5))]:
            d = domain(company.website)
            if not d:
                note(company,'No reliable domain; contact enrichment skipped')
                continue
            detail = session.call('company.enrich',{'identity':{'domains':[d]},'waterfall':{'mode':'first_match','source_order':['hunter']}})
            if detail:
                enriched_ids.add(id(company))
                for row in unpack(detail['response'],'company'):
                    apply_company(company,row,citation(detail))
            if (company.country and iso_country(company.country) not in target_countries(config)) or 'Country conflict' in (company.notes or '') or 'Company domain conflict' in (company.notes or ''):
                stats['country_mismatch'] += 1
                quarantined.append({'company': company.company_name, 'reason': company.notes, 'source': company.all_citations})
                continue
            company.product_match_status = product_match(company, profile_by_id[company.source_seed])
            if opts.get('require_product_match', True) and company.product_match_status in {'unknown', 'unconfirmed'}:
                note(company, 'Product relevance not corroborated; contact enrichment skipped')
                continue
            if opts.get('customs_enabled') and not session.stop_reason:
                verify_customs(company, session, opts)
            result = session.call('people.search',{'company':{'domains':[d]},'page':1,'per_page':5,
                'waterfall':{'mode':'first_match','source_order':[opts.get('people_source','hunter')]}})
            if result:
                person_enrich_used = 0
                for person in sorted(unpack(result['response'],'people'), key=role_rank, reverse=True):
                    if role_rank(person) <= 0:
                        note(company, 'Non-buying or unknown role retained in raw evidence, not selected as main contact')
                        continue
                    if not person_matches(person,company) or not person_identity(person):
                        apply_person(company,person,citation(result));continue
                    if apply_person(company,person,citation(result)):
                        break
                    identity = enrich_identity(person, company)
                    if opts.get('enrich_people',True) and identity and person_enrich_used < 1:
                        person_enrich_used += 1
                        enriched = session.call('people.enrich',{'identity':identity,
                            'waterfall':{'mode':'first_match','source_order':[opts.get('people_source','hunter')],'reveal_phone':False}})
                        if enriched:
                            for row in unpack(enriched['response'],'person'):
                                apply_person(company,row,citation(enriched))
                        if company.contact_name:
                            break
            if opts.get('verify_email',False) and company.email:
                verified = session.call('email.verify',{'type':'single','mode':opts.get('email_verification_mode', 'quick'),'email':company.email})
                if verified:
                    apply_verification(company, verified)
            if session.stop_reason:
                break
        discovered_count = len(companies)
        product_unconfirmed = 0
        for company in companies:
            company.product_match_status = product_match(company, profile_by_id[company.source_seed])
            if opts.get('require_product_match', True) and company.product_match_status in {'unknown', 'unconfirmed'}:
                product_unconfirmed += 1
                quarantined.append({'company': company.company_name, 'reason': 'Product relevance '+company.product_match_status,
                                    'source': company.all_citations})
        deferred_count = sum(id(c) not in enriched_ids for c in companies)
        rejected = {item['company'] for item in quarantined}
        companies = [c for c in companies if c.company_name not in rejected]
        report = session.report()
        report['quarantined'] = quarantined
        report['enriched_companies'] = len(enriched_ids)
        report['role_matched_contacts'] = sum(c.contact_role_fit is True for c in companies)
        report['discovery_requests_planned'] = len(bodies)
        report['discovered_candidates'] = discovered_count
        report['product_unconfirmed_count'] = product_unconfirmed
        report['qualification'] = 'Product text corroboration only; import activity and procurement authority remain unverified'
        report['discovery'] = stats
        report['candidate_count'] = len(companies)
        report['enrichment_deferred_count'] = deferred_count
        report['named_contacts'] = sum(bool(c.contact_name) for c in companies)
        report['verified_mailboxes'] = sum(c.email_verified for c in companies)
        evidence_path = Path(output_path).with_suffix('.evidence.json')
        private_json(evidence_path, report)
        config.setdefault('_run_stats',{})['tradewind'] = {k:v for k,v in report.items() if k not in {'operations', 'quarantined'}}
        config['_run_stats']['evidence_file'] = str(evidence_path)
        for company in companies:
            if not company.hs_codes:
                note(company,'Import/HS/procurement evidence unavailable; similarity is not proof of China imports')
        return companies
    finally:
        session.store.close()


def validate_options(opts):
    if opts.get('email_verification_mode', 'quick') not in {'quick', 'power'}:
        raise ValueError('email_verification_mode must be quick or power')
    if opts.get('discovery_strategy', 'keywords') not in {'keywords', 'similar', 'hybrid'}:
        raise ValueError('discovery_strategy must be keywords, similar, or hybrid')
    if not 1 <= int(opts.get('max_discovery_queries', 2)) <= 4:
        raise ValueError('max_discovery_queries must be 1..4')
    if opts.get('people_source', 'hunter') not in {'hunter','apollo','rocketreach'}:
        raise ValueError('people_source must be hunter, apollo, or rocketreach')
    if not 0 <= int(opts.get('max_enrich',5)) <= 100:
        raise ValueError('max_enrich must be 0..100')
    if not 0 <= float(opts.get('cache_days',7)) <= 30:
        raise ValueError('cache_days must be 0..30')
    if opts.get('customs_enabled'):
        from datetime import date
        start = date.fromisoformat(opts.get('customs_start',''))
        end = date.fromisoformat(opts.get('customs_end',''))
        if start > end:
            raise ValueError('customs_start must precede customs_end')
        if not opts.get('customs_importer_country') or not opts.get('customs_exporter_country'):
            raise ValueError('Customs requires provider country IDs from customs.reference.countries')


def verify_customs(company, session, opts):
    body = {'start_time':opts['customs_start'],'end_time':opts['customs_end'],'product':'',
        'buyer':company.company_name,'importer_country':str(opts['customs_importer_country']),
        'exporter_country':str(opts['customs_exporter_country']), 'recordType':'Import','limit':10,'page':1}
    result = session.call('customs.search',body)
    if not result:
        return
    # Query matching is fuzzy upstream. Only evidence tied to this exact buyer is accepted.
    matched = {}
    for record in unpack(result['response'],'records'):
        buyer = record.get('buyer') or {}
        name = buyer.get('name') or record.get('importer_company_name')
        bd = company_domain(buyer)
        if not (bd and bd == domain(company.website)) and normalize_company_name(name) != normalize_company_name(company.company_name):
            continue
        key = record.get('snow_flake_id') or record.get('id') or json.dumps(record,sort_keys=True)
        matched[key] = record
    if not matched:
        note(company,'No exact buyer match in customs sample; import status remains unknown')
        return
    codes = sorted({str(r.get('hs_code')).strip() for r in matched.values() if r.get('hs_code')})
    put(company,'hs_codes',codes,citation(result),.7)
    put(company,'shipment_frequency',f"{len(matched)} sampled customs records ({opts['customs_start']} to {opts['customs_end']}; not annual frequency)",citation(result),.6)
    note(company,'Matched customs sample; amount, currency and full-year procurement not inferred')


def preview(profiles, config, max_results=None):
    opts = config.get('tradewind',{})
    validate_options(opts)
    limit = max_results or config.get('pipeline',{}).get('max_results_per_customer',10)
    if not 1 <= limit <= 100:
        raise ValueError('max_results_per_customer must be 1..100')
    requests = []
    for profile in profiles:
        for body in discovery_requests(profile,config,limit):
            requests.append({'seed':profile.customer_id,'operation':'company.search','body':body,
                             'reserve':str(estimate(prepare('company.search',body)))})
    return {'mode':'preview','network_calls':0,'requests':requests,
            'max_credits':str(opts.get('max_credits','2')),'max_enrich':opts.get('max_enrich',5),
            'next_steps':'Company details, optional customs, people search, identity-based people enrich, optional email verification',
            'warning':'Dependent requests use discovered identities; budget is a local planning limit, not provider hard cap'}


def enrich_identity(person, company):
    if not person_matches(person,company) or not person_identity(person):
        return None
    if person.get('source') and person.get('source_id'):
        return {'source':person['source'],'source_id':str(person['source_id'])}
    if person.get('first_name') and person.get('last_name') and domain(company.website):
        return {'first_name':person['first_name'],'last_name':person['last_name'],
                'domain':domain(company.website),'company_name':company.company_name}
    linkedin = person.get('linkedin_url') or (person.get('social_links') or {}).get('linkedin_url')
    if linkedin:
        return {'linkedin':linkedin,'domain':domain(company.website)}
    return None
