"""Command-line entry point for similar-customer-miner."""
import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from src import (
    buyer_discovery,
    company_verify,
    config_loader,
    enrichment,
    entity_resolution,
    exporter,
    fact_check,
    market_filter,
    parser,
    profiler,
    scoring,
    utils,
    validation,
    tradewind,
)
from src.models import Customer, CustomerProfile, SimilarCompany

logger = logging.getLogger("similar_customer_miner")

API_CREDENTIAL_FIELDS = (
    ("apify", "api_token"),
    ("opencorporates", "api_token"),
    ("hunter", "api_key"),
    ("comtrade", "subscription_key"),
    ("google", "fact_check_api_key"),
)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Mine similar B2B buyers from high-value customers")
    p.add_argument("--input", required=True, help="Path to customer list (xlsx/csv)")
    p.add_argument("--output", required=True, help="Path for output file")
    p.add_argument("--config", default=None, help="Path to config YAML")
    p.add_argument("--mode", default=None, choices=["demo", "test", "live"], help="Runtime mode")
    p.add_argument("--allow-cached", action="store_true", help="Accept a complete cached batch; never classify it as a new online case")
    p.add_argument("--trial", action="store_true", help="First seed only, up to 3 candidates and 1 enrichment; preserve cumulative budget")
    p.add_argument("--proxy-mode", choices=["system", "direct"], default=None, help="System proxy by default; direct is an explicit per-run override")
    p.add_argument("--no-local", action="store_true", help="Do not load config/local.yaml or config/secrets.yaml")
    p.add_argument("--max-results", type=int, default=None, help="Max candidates per seed")
    p.add_argument("--grade", default="C", choices=["A", "B", "C"], help="Minimum grade to output")
    p.add_argument("--max-credits", default=None, help="Local cumulative credit budget (not provider hard cap)")
    p.add_argument("--state-dir", default=None, help="Private billing/cache state directory")
    p.add_argument("--env-file", default=None, help="Explicit Trade Wind env file override")
    p.add_argument("--product-evidence-file", default=None, help="Dated official-page product reviews JSON")
    p.add_argument("--dry-run", action="store_true", help="Write request preview without network or credentials")
    p.add_argument("--log-level", default="INFO", help="Logging level")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    arg_parser = build_arg_parser()
    args = arg_parser.parse_args(argv)
    if not args.dry_run and args.mode is None:
        arg_parser.error("Execution requires --mode live, demo or test; no implicit demo")
    load_local = False  # v2 never loads legacy local.yaml/secrets.yaml credentials
    config = config_loader.load_config(args.config, load_local=load_local)
    _apply_runtime_mode(config, args.mode)
    for key in ("max_credits", "state_dir", "env_file", "product_evidence_file", "proxy_mode"):
        if getattr(args, key) is not None:
            config.setdefault("tradewind", {})[key] = getattr(args, key)
    if args.trial:
        config.setdefault("runtime", {})["trial"] = True
        config.setdefault("pipeline", {})["max_results_per_customer"] = min(3, args.max_results if args.max_results is not None else config.get("pipeline", {}).get("max_results_per_customer", 3))
        config.setdefault("tradewind", {})["max_enrich"] = min(1, config.get("tradewind", {}).get("max_enrich", 1))
        config["tradewind"]["max_discovery_queries"] = 1
        args.max_results = config["pipeline"]["max_results_per_customer"]
    if args.dry_run:
        profiles = profiler.profile_customers(parser.parse_customers(args.input, config.get("input", {}).get("column_aliases", {})))
        if args.trial: profiles = profiles[:1]
        preview = tradewind.preview(profiles, config, args.max_results)
        preview["trial"] = args.trial
        from src.tradewind_core.security import private_json
        private_json(args.output, preview)
        print("Preview written; no API calls")
        return 0

    log_level = args.log_level or config.get("logging", {}).get("level", "INFO")
    utils.setup_logging(log_level, config.get("logging", {}).get("file"))

    if args.max_results:
        config.setdefault("pipeline", {})["max_results_per_customer"] = args.max_results

    try:
        run_pipeline(args.input, args.output, config, min_grade=args.grade)
        tw_stats = config.get("_run_stats", {}).get("tradewind", {})
        if args.mode == "live" and tw_stats.get("connection_refused"):
            from src.tradewind_core.network import diagnose
            from src.tradewind_core.security import private_json
            diagnosis = diagnose(config.get("tradewind", {}).get("proxy_mode", "system"))
            private_json(Path(args.output).with_suffix('.diagnostics.json'), diagnosis)
            with Path(args.output).with_suffix('.status.md').open('a', encoding='utf-8') as status:
                status.write("\n自动网络检查：" + diagnosis['next_action'] + "\n")
            print(diagnosis['next_action'], file=sys.stderr)
        audit = tw_stats.get("execution_audit", {})
        if args.mode == "live" and (not audit.get("coverage_complete") or not (audit.get("new_online_case") or args.allow_cached and audit.get("cached_or_live_complete"))):
            print("Partial output saved; inspect .audit.json, .stats.json and .evidence.json", file=sys.stderr)
            return 2
        return 0
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        return 1


