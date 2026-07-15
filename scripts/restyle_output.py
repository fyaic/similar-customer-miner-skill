"""Re-render an existing mining output with the product-level styled lead list.

Reads the full-detail `Results` sheet of an output xlsx and rebuilds the styled
`线索名单` tab (plus keeps Results + Summary), without re-running the pipeline.

Usage:
  python scripts/restyle_output.py <output.xlsx> [--out <styled.xlsx>]
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import table_style as ts
from src.exporter import _write_leads_sheet, _write_summary_sheet, _style_results_sheet
from src.models import SimilarCompany


def _v(row, name, default=None):
    val = row.get(name, default)
    if pd.isna(val) if not isinstance(val, list) else False:
        return default
    s = str(val).strip()
    return default if s in ("", "nan", "None") else val


def _row_to_company(row) -> SimilarCompany:
    def sv(field):
        return _v(row, f"{field}_value")

    hs = sv("hs_codes")
    hs_list = [h.strip() for h in str(hs).split(";") if h.strip()] if hs else []
    return SimilarCompany(
        source_seed=_v(row, "source_seed"),
        company_name=sv("company_name"),
        website=sv("website"),
        main_products=sv("main_products"),
        hs_codes=hs_list,
        contact_name=sv("contact_name"),
        contact_title=sv("contact_title"),
        email=sv("email"),
        email_confidence=float(_v(row, "email_confidence", 0) or 0),
        phone=sv("phone"),
        linkedin=sv("linkedin"),
        facebook=sv("facebook"),
        twitter=sv("twitter"),
        youtube=sv("youtube"),
        shipment_frequency=sv("shipment_frequency"),
        estimated_shipping_spend=sv("estimated_shipping_spend"),
        procurement_proxy_notes=_v(row, "procurement_proxy_notes_value"),
        priority_score=float(_v(row, "priority_score", 0) or 0),
        fit_score=float(_v(row, "fit_score", 0) or 0),
        grade=_v(row, "grade", "C"),
        notes=_v(row, "notes"),
        all_citations={"datasource": _v(row, "datasource", "")},
    )


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("output")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    src = Path(args.output)
    df = pd.read_excel(src, sheet_name="Results")
    from src.field_labels import to_canonical_columns
    df = to_canonical_columns(df)  # tolerate Chinese-headed inputs
    companies = [_row_to_company(r) for _, r in df.iterrows()]

    out = Path(args.out) if args.out else src.with_name(src.stem + "_styled.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Results", index=False)
        _write_leads_sheet(writer.book, companies)
        _write_summary_sheet(writer.book, companies)
        _style_results_sheet(writer.book)
        ts.enforce_font(writer.book)
    print(f"Wrote styled workbook: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
