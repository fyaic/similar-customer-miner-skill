"""Tests for exporter module."""
import tempfile
from pathlib import Path

from src.exporter import export_results
from src.models import SimilarCompany


def test_export_results_xlsx():
    companies = [
        SimilarCompany(
            source_seed="1",
            company_name="Test Co",
            country="US",
            overall_confidence=0.8,
            grade="A",
            fact_check_status="passed",
        )
    ]
    config = {"output": {"include_summary_sheet": True}}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "result.xlsx"
        export_results(companies, str(path), config)
        assert path.exists()
        assert path.stat().st_size > 0
