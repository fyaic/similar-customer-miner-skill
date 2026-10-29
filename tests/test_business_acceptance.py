"""Outcome-level acceptance cases, runnable unchanged against rc1 and rc2.

All companies/people are synthetic. Transport is replaced; no real credentials
or network are used. These test selection quality, not supplier coverage.
"""
import pytest
from src import tradewind as tw, scoring
from src.models import CustomerProfile, SimilarCompany


@pytest.fixture
def run_case(tmp_path, monkeypatch):
    monkeypatch.setattr(tw, 'settings', lambda *a: {
        'key': 'acceptance-fixture', 'base': 'https://app.trade-wind.co',
        'insight_prefix': '/api/insight', 'state': str(tmp_path/'state')})

    def run(search=None, detail=None, people=None, verification=None, profiles=None, opts=None, pipeline=None):
        calls = []
        cfg = {'tradewind': {'max_credits': '10', 'max_enrich': 1,
                            'enrich_people': False, 'require_product_match': False, **(opts or {})},
               'pipeline': {'target_countries': ['US'], 'max_results_per_customer': 3, **(pipeline or {})}}
        def send(method, url, body, headers, timeout):
            calls.append((url.rsplit('/', 2)[-2:], body))
            response = {'success': True, 'request_id': 'req_synthetic',
                        'meta': {'billing': {'credits_charged': .24}}}
            if url.endswith('/company/search'):
                response['companies'] = search if search is not None else [{'name': 'Buyer', 'domain': 'buyer.example', 'country': 'US'}]
            elif url.endswith('/company/enrich'):
                response['company'] = detail or {'name': 'Buyer', 'domain': 'buyer.example', 'country': 'US'}
            elif url.endswith('/people/search'):
                response['people'] = people or []
            elif url.endswith('/email/verify'):
                response.update(verification or {})
            else:
                raise AssertionError('Unexpected paid operation '+url)
            return 200, response
        result = tw.mine(profiles or [CustomerProfile(customer_id='seed', customer_name='seed.example', product_tags=['faucet'])],
                         cfg, tmp_path/'output.xlsx', send=send)
        return result, calls, cfg
    return run


def person(name='Pat', title='Procurement Director', email='pat@buyer.example', **extra):
    return {'name': name, 'current_title': title, 'company_domain': 'buyer.example', 'email': email, **extra}


def test_target_country_rechecked_after_detail(run_case):
    rows, calls, _ = run_case(search=[{'name': 'Buyer', 'domain': 'buyer.example'}],
                              detail={'name': 'Buyer', 'domain': 'buyer.example', 'country': 'GB'})
    assert rows == []
    assert all(path != ['people', 'search'] for path, body in calls)


def test_conflicting_country_is_quarantined(run_case):
    rows, _, _ = run_case(detail={'name': 'Buyer', 'domain': 'buyer.example', 'country': 'GB'})
    assert rows == []


def test_procurement_selected_before_hr(run_case):
    rows, _, _ = run_case(people=[person('Hannah', 'HR Manager', 'hr-person@buyer.example'), person()])
    assert rows[0].contact_name == 'Pat'


def test_hr_only_is_not_selected_as_buyer_contact(run_case):
    rows, _, _ = run_case(people=[person('Hannah', 'Human Resources Director')])
    assert rows[0].contact_name is None


def test_procurement_selected_before_executive(run_case):
    rows, _, _ = run_case(people=[person('Chris', 'CEO', 'chris@buyer.example'), person()])
    assert rows[0].contact_name == 'Pat'


@pytest.mark.parametrize('catchall', [None, True])
def test_uncertain_or_catchall_email_not_verified(run_case, catchall):
    rows, _, _ = run_case(people=[person()], opts={'verify_email': True},
        verification={'data': {'email': 'pat@buyer.example', 'status': 'valid', 'is_deliverable': True, 'is_catch_all': catchall}})
    assert rows[0].email_verified is False


def test_documented_verification_response_accepted(run_case):
    rows, _, _ = run_case(people=[person()], opts={'verify_email': True},
        verification={'result': {'email': 'pat@buyer.example', 'status': 'valid', 'is_deliverable': True, 'is_catch_all': False}})
    assert rows[0].email_verified is True


def test_verification_for_other_address_not_attached(run_case):
    rows, _, _ = run_case(people=[person()], opts={'verify_email': True},
        verification={'data': {'email': 'someone@other.example', 'status': 'valid', 'is_deliverable': True, 'is_catch_all': False}})
    assert rows[0].email_verified is False


def test_verification_without_subject_not_attached(run_case):
    rows, _, _ = run_case(people=[person()], opts={'verify_email': True},
        verification={'data': {'status': 'valid', 'is_deliverable': True, 'is_catch_all': False}})
    assert rows[0].email_verified is False


