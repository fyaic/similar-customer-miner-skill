"""Standalone credential health check.

Usage:
    # Static check (config only, no network):
    python scripts/check_secrets.py

    # Live probe (auth-check each configured key against its provider):
    python scripts/check_secrets.py --live

    # JSON output for scripting / monitoring:
    python scripts/check_secrets.py --live --json

Exit codes:
    0 — all required credentials healthy
    1 — one or more required credentials missing/broken
    2 — unexpected error
"""
import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config_loader
from src.secret_health import check_credentials, format_report


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check credential health for similar-customer-miner")
    p.add_argument("--config", default=None, help="Path to config YAML (default: config/default.yaml + local.yaml)")
    p.add_argument("--live", action="store_true", help="Probe each configured key against its provider")
    p.add_argument("--no-local", action="store_true", help="Do not load config/local.yaml")
    p.add_argument("--json", action="store_true", help="Output JSON instead of human-readable text")
    p.add_argument("--mode", default="live", choices=["demo", "test", "live"], help="Runtime mode for config resolution")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    load_local = args.mode == "live" and not args.no_local

    try:
        config = config_loader.load_config(args.config, load_local=load_local)
        health = check_credentials(
            config,
            live_probe=args.live,
            probe_only=["apify", "hunter", "google"] if args.live else None,
        )

        if args.json:
            print(json.dumps(health.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(format_report(health))

        return 1 if health.has_fatal else 0

    except Exception as exc:
        if args.json:
            print(json.dumps({"error": str(exc), "status": "fatal"}, indent=2))
        else:
            print(f"Fatal error during health check: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
