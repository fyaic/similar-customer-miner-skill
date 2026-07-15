"""Configuration loader."""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.yaml"
DATASOURCES_CONFIG_PATH = Path(__file__).parent.parent / "config" / "datasources.yaml"


def _expand_path(value: Any) -> Any:
    """Expand user home in path strings nested in dicts/lists."""
    if isinstance(value, str):
        return os.path.expanduser(value)
    if isinstance(value, dict):
        return {k: _expand_path(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_path(v) for v in value]
    return value


def load_yaml(path: Path) -> Dict[str, Any]:
    """Load a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return _expand_path(data)


def load_config(config_path: Optional[str] = None, load_local: bool = True) -> Dict[str, Any]:
    """Load default + datasources + optional user config.

    Set load_local=False for deterministic demo/test runs that must not read
    gitignored local secrets.
    """
    config = load_yaml(DEFAULT_CONFIG_PATH)

    # Load datasource configuration template (API keys are empty by default)
    if DATASOURCES_CONFIG_PATH.exists():
        config = _merge_dicts(config, load_yaml(DATASOURCES_CONFIG_PATH))

    if config_path:
        user_config = load_yaml(Path(config_path))
        config = _merge_dicts(config, user_config)

    if load_local:
        # Auto-load local.yaml or secrets.yaml if present.
        local_path = DEFAULT_CONFIG_PATH.parent / "local.yaml"
        secrets_path = DEFAULT_CONFIG_PATH.parent / "secrets.yaml"
        for extra in [local_path, secrets_path]:
            if extra.exists():
                config = _merge_dicts(config, load_yaml(extra))

    return config


def _merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge override into base."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
    return result
