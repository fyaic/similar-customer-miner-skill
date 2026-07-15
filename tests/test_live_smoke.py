import json
from unittest.mock import Mock, patch

import pytest

from scripts import live_smoke
from tools.importyeti_tool import ImportYetiTool, _map_item


def _response(payload):
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


@patch("tools.importyeti_tool.requests.post")
@patch("tools.importyeti_tool.requests.get")
def test_importyeti_live_smoke_success_maps_dataset(mock_get, mock_post):
    mock_post.return_value = _response({"data": {"id": "run-1"}})
    mock_get.side_effect = [
        _response({"data": {"id": "user-1"}}),
        _response({"data": {"id": "actor-1", "name": "importyeti"}}),
        _response({"data": {"status": "SUCCEEDED", "defaultDatasetId": "dataset-1"}}),
        _response(
            [
                {
                    "companyName": "Acme Supply",
                    "country": "US",
                    "totalShipments": 7,
                    "productDescription": "shower faucet parts",
                }
            ]
        ),
    ]
    tool = ImportYetiTool({"apify": {"api_token": "test-token", "actor_id": "actor-1"}})

    result = tool.live_smoke("shower faucet", limit=1, poll_timeout=1)

    assert result["run_status"] == "SUCCEEDED"
    assert result["raw_item_count"] == 1
    assert result["mapped_company_count"] == 1
    assert "companyName" in result["raw_item_keys"]
    assert result["mapped_items"][0]["company_name"] == "Acme Supply"
    assert mock_post.call_args.kwargs["json"] == {
        "searchQueries": ["shower faucet"],
        "maxResultsPerQuery": 1,
        "minShipments": 1,
        "countryCode": "US",
        "typeFilter": "company",
    }


def test_importyeti_actor_input_uses_public_schema_keys():
    tool = ImportYetiTool(
        {
            "apify": {
                "api_token": "test-token",
                "country_code": "US",
                "type_filter": "company",
            }
        }
    )

    payload = tool._build_actor_input("shower faucet", min_shipments=1, limit=3)

    assert payload == {
        "searchQueries": ["shower faucet"],
        "maxResultsPerQuery": 3,
        "minShipments": 1,
        "countryCode": "US",
        "typeFilter": "company",
    }


@patch("tools.importyeti_tool.requests.post")
@patch("tools.importyeti_tool.requests.get")
def test_importyeti_fallback_live_smoke_uses_configured_actor(mock_get, mock_post):
    mock_post.return_value = _response({"data": {"id": "run-1"}})
    mock_get.side_effect = [
        _response({"data": {"id": "user-1"}}),
        _response({"data": {"id": "fallback-actor", "name": "importyeti-bol"}}),
        _response(
            {
                "data": {
                    "status": "SUCCEEDED",
                    "statusMessage": "Finished! Total 1 requests: 1 succeeded, 0 failed.",
                    "defaultDatasetId": "dataset-1",
                }
            }
        ),
        _response(
            [
                {
                    "target_name": "APPLE INC",
                    "target_url": "https://www.importyeti.com/company/apple",
                    "total_shipments": 10,
                    "hs_codes": ["8517", "8542"],
                    "hs_chapters": ["85"],
                    "product_description": "consumer electronics",
                    "est_shipping_spend_usd": 12345,
                }
            ]
        ),
    ]
    tool = ImportYetiTool(
        {
            "apify": {
                "api_token": "test-token",
                "actor_id": "primary-actor",
                "fallback_actor_id": "fallback-actor",
            }
        }
    )

    result = tool.live_smoke("apple", limit=1, poll_timeout=1, actor_role="fallback")

    assert result["actor"]["role"] == "fallback"
    assert result["mapped_company_count"] == 1
    assert result["mapped_items"][0]["company_name"] == "APPLE INC"
    assert result["mapped_items"][0]["hs_codes"] == ["8517", "8542"]
    assert result["mapped_items"][0]["industry_tags"] == ["HS 85"]
    assert result["mapped_items"][0]["estimated_shipping_spend"] == (
        "Estimated shipping spend: $12,345 (not verified procurement value)"
    )
    assert "not verified customs procurement value" in result["mapped_items"][0]["procurement_proxy_notes"]
    assert result["mapped_items"][0]["customs_china_purchase"] is None
    assert mock_post.call_args.args[0].endswith("/acts/fallback-actor/runs")
    assert mock_post.call_args.kwargs["json"] == {
        "companies": ["apple"],
        "includeSummary": True,
        "maxItems": 1,
    }


