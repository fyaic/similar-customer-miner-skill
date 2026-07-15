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
    p.add_argument("--mode", default="demo", choices=["demo", "test", "live"], help="Runtime mode")
    p.add_argument("--no-local", action="store_true", help="Do not load config/local.yaml or config/secrets.yaml")
    p.add_argument("--max-results", type=int, default=None, help="Max candidates per seed")
    p.add_argument("--grade", default="C", choices=["A", "B", "C"], help="Minimum grade to output")
    p.add_argument("--log-level", default="INFO", help="Logging level")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    load_local = args.mode == "live" and not args.no_local
    config = config_loader.load_config(args.config, load_local=load_local)
    _apply_runtime_mode(config, args.mode)

    log_level = args.log_level or config.get("logging", {}).get("level", "INFO")
    utils.setup_logging(log_level, config.get("logging", {}).get("file"))

    if args.max_results:
        config.setdefault("pipeline", {})["max_results_per_customer"] = args.max_results

    try:
        run_pipeline(args.input, args.output, config, min_grade=args.grade)
        return 0
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        return 1


def _apply_runtime_mode(config: Dict[str, Any], mode: str) -> Dict[str, Any]:
    """Apply demo/test/live credential isolation to a loaded config."""
    config.setdefault("runtime", {})["mode"] = mode
    if mode == "live":
        config.setdefault("apify", {}).setdefault("actor_role", "fallback")
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
    logger.info("Parsed %d customers, generated %d profiles", len(customers), len(profiles))

    # Optional market filter
    try:
        market_filter.rank_markets(profiles, config)
    except Exception as exc:
        logger.warning("Market filter skipped: %s", exc)

    # P2: Buyer discovery
    raw_companies = buyer_discovery.discover_buyers(profiles, config)

    # P3: Company verify + enrichment
    verified = company_verify.verify_companies(raw_companies, config)
    enriched = enrichment.enrich_companies(verified, config)

    # P4: Validation + entity resolution
    validated = validation.validate_companies(enriched, config)
    unique = entity_resolution.deduplicate_companies(validated)

    # P5: Scoring + fact check
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
