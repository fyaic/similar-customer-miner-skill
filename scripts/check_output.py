"""Validate a similar-customer-miner output file.

Checks required fields, citation coverage, confidence ranges, grade counts,
and explicit demo/inferred/unverified annotations.
"""
import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


REQUIRED_BASE_FIELDS = [
    "source_seed",
    "similarity_score",
    "overall_confidence",
    "grade",
    "fact_check_status",
    "notes",
    "all_citations",
    "email_verified",
]

REPORTED_FIELDS = [
    "company_name", "country", "website", "main_products", "hs_codes", "industry_tags",
    "revenue", "customs_china_purchase", "estimated_shipping_spend", "shipment_frequency",
    "contact_name", "contact_title", "phone", "email",
    "linkedin", "facebook", "twitter", "youtube",
]


def load_output(path: str) -> pd.DataFrame:
    p = Path(path)
    if p.suffix.lower() == ".xlsx":
        df = pd.read_excel(p, sheet_name="Results")
    elif p.suffix.lower() == ".csv":
        df = pd.read_csv(p)
    else:
        raise ValueError(f"Unsupported output format: {p.suffix}")
    # Results headers are Chinese for readability; map back to canonical keys.
    try:
        from src.field_labels import to_canonical_columns
        df = to_canonical_columns(df)
    except Exception:
        pass
    return df


def check_required_columns(df: pd.DataFrame) -> List[str]:
    missing: List[str] = []
    for col in REQUIRED_BASE_FIELDS:
        if col not in df.columns:
            missing.append(col)
    for field in REPORTED_FIELDS:
        for suffix in ("_value", "_citation", "_confidence", "_notes"):
            col = f"{field}{suffix}"
            if col not in df.columns:
                missing.append(col)
    return missing


def check_citation_coverage(df: pd.DataFrame) -> Tuple[int, int, List[str]]:
    """Return (filled, total, low_coverage_fields)."""
    low_fields: List[str] = []
    total_cells = 0
    filled_cells = 0
    for field in REPORTED_FIELDS:
        value_col = f"{field}_value"
        citation_col = f"{field}_citation"
        if value_col not in df.columns or citation_col not in df.columns:
            continue
        mask = df[value_col].notna() & (df[value_col].astype(str) != "")
        total = mask.sum()
        filled = df.loc[mask, citation_col].notna().sum()
        total_cells += int(total)
        filled_cells += int(filled)
        if total > 0 and filled / total < 0.5:
            low_fields.append(field)
    return filled_cells, total_cells, low_fields


def check_confidence_ranges(df: pd.DataFrame) -> List[str]:
    bad: List[str] = []
    for field in REPORTED_FIELDS:
        col = f"{field}_confidence"
        if col not in df.columns:
            continue
        values = pd.to_numeric(df[col], errors="coerce").dropna()
        if (values < 0).any() or (values > 1).any():
            bad.append(col)
    return bad


def check_grade_counts(df: pd.DataFrame, min_ab: int = 5) -> Dict[str, Any]:
    counts = df["grade"].value_counts().to_dict()
    ab_count = counts.get("A", 0) + counts.get("B", 0)
    return {
        "counts": counts,
        "ab_count": ab_count,
        "meets_min_ab": ab_count >= min_ab,
    }


def check_annotation_coverage(df: pd.DataFrame) -> Dict[str, int]:
    """Count rows that mention demo fallback / inferred / unverified."""
    text = (df["notes"].fillna("").astype(str) + " " +
            df[[c for c in df.columns if c.endswith("_notes")]].fillna("").astype(str).agg(" ".join, axis=1))
    lower = text.str.lower()
    return {
        "demo_fallback": int(lower.str.contains("demo fallback").sum()),
        "inferred": int(lower.str.contains("inferred").sum()),
        "unverified": int(lower.str.contains("unverified").sum()),
    }


def _is_filled(value: Any) -> bool:
    return pd.notna(value) and str(value).strip() not in {"", "nan", "None"}


def _row_has_source_url(row: pd.Series) -> bool:
    for col in ("company_name_citation", "shipment_frequency_citation", "main_products_citation", "hs_codes_citation"):
        if col in row and _is_filled(row[col]) and str(row[col]).startswith(("http://", "https://")):
            return True
    raw_citations = row.get("all_citations")
    if not _is_filled(raw_citations):
        return False
    try:
        citations = ast.literal_eval(str(raw_citations))
    except (SyntaxError, ValueError):
        return "source_url" in str(raw_citations)
    return bool(isinstance(citations, dict) and _is_filled(citations.get("source_url")))


