"""Tests for the SecretError typology, HTTP classification, and credential health."""
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.secret_errors import (
    SecretError,
    SecretMissingError,
    SecretInvalidError,
    SecretExhaustedError,
    SecretForbiddenError,
    classify_http_error,
    raise_for_status_classified,
)
from src.secret_health import check_credentials, format_report, HealthReport, CredentialReport


# --------------------------------------------------------------------------- #
# SecretError typology
# --------------------------------------------------------------------------- #

class TestSecretErrorTypology:
    def test_missing_error_has_correct_kind_and_remediation(self):
        err = SecretMissingError("apify", env_var="APIFY_API_TOKEN")
        assert err.kind == "missing"
        assert err.service == "apify"
        assert "APIFY_API_TOKEN" in (err.remediation or "")
        assert "config/local.yaml" in (err.remediation or "")

    def test_invalid_error_has_correct_kind(self):
        err = SecretInvalidError("hunter")
        assert err.kind == "invalid"
        assert err.service == "hunter"

    def test_exhausted_error_has_correct_kind(self):
        err = SecretExhaustedError("apify")
        assert err.kind == "exhausted"

    def test_forbidden_error_has_correct_kind(self):
        err = SecretForbiddenError("google")
        assert err.kind == "forbidden"

    def test_all_subclasses_inherit_from_secret_error(self):
        for cls in [SecretMissingError, SecretInvalidError, SecretExhaustedError, SecretForbiddenError]:
            assert issubclass(cls, SecretError)

    def test_to_dict_has_required_fields(self):
        err = SecretInvalidError("apify", "bad key", status_code=401)
        d = err.to_dict()
        assert d["service"] == "apify"
        assert d["kind"] == "invalid"
        assert d["status_code"] == 401
        assert "remediation" in d
        assert "message" in d

    def test_str_representation(self):
        err = SecretMissingError("hunter", env_var="HUNTER_API_KEY")
        s = str(err)
        assert "[missing]" in s
        assert "hunter" in s


# --------------------------------------------------------------------------- #
# classify_http_error / raise_for_status_classified
# --------------------------------------------------------------------------- #