def test_importyeti_map_item_preserves_fallback_business_fields():
    mapped = _map_item(
        {
            "target_name": "APPLE INC",
            "target_url": "https://www.importyeti.com/company/apple",
            "total_shipments": 12,
            "most_recent_shipment_date": "2026-01-01",
            "product_description": "consumer electronics",
            "hs_codes": "8517; 8542",
            "hs_chapters": ["85"],
            "est_shipping_spend_usd": 9876.5,
        }
    )

    assert mapped["company_name"] == "APPLE INC"
    assert mapped["source_url"] == "https://www.importyeti.com/company/apple"
    assert mapped["product_description"] == "consumer electronics"
    assert mapped["hs_codes"] == ["8517", "8542"]
    assert mapped["industry_tags"] == ["HS 85"]
    assert mapped["estimated_shipping_spend"] == "Estimated shipping spend: $9,876 (not verified procurement value)"
    assert mapped["customs_china_purchase"] is None
    assert "not verified customs procurement value" in mapped["procurement_proxy_notes"]


def test_importyeti_strict_search_does_not_use_demo_fallback(monkeypatch):
    tool = ImportYetiTool({"apify": {"api_token": "test-token"}})
    monkeypatch.setattr(tool, "_call_apify", Mock(side_effect=RuntimeError("actor failed")))
    monkeypatch.setattr(tool, "_demo_results", Mock(side_effect=AssertionError("demo fallback used")))

    with pytest.raises(RuntimeError, match="actor failed"):
        tool.search("shower faucet", limit=1, allow_fallback=False, use_cache=False)


def test_importyeti_search_can_use_fallback_actor(monkeypatch):
    tool = ImportYetiTool({"apify": {"api_token": "test-token", "actor_role": "fallback"}})
    fallback = Mock(return_value=[{"company_name": "APPLE INC"}])
    monkeypatch.setattr(tool, "_call_fallback_actor", fallback)

    results = tool.search("Apple", limit=1, allow_fallback=False, use_cache=False)

    assert results == [{"company_name": "APPLE INC"}]
    fallback.assert_called_once_with("Apple", limit=1, poll_timeout=120)


def test_live_smoke_summary_filename_includes_actor_role_and_run_id(tmp_path):
    path = live_smoke._write_summary(
        {"actor_role": "fallback", "run_id": "run-123", "status": "ok"},
        str(tmp_path),
    )

    assert path.name.startswith("live_smoke_fallback_run-123_")
    assert path.exists()


def test_live_smoke_script_reports_empty_dataset(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        live_smoke.config_loader,
        "load_config",
        lambda config_path=None, load_local=True: {"apify": {"api_token": "test-token"}},
    )
    monkeypatch.setattr(
        live_smoke.ImportYetiTool,
        "live_smoke",
        lambda self, query, min_shipments=1, limit=1, poll_timeout=120, actor_role="primary": {
            "auth": {"ok": True},
            "actor": {"id": "actor-1", "name": "importyeti", "title": None, "role": actor_role},
            "run_id": "run-1",
            "run_status": "SUCCEEDED",
            "run_status_message": "Done. Pushed 0 records to default dataset.",
            "dataset_id": "dataset-1",
            "raw_item_count": 0,
            "raw_item_keys": [],
            "mapped_company_count": 0,
        },
    )

    exit_code = live_smoke.main(["--output-dir", str(tmp_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["status"] == "empty_dataset"
    assert output["no_demo_fallback"] is True
    assert "test-token" not in json.dumps(output)


def test_live_smoke_script_reports_http_failures_as_failed(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        live_smoke.config_loader,
        "load_config",
        lambda config_path=None, load_local=True: {"apify": {"api_token": "test-token"}},
    )
    monkeypatch.setattr(
        live_smoke.ImportYetiTool,
        "live_smoke",
        lambda self, query, min_shipments=1, limit=1, poll_timeout=120, actor_role="primary": {
            "auth": {"ok": True},
            "actor": {"id": "actor-1", "name": "importyeti", "title": None, "role": actor_role},
            "run_id": "run-1",
            "run_status": "SUCCEEDED",
            "run_status_message": "Done. Pushed 0 records to default dataset. HTTP failures: 1.",
            "dataset_id": "dataset-1",
            "raw_item_count": 0,
            "raw_item_keys": [],
            "mapped_company_count": 0,
        },
    )

    exit_code = live_smoke.main(["--output-dir", str(tmp_path)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["status"] == "failed"
    assert output["no_demo_fallback"] is True
