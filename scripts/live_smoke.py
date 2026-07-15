"""Bounded live ImportYeti smoke test.

This script is intentionally strict: it never falls back to demo data.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config_loader
from tools.importyeti_tool import ImportYetiTool


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a bounded live ImportYeti smoke test")
    parser.add_argument("--config", default=None, help="Path to config YAML")
    parser.add_argument("--query", default="shower faucet", help="Single ImportYeti query to smoke")
    parser.add_argument("--actor-role", default="primary", choices=["primary", "fallback"], help="Configured live Actor to smoke")
    parser.add_argument("--limit", type=int, default=1, help="Dataset limit, 1-3")
    parser.add_argument("--min-shipments", type=int, default=1, help="Minimum shipments for the bounded query")
    parser.add_argument("--timeout", type=int, default=120, help="Run polling timeout in seconds")
    parser.add_argument("--output-dir", default="output", help="Directory for JSON smoke summary")
    return parser


def _write_summary(summary: Dict[str, Any], output_dir: str) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    actor_role = str(summary.get("actor_role") or "unknown")
    run_id = str(summary.get("run_id") or "no-run")
    safe_run_id = "".join(ch for ch in run_id if ch.isalnum() or ch in {"-", "_"})[:32] or "no-run"
    path = out_dir / f"live_smoke_{actor_role}_{safe_run_id}_{stamp}.json"
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.limit < 1 or args.limit > 3:
        print(json.dumps({"status": "failed", "error": "limit must be between 1 and 3"}))
        return 1

    try:
        config = config_loader.load_config(args.config, load_local=True)
        tool = ImportYetiTool(config, cache_dir=None)
        result = tool.live_smoke(
            args.query,
            min_shipments=args.min_shipments,
            limit=args.limit,
            poll_timeout=args.timeout,
            actor_role=args.actor_role,
        )
        has_http_failures = "HTTP failures:" in str(result.get("run_status_message"))
        if result["raw_item_count"]:
            status = "ok"
        elif has_http_failures:
            status = "failed"
        else:
            status = "empty_dataset"
        summary = {
            "status": status,
            "query": args.query,
            "actor_role": args.actor_role,
            "limit": args.limit,
            "auth_ok": result["auth"]["ok"],
            "actor": result["actor"],
            "run_id": result["run_id"],
            "run_status": result["run_status"],
            "run_status_message": result.get("run_status_message"),
            "dataset_id": result["dataset_id"],
            "dataset_item_count": result["raw_item_count"],
            "raw_item_keys": result["raw_item_keys"],
            "mapped_company_count": result["mapped_company_count"],
            "no_demo_fallback": True,
        }
        summary["output_json"] = str(_write_summary(summary, args.output_dir))
        print(json.dumps(summary, indent=2, sort_keys=True))
        if status == "ok":
            return 0
        return 1 if status == "failed" else 2
    except Exception as exc:
        summary = {
            "status": "failed",
            "query": args.query,
            "actor_role": args.actor_role,
            "limit": args.limit,
            "error": str(exc),
            "no_demo_fallback": True,
        }
        summary["output_json"] = str(_write_summary(summary, args.output_dir))
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