def _mock_resp(status_code, body=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    if body is not None:
        resp.json.return_value = body
    else:
        resp.json.side_effect = ValueError("no json")
    return resp


class TestClassifyHttpError:
    def test_401_maps_to_invalid(self):
        err = classify_http_error("apify", _mock_resp(401))
        assert isinstance(err, SecretInvalidError)
        assert err.status_code == 401

    def test_402_maps_to_exhausted(self):
        err = classify_http_error("apify", _mock_resp(402))
        assert isinstance(err, SecretExhaustedError)

    def test_403_maps_to_forbidden(self):
        err = classify_http_error("apify", _mock_resp(403))
        assert isinstance(err, SecretForbiddenError)

    def test_429_maps_to_exhausted(self):
        err = classify_http_error("hunter", _mock_resp(429))
        assert isinstance(err, SecretExhaustedError)

    def test_extracts_detail_from_json_body(self):
        body = {"error": {"message": "Token expired"}}
        err = classify_http_error("apify", _mock_resp(401, body=body))
        assert "Token expired" in str(err)

    def test_extracts_detail_from_alternate_json_keys(self):
        body = {"message": "Quota exceeded"}
        err = classify_http_error("apify", _mock_resp(429, body=body))
        assert "Quota exceeded" in str(err)

    def test_falls_back_to_text_body(self):
        err = classify_http_error("apify", _mock_resp(403, text="Forbidden resource"))
        assert "Forbidden resource" in str(err)

    def test_raises_value_error_on_success_status(self):
        with pytest.raises(ValueError, match="success status"):
            classify_http_error("apify", _mock_resp(200))

    def test_5xx_raises_plain_http_error(self):
        with pytest.raises(requests.HTTPError):
            classify_http_error("apify", _mock_resp(500))


class TestRaiseForStatusClassified:
    def test_success_returns_silently(self):
        resp = _mock_resp(200)
        # Should not raise
        raise_for_status_classified("apify", resp)

    def test_401_raises_secret_invalid(self):
        with pytest.raises(SecretInvalidError):
            raise_for_status_classified("apify", _mock_resp(401))

    def test_403_raises_secret_forbidden(self):
        with pytest.raises(SecretForbiddenError):
            raise_for_status_classified("apify", _mock_resp(403))

    def test_500_raises_http_error(self):
        with pytest.raises(requests.HTTPError):
            raise_for_status_classified("apify", _mock_resp(500))


# --------------------------------------------------------------------------- #
# Tool integration: ImportYetiTool raises SecretMissingError
# --------------------------------------------------------------------------- #

class TestImportYetiToolSecretErrors:
    def test_keyword_search_raises_secret_missing_without_token(self):
        from tools.importyeti_tool import ImportYetiTool
        config = {"apify": {"discovery_actor_id": "test~actor"}}
        tool = ImportYetiTool(config)
        with pytest.raises(SecretMissingError) as exc_info:
            tool.keyword_search("shower faucet")
        assert exc_info.value.service == "apify"

    def test_live_search_no_fallback_raises_secret_missing(self):
        from tools.importyeti_tool import ImportYetiTool
        config = {"apify": {}}
        tool = ImportYetiTool(config)
        with pytest.raises(SecretMissingError):
            tool.search("query", allow_fallback=False)


# --------------------------------------------------------------------------- #
# Tool integration: EmailTool records SecretMissingError
# --------------------------------------------------------------------------- #

class TestEmailToolSecretErrors:
    def test_missing_hunter_key_records_error_and_returns_empty(self):
        from tools.email_tool import EmailTool
        tool = EmailTool({"hunter": {}})
        assert tool.hunter_key is None
        result = tool.hunter_domain_contacts("example.com")
        assert result == []
        assert tool.last_error is not None
        assert isinstance(tool.last_error, SecretMissingError)
        assert tool.last_error.service == "hunter"

    def test_hunter_key_present_no_error_recorded_initially(self):
        from tools.email_tool import EmailTool
        tool = EmailTool({"hunter": {"api_key": "test-key"}})
        assert tool.last_error is None


# --------------------------------------------------------------------------- #
# Credential health check
# --------------------------------------------------------------------------- #

class TestCheckCredentials:
    def test_all_missing_when_config_empty(self):
        report = check_credentials({}, live_probe=False)
        assert len(report.checks) == 5
        assert all(c.status == "missing" for c in report.checks)
        assert report.has_fatal  # apify is required and missing

    def test_apify_configured_passes_static_check(self):
        config = {
            "apify": {"api_token": "test-token"},
            "hunter": {},
            "opencorporates": {},
            "comtrade": {},
            "google": {},
        }
        report = check_credentials(config, live_probe=False)
        apify_check = next(c for c in report.checks if c.service == "apify")
        assert apify_check.status == "unchecked"
        assert apify_check.configured is True
        assert not report.has_fatal

    def test_env_var_fallback(self, monkeypatch):
        monkeypatch.setenv("APIFY_API_TOKEN", "env-token")
        report = check_credentials({}, live_probe=False)
        apify_check = next(c for c in report.checks if c.service == "apify")
        assert apify_check.configured is True

    def test_live_probe_apify_success(self):
        config = {"apify": {"api_token": "valid"}, "hunter": {}, "opencorporates": {}, "comtrade": {}, "google": {}}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": {"username": "testuser"}}
        with patch("src.secret_health.requests.get", return_value=mock_resp):
            report = check_credentials(config, live_probe=True, probe_only=["apify"])
        apify_check = next(c for c in report.checks if c.service == "apify")
        assert apify_check.status == "ok"
        assert "testuser" in (apify_check.detail or "")

    def test_live_probe_apify_401(self):
        config = {"apify": {"api_token": "bad"}, "hunter": {}, "opencorporates": {}, "comtrade": {}, "google": {}}
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": {"message": "Invalid token"}}
        mock_resp.text = ""
        with patch("src.secret_health.requests.get", return_value=mock_resp):
            report = check_credentials(config, live_probe=True, probe_only=["apify"])
        apify_check = next(c for c in report.checks if c.service == "apify")
        assert apify_check.status == "invalid"
        assert report.has_fatal

    def test_optional_missing_is_warning_not_fatal(self):
        config = {"apify": {"api_token": "ok"}, "hunter": {}, "opencorporates": {}, "comtrade": {}, "google": {}}
        report = check_credentials(config, live_probe=False)
        assert not report.has_fatal
        assert len(report.warnings()) >= 3  # hunter, opencorporates, comtrade, google all optional+missing


# --------------------------------------------------------------------------- #
# Report formatting
# --------------------------------------------------------------------------- #

class TestFormatReport:
    def test_report_has_header_and_summary(self):
        report = HealthReport(checks=[
            CredentialReport("apify", True, True, "APIFY_API_TOKEN", "ok", "auth ok"),
            CredentialReport("hunter", False, False, "HUNTER_API_KEY", "missing", "not set"),
        ])
        text = format_report(report)
        assert "Credential Health Report" in text
        assert "All required credentials are healthy" in text
        assert "apify" in text
        assert "hunter" in text

    def test_report_shows_fatal_when_required_missing(self):
        report = HealthReport(checks=[
            CredentialReport("apify", False, True, "APIFY_API_TOKEN", "missing", "not set", "Set APIFY_API_TOKEN"),
        ])
        text = format_report(report)
        assert "required credential" in text.lower()

    def test_health_report_to_dict_serializable(self):
        report = HealthReport(checks=[
            CredentialReport("apify", True, True, "APIFY_API_TOKEN", "ok"),
        ])
        d = report.to_dict()
        # Must be JSON-serializable
        json.dumps(d)
        assert d["all_required_ok"] is True
        assert len(d["checks"]) == 1