def _apply_runtime_mode(config: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """Apply demo/test/live credential isolation to a loaded config."""
    config.setdefault("runtime", {})["mode"] = mode
    if mode == "live":
        for section, key in API_CREDENTIAL_FIELDS:
            config.setdefault(section, {})[key] = ""
        config.setdefault("google", {})["fact_check_enabled"] = False
    if mode in {"demo", "test"}:
        for section, key in API_CREDENTIAL_FIELDS:
            config.setdefault(section, {})[key] = ""
        config.setdefault("google", {})["fact_check_enabled"] = False
    return config


def run_pipeline(input_path: str, output_path: str, config: Dict[str, Any], min_grade: str = "C") -> List[SimilarCompany]:
    """Run the full mining pipeline."""
    logger.info("Starting pipeline: input=%s output=%s", input_path, output_path)

    # P1: Parse + profile
    aliases = config.get("input", {}).get("column_aliases", {})
    customers: List[Customer] = parser.parse_customers(input_path, aliases)
    profiles: List[CustomerProfile] = profiler.profile_customers(customers)
    if config.get("runtime", {}).get("trial"):
        profiles = profiles[:1]
    logger.info("Parsed %d customers, generated %d profiles", len(customers), len(profiles))

    if config.get("runtime", {}).get("mode") == "live":
        enriched = tradewind.mine(profiles, config, output_path)
        # The Trade Wind path already deduplicates by exact name/domain. Fuzzy
        # merges can incorrectly bind one person's email to another company.
        from dataclasses import replace
        scoring_profiles = [replace(p, target_regions=tradewind.target_countries(config)) for p in profiles]
        checked = scoring.score_companies(enriched, scoring_profiles, config)
        for company in checked:
            company.fact_check_status = "pending"  # API evidence is not human verification
    else:
        raw_companies = buyer_discovery.discover_buyers(profiles, config)
        verified = company_verify.verify_companies(raw_companies, config)
        enriched = enrichment.enrich_companies(verified, config)
        validated = validation.validate_companies(enriched, config)
        unique = entity_resolution.deduplicate_companies(validated)
        scored = scoring.score_companies(unique, profiles, config)
        checked = fact_check.fact_check_companies(scored, config)

    # Filter by grade
    grade_order = {"A": 3, "B": 2, "C": 1}
    min_level = grade_order.get(min_grade, 1)
    filtered = [c for c in checked if grade_order.get(c.grade, 0) >= min_level]

    # P6: Export
    exporter.export_results(filtered, output_path, config)

    # Persist run stats (discovery / BOL verify) next to the output for the run report.
    try:
        import json
        stats = dict(config.get("_run_stats", {}))
        stats["mode"] = config.get("runtime", {}).get("mode")
        stats["input_rows"] = len(customers)
        stats["output_rows"] = len(filtered)
        stats_path = Path(output_path).with_suffix(".stats.json")
        stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not write run stats: %s", exc)

    logger.info("Pipeline complete: %d companies exported", len(filtered))
    if config.get("runtime", {}).get("mode") == "live":
        tw = config.get("_run_stats", {}).get("tradewind", {})
        audit = tw.get("execution_audit", {})
        text = ("# 本次查询说明\n\n"
            + ("本次为小样本试跑：仅首个种子，最多3家候选、补全1家。\n\n" if config.get("runtime", {}).get("trial") else "")
            + f"当前可交付候选：{len(filtered)}家；范围内完成：{audit.get('companies_complete',0)}/{audit.get('companies_planned',0)}家。\n\n"
            + f"执行状态：{audit.get('classification','unproven')}。{tw.get('stop_reason') or '覆盖不足请查待复核队列和补全上限；缓存不算新增API案例。'}\n\n"
            + f"本轮已确认费用：{tw.get('new_credits_known','unknown')} credits；本地预留不代表实际扣费。\n\n"
            + "连接失败不等于查询到零客户；不会通过等待自动解锁，也不自动重复收费请求。诊断信息留给维护人员，业务侧交付本说明及Excel。\n")
        Path(output_path).with_suffix('.status.md').write_text(text, encoding='utf-8')
    _print_summary(filtered)
    return filtered


def _print_summary(companies: List[SimilarCompany]) -> None:
    counts = {}
    for c in companies:
        counts[c.grade] = counts.get(c.grade, 0) + 1
    print("\n=== Similar Customer Miner Summary ===")
    print(f"Total companies: {len(companies)}")
    print(f"Grade A: {counts.get('A', 0)}")
    print(f"Grade B: {counts.get('B', 0)}")
    print(f"Grade C: {counts.get('C', 0)}")


if __name__ == "__main__":
    sys.exit(main())
