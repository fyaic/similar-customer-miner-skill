from pathlib import Path

from src import config_loader
from src.cli import _apply_runtime_mode, build_arg_parser


def test_load_config_can_skip_local_secrets(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    default_path = config_dir / "default.yaml"
    datasources_path = config_dir / "datasources.yaml"
    local_path = config_dir / "local.yaml"

    default_path.write_text("apify:\n  api_token: ''\n", encoding="utf-8")
    datasources_path.write_text("hunter:\n  api_key: ''\n", encoding="utf-8")
    local_path.write_text("apify:\n  api_token: local-secret\nhunter:\n  api_key: local-hunter\n", encoding="utf-8")

    monkeypatch.setattr(config_loader, "DEFAULT_CONFIG_PATH", default_path)
    monkeypatch.setattr(config_loader, "DATASOURCES_CONFIG_PATH", datasources_path)

    config = config_loader.load_config(load_local=False)

    assert config["apify"]["api_token"] == ""
    assert config["hunter"]["api_key"] == ""


def test_load_config_keeps_local_loading_by_default(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    default_path = config_dir / "default.yaml"
    datasources_path = config_dir / "datasources.yaml"
    local_path = config_dir / "local.yaml"

    default_path.write_text("apify:\n  api_token: ''\n", encoding="utf-8")
    datasources_path.write_text("hunter:\n  api_key: ''\n", encoding="utf-8")
    local_path.write_text("apify:\n  api_token: local-secret\n", encoding="utf-8")

    monkeypatch.setattr(config_loader, "DEFAULT_CONFIG_PATH", default_path)
    monkeypatch.setattr(config_loader, "DATASOURCES_CONFIG_PATH", datasources_path)

    config = config_loader.load_config()

    assert config["apify"]["api_token"] == "local-secret"


def test_cli_runtime_modes_control_local_loading():
    parser = build_arg_parser()

    demo_args = parser.parse_args(["--input", "in.csv", "--output", "out.xlsx"])
    live_args = parser.parse_args(["--input", "in.csv", "--output", "out.xlsx", "--mode", "live"])
    no_local_args = parser.parse_args(
        ["--input", "in.csv", "--output", "out.xlsx", "--mode", "live", "--no-local"]
    )

    assert demo_args.mode is None
    assert live_args.mode == "live"
    assert no_local_args.no_local is True


def test_cli_demo_mode_clears_api_credentials():
    config = {
        "apify": {"api_token": "local-secret"},
        "hunter": {"api_key": "local-hunter"},
        "google": {"fact_check_api_key": "local-google", "fact_check_enabled": True},
    }

    _apply_runtime_mode(config, "demo")

    assert config["apify"]["api_token"] == ""
    assert config["hunter"]["api_key"] == ""
    assert config["google"]["fact_check_api_key"] == ""
    assert config["google"]["fact_check_enabled"] is False


def test_cli_live_mode_discards_legacy_api_credentials():
    config = {"apify": {"api_token": "local-secret"}}

    _apply_runtime_mode(config, "live")

    assert config["apify"]["api_token"] == ""
    assert config["hunter"]["api_key"] == ""
