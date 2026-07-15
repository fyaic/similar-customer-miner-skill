"""End-to-end pipeline test with demo fallback data."""
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.cli import run_pipeline
from src import config_loader


FIXTURE = Path(__file__).parent / "fixtures" / "mini_customers.csv"


@pytest.fixture
def default_config():
    config = config_loader.load_config("config/default.yaml", load_local=False)
    # Keep this regression test deterministic even when config/local.yaml
    # contains real API keys for manual/live runs.
    config.setdefault("apify", {})["api_token"] = ""
    config.setdefault("google", {})["fact_check_api_key"] = ""
    config.setdefault("google", {})["fact_check_enabled"] = False
    config.setdefault("opencorporates", {})["api_token"] = ""
    config.setdefault("comtrade", {})["subscription_key"] = ""
    return config


def test_pipeline_end_to_end(default_config):
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "result.xlsx"
        companies = run_pipeline(
            str(FIXTURE),
            str(output),
            default_config,
            min_grade="C",
        )

        assert output.exists()
        assert len(companies) > 0

        df = pd.read_excel(output, sheet_name="Results")
        # Results headers are Chinese for readability; map back to canonical keys.
        from src.field_labels import to_canonical_columns
        df = to_canonical_columns(df)

        # Required base columns
        for col in ("source_seed", "similarity_score", "overall_confidence", "grade", "fact_check_status"):
            assert col in df.columns, f"Missing base column: {col}"

        # Scoring columns from the discovery rework.
        for col in ("priority_score", "fit_score"):
            assert col in df.columns, f"Missing score column: {col}"

        # Each reported field has value/citation/confidence/notes
        for field in (
            "company_name", "country", "website", "main_products", "hs_codes",
            "revenue", "customs_china_purchase", "estimated_shipping_spend", "shipment_frequency",
            "contact_name", "contact_title", "phone", "email",
            "linkedin", "facebook", "twitter", "youtube",
        ):
            for suffix in ("_value", "_citation", "_confidence", "_notes"):
                assert f"{field}{suffix}" in df.columns, f"Missing column: {field}{suffix}"

        # Honest procurement fields: proxy notes surfaced; the misleading conflated
        # field is gone.
        assert "procurement_proxy_notes_value" in df.columns
        assert "china_purchase_value" not in df.columns

        # Confidence values in valid range
        conf_cols = [c for c in df.columns if c.endswith("_confidence")]
        for col in conf_cols:
            vals = pd.to_numeric(df[col], errors="coerce").dropna()
            assert (vals >= 0).all() and (vals <= 1).all(), f"Confidence out of range in {col}"

        # At least some A/B candidates from the demo pool
        ab_count = (df["grade"].isin(["A", "B"])).sum()
        assert ab_count >= 5, f"Expected at least 5 A/B rows, got {ab_count}"

        # Demo fallback is explicitly annotated
        notes = df["notes"].fillna("").str.lower()
        demo_count = notes.str.contains("demo fallback").sum()
        assert demo_count > 0, "Expected demo fallback annotations in notes"

        # Department/generic email channels are flagged without creating fake person names
        department_count = notes.str.contains("not a verified person").sum()
        assert department_count > 0, "Expected department email annotations"
        fake_names = {"Info", "Sales", "Support", "Contact", "Hello", "Admin", "Orders", "Service"}
        observed_contact_names = set(df["contact_name_value"].fillna("").astype(str))
        assert observed_contact_names.isdisjoint(fake_names)

        # Sorted by priority_score descending (worth-contacting first).
        prio = pd.to_numeric(df["priority_score"], errors="coerce").fillna(0).tolist()
        assert prio == sorted(prio, reverse=True), "Results should be sorted by priority_score desc"

        # Whole-table font constraint: every used cell in every sheet is 微软雅黑.
        import openpyxl
        wb = openpyxl.load_workbook(output)
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is not None:
                        assert cell.font.name == "微软雅黑", (
                            f"{ws.title}!{cell.coordinate} font is {cell.font.name}, expected 微软雅黑"
                        )