def test_foreign_company_email_not_accepted_on_initial_search(run_case):
    rows, _, _ = run_case(search=[{'name': 'Buyer', 'domain': 'buyer.example', 'country': 'US', 'email': 'sales@other.example'}])
    assert rows[0].email is None


def test_role_mailbox_not_bound_to_named_person(run_case):
    rows, _, _ = run_case(people=[person(email='sales@buyer.example')])
    assert rows[0].contact_name is None


def test_seed_domain_is_excluded(run_case):
    rows, _, _ = run_case(search=[{'name': 'Seed alias', 'domain': 'seed.example'}])
    assert rows == []


def test_missing_country_not_invented(run_case):
    rows, _, _ = run_case(search=[{'name': 'Buyer', 'domain': 'buyer.example'}], opts={'max_enrich': 0})
    assert rows[0].country is None


def test_product_relevance_prioritizes_enrichment(run_case):
    rows, calls, _ = run_case(search=[
        {'name': 'Unrelated', 'domain': 'unrelated.example', 'description': 'Recruitment software', 'country': 'US'},
        {'name': 'Buyer', 'domain': 'buyer.example', 'description': 'Faucet distributor', 'country': 'US'}])
    request = next(body for path, body in calls if path == ['company', 'enrich'])
    assert request['identity']['domains'] == ['buyer.example']


def test_sample_records_not_treated_as_shipping_strength():
    base = SimilarCompany(company_name='Buyer', website='https://buyer.example', fit_score=.2)
    sampled = SimilarCompany(company_name='Buyer', website='https://buyer.example', fit_score=.2,
                             shipment_frequency='100 sampled customs records (not annual frequency)')
    assert scoring._priority_score(sampled) == scoring._priority_score(base)
    assert scoring._freq_bucket(sampled.shipment_frequency) is None


def test_region_scoring_respects_non_us_target():
    assert scoring._region_similarity('GB', ['GB']) > scoring._region_similarity('US', ['GB'])


def test_hybrid_discovery_keeps_anchor_and_product_routes(run_case):
    _, calls, _ = run_case(opts={'discovery_strategy': 'hybrid', 'max_enrich': 0})
    bodies = [b for path, b in calls if path == ['company', 'search']]
    assert any(b.get('similar_to') is True for b in bodies)
    assert any(b['company'].get('keywords') for b in bodies)


def test_all_product_terms_used_with_bounded_query_batches(run_case):
    p = CustomerProfile(customer_id='seed', product_tags=['faucet', 'shower', 'valve', 'plumbing'])
    _, calls, _ = run_case(profiles=[p], opts={'max_enrich': 0})
    terms = {term for path, b in calls if path == ['company', 'search'] for term in b['company'].get('keywords', {}).get('include', [])}
    assert 'plumbing' in terms


def test_no_procurement_value_copied_from_profile(run_case):
    rows, _, _ = run_case()
    assert rows[0].customs_china_purchase is None
    assert rows[0].estimated_shipping_spend is None


@pytest.mark.parametrize('title', ['Executive Editor', 'Director Investor Relations', '', 'Partner Account Manager'])
def test_unrelated_or_unknown_role_not_main_contact(run_case, title):
    rows, _, _ = run_case(people=[person(title=title)])
    assert rows[0].contact_name is None


def test_financial_tools_not_hand_tools(run_case):
    rows, calls, _ = run_case(
        profiles=[CustomerProfile(customer_id='seed', product_tags=['hand tools'])],
        opts={'require_product_match': True},
        detail={'name': 'Buyer', 'domain': 'buyer.example', 'country': 'US',
                'description': 'Financial management tools for consumers.'})
    assert rows == []
    assert all(path != ['people', 'search'] for path, body in calls)


def test_product_missing_stays_out_of_sales_sheet(run_case):
    rows, _, _ = run_case(opts={'require_product_match': True, 'max_enrich': 0})
    assert rows == []


def test_product_match_allows_contact_work(run_case):
    rows, _, _ = run_case(opts={'require_product_match': True}, people=[person()],
        detail={'name': 'Buyer', 'domain': 'buyer.example', 'description': 'Manufacturer of laboratory faucets.', 'country': 'US'})
    assert len(rows) == 1 and rows[0].contact_name == 'Pat'


def test_product_phrase_survives_input_profiling():
    from src.models import Customer
    from src.profiler import profile_customers
    p = profile_customers([Customer(id='seed', main_products='hand tools / ceramic tiles')])[0]
    assert p.product_tags == ['hand tools', 'ceramic tiles']


def test_explicit_power_verification_uses_requested_mode(run_case):
    rows, calls, _ = run_case(people=[person()],
        opts={'verify_email': True, 'email_verification_mode': 'power'},
        verification={'result': {'email': 'pat@buyer.example', 'status': 'catch_all', 'is_deliverable': True, 'is_catch_all': True}})
    request = next(body for path, body in calls if path == ['email', 'verify'])
    assert request['mode'] == 'power'
    assert rows[0].email_verified is False
