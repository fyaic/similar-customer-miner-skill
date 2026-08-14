"""Tests for email discovery helpers."""
from unittest.mock import MagicMock, patch

from tools.email_tool import EmailTool, is_generic_email


def test_hunter_key_can_come_from_env(monkeypatch):
    monkeypatch.setenv("HUNTER_API_KEY", "env-key")

    tool = EmailTool({})

    assert tool.hunter_key == "env-key"


def test_hunter_config_overrides_env(monkeypatch):
    monkeypatch.setenv("HUNTER_API_KEY", "env-key")

    tool = EmailTool({"hunter": {"api_key": "config-key"}})

    assert tool.hunter_key == "config-key"


@patch("tools.email_tool.requests.get")
def test_hunter_domain_search_calls_api(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "data": {
                "emails": [
                    {"value": "sales@example.com"},
                    {"value": "info@example.com"},
                ]
            }
        },
    )

    tool = EmailTool({"hunter": {"api_key": "test-key"}})

    assert tool.hunter_domain_search("example.com") == ["sales@example.com", "info@example.com"]
    mock_get.assert_called_once()
    assert mock_get.call_args.kwargs["params"] == {
        "domain": "example.com",
        "api_key": "test-key",
    }


@patch("tools.email_tool.requests.get")
def test_hunter_domain_contacts_returns_structured_records(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        json=lambda: {
            "data": {
                "emails": [
                    {
                        "value": "jane.doe@example.com",
                        "first_name": "Jane",
                        "last_name": "Doe",
                        "position": "Procurement Manager",
                        "confidence": 92,
                    }
                ]
            }
        },
    )

    tool = EmailTool({"hunter": {"api_key": "test-key"}})

    assert tool.hunter_domain_contacts("example.com") == [
        {
            "email": "jane.doe@example.com",
            "first_name": "Jane",
            "last_name": "Doe",
            "position": "Procurement Manager",
            "confidence": 92,
            "source": "hunter",
        }
    ]


def test_is_generic_email_identifies_department_mailboxes():
    assert is_generic_email("sales@example.com")
    assert is_generic_email("Support@example.com")
    assert not is_generic_email("jane.doe@example.com")
