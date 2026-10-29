"""Additional invariants for release evidence, privacy and billing boundaries."""
from datetime import datetime, timedelta, timezone
import json
import pytest
from src import tradewind as tw
from src.models import SimilarCompany, CustomerProfile


@pytest.mark.parametrize('age', [8, -1])
def test_mailbox_proof_must_be_fresh_and_not_future(age):
    c = SimilarCompany(email='buyer@example.com')
    tw.apply_verification(c, {'operation_id': 'receipt',
        'observed_at': (datetime.now(timezone.utc)-timedelta(days=age)).isoformat(),
        'response': {'result': {'email': c.email, 'status': 'valid', 'is_deliverable': True, 'is_catch_all': False}}})
    assert c.email_verified is False


def test_verification_citation_separate_from_discovery():
    c = SimilarCompany(email='buyer@example.com', email_citation='search-receipt')
    tw.apply_verification(c, {'operation_id': 'verify-receipt', 'observed_at': datetime.now(timezone.utc).isoformat(),
        'response': {'request_id': 'request-verify', 'result': {
            'email': c.email, 'status': 'valid', 'is_deliverable': True, 'is_catch_all': False}}})
    assert c.email_verified and c.email_citation == 'search-receipt'
    assert 'verify-receipt' in c.email_verification_citation
    assert c.email_verified_at


def test_pending_operation_blocks_different_paid_query(tmp_path, monkeypatch):
    monkeypatch.setattr(tw, 'settings', lambda *a: {'key': 'fixture', 'base': 'https://app.trade-wind.co',
        'insight_prefix': '/api/insight', 'state': str(tmp_path)})
    cfg = {'tradewind': {'max_credits': '5', 'max_enrich': 0}, 'pipeline': {'target_countries': ['US']}}
    calls = []
    def send(*args):
        calls.append(1)
        return 200, {'success': True, 'status': 'pending', 'task_id': 'pending-task', 'meta': {'billing': {'credits_charged': 0}}}
    tw.mine([CustomerProfile(customer_id='one', product_tags=['faucet'])], cfg, tmp_path/'one.xlsx', send)
    tw.mine([CustomerProfile(customer_id='two', product_tags=['packaging'])], cfg, tmp_path/'two.xlsx', send)
    assert len(calls) == 1
    assert cfg['_run_stats']['tradewind']['stop_reason']


def test_hs_only_rejected_before_creating_session(monkeypatch):
    monkeypatch.setattr(tw, 'settings', lambda *a: pytest.fail('Credentials loaded before input validation'))
    with pytest.raises(ValueError, match='HS-only'):
        tw.mine([CustomerProfile(customer_id='hs', hs_codes=['8481'])], {}, 'unused.xlsx')


def test_trade_wind_report_uses_its_own_stats(tmp_path):
    from src.exporter import export_results
    from scripts.run_report import main
    output = tmp_path/'empty.xlsx'
    export_results([], str(output), {})
    output.with_suffix('.stats.json').write_text(json.dumps({'mode': 'live', 'tradewind': {
        'candidate_count': 0, 'discovered_candidates': 3, 'product_unconfirmed_count': 3,
        'new_credits_known': '.48', 'reused_requests': 1, 'budget': {'unresolved_operations': 0}}}))
    assert main([str(output)]) == 0
    report = output.with_name('empty_run_report.md').read_text()
    assert 'Trade Wind' in report and '.48' in report
    assert 'apify=' not in report and 'BOL 验证' not in report
