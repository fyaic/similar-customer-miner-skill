"""Tests for UN Comtrade helper."""

from tools.comtrade_tool import ComtradeTool


def test_comtrade_key_can_come_from_env(monkeypatch):
    monkeypatch.setenv("COMTRADE_SUBSCRIPTION_KEY", "env-key")

    tool = ComtradeTool({})

    assert tool.subscription_key == "env-key"


def test_comtrade_config_overrides_env(monkeypatch):
    monkeypatch.setenv("COMTRADE_SUBSCRIPTION_KEY", "env-key")

    tool = ComtradeTool({"comtrade": {"subscription_key": "config-key"}})

    assert tool.subscription_key == "config-key"