def _normalize(name: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower()) if name is not None else ""


def check_business_fields(df: pd.DataFrame, seed_keys: set = None) -> Tuple[List[str], List[str]]:
    """Validate PRD business usability for live outputs (discovery rework)."""
    seed_keys = seed_keys or set()
    errors: List[str] = []
    warnings: List[str] = []
    for idx, row in df.iterrows():
        row_label = idx + 2  # Spreadsheet row number with header.
        if not _is_filled(row.get("company_name_value")):
            errors.append(f"Row {row_label}: company_name_value is required")
        # 1) Discovery validity: candidate must NOT be a seed / industry leader.
        if seed_keys and _normalize(row.get("company_name_value")) in seed_keys:
            errors.append(f"Row {row_label}: candidate equals seed/industry-leader (discovery invalid)")
        # 2) Similarity: HS or products present.
        if not (_is_filled(row.get("hs_codes_value")) or _is_filled(row.get("main_products_value"))):
            errors.append(f"Row {row_label}: hs_codes_value or main_products_value is required")
        # 3) Source citation required.
        if not _row_has_source_url(row):
            errors.append(f"Row {row_label}: source_url citation is required")
        # 4) Reachability: website/domain required for outreach.
        if not _is_filled(row.get("website_value")):
            errors.append(f"Row {row_label}: website/domain is required for outreach")
        # 5) Proxy honesty: estimated shipping spend must carry a proxy note.
        if _is_filled(row.get("estimated_shipping_spend_value")) and not _is_filled(row.get("procurement_proxy_notes_value")):
            errors.append(f"Row {row_label}: estimated_shipping_spend must carry procurement_proxy_notes")
        # Soft: email/contact/social three-of, and shipment frequency.
        if not any(_is_filled(row.get(c)) for c in ("email_value", "contact_name_value", "linkedin_value", "facebook_value")):
            warnings.append(f"Row {row_label}: no email/contact/social (reachability incomplete)")
        if not _is_filled(row.get("shipment_frequency_value")):
            warnings.append(f"Row {row_label}: shipment_frequency empty (BOL not verified)")
    return errors, warnings


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a similar-customer-miner output file")
    parser.add_argument("output", help="Path to output xlsx/csv")
    parser.add_argument("--min-ab", type=int, default=5, help="Minimum required A+B grade count")
    parser.add_argument("--business-fields", action="store_true", help="Require minimum live/business field usability")
    parser.add_argument("--seed-file", default=None, help="Path to newline-delimited seed/industry-leader names to exclude")
    args = parser.parse_args(argv)

    seed_keys = set()
    if args.seed_file:
        try:
            for line in Path(args.seed_file).read_text(encoding="utf-8").splitlines():
                if line.strip():
                    seed_keys.add(_normalize(line.strip()))
        except Exception as exc:
            print(f"WARNING: could not read seed file: {exc}")

    try:
        df = load_output(args.output)
    except Exception as exc:
        print(f"ERROR: Failed to load output: {exc}")
        return 1

    errors: List[str] = []
    warnings: List[str] = []

    missing = check_required_columns(df)
    if missing:
        errors.append(f"Missing columns: {', '.join(missing)}")

    filled, total, low_fields = check_citation_coverage(df)
    coverage = filled / total if total else 0.0
    if coverage < 0.8:
        errors.append(f"Citation coverage too low: {coverage:.1%} ({filled}/{total})")
    if low_fields:
        warnings.append(f"Low citation coverage by field: {', '.join(low_fields)}")

    bad_conf = check_confidence_ranges(df)
    if bad_conf:
        errors.append(f"Confidence values out of [0,1] in columns: {', '.join(bad_conf)}")

    grade_info = check_grade_counts(df, args.min_ab)
    if not grade_info["meets_min_ab"]:
        errors.append(f"A+B count {grade_info['ab_count']} below minimum {args.min_ab}")

    annotations = check_annotation_coverage(df)
    if args.business_fields:
        business_errors, business_warnings = check_business_fields(df, seed_keys)
        errors.extend(business_errors)
        warnings.extend(business_warnings)

    print(f"Rows: {len(df)}")
    print(f"Grade counts: {grade_info['counts']}")
    print(f"A+B count: {grade_info['ab_count']} (meets min {args.min_ab}: {grade_info['meets_min_ab']})")
    print(f"Citation coverage: {coverage:.1%} ({filled}/{total})")
    print(f"Annotation flags: {annotations}")

    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("OK: Output validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
