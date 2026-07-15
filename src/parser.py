"""Parse customer input files into Customer objects."""
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.models import Customer
from src.utils import clean_text, split_values

logger = logging.getLogger("similar_customer_miner")


def resolve_column(df_columns: List[str], aliases: List[str]) -> Optional[str]:
    """Find the first matching column name from aliases."""
    col_map = {c.strip().lower(): c for c in df_columns}
    for alias in aliases:
        key = alias.strip().lower()
        if key in col_map:
            return col_map[key]
    return None


def read_file(path: str) -> pd.DataFrame:
    """Read Excel or CSV into DataFrame."""
    p = Path(path)
    if p.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path, dtype=str)
    if p.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str)
    raise ValueError(f"Unsupported file format: {p.suffix}")


def parse_customers(path: str, column_aliases: Dict[str, List[str]]) -> List[Customer]:
    """Parse customers from an input file."""
    df = read_file(path)
    df.columns = [str(c) for c in df.columns]

    col_id = resolve_column(df.columns.tolist(), column_aliases.get("id", ["id"]))
    if not col_id:
        raise ValueError("Required column 'id' not found in input")

    customers: List[Customer] = []
    for _, row in df.iterrows():
        raw_id = row.get(col_id)
        if pd.isna(raw_id):
            logger.warning("Skipping row with missing id")
            continue

        hs_codes = _get_hs_codes(row, df.columns, column_aliases)
        main_products = _get_text(row, df.columns, column_aliases, "main_products")
        if not hs_codes and not main_products:
            logger.warning("Skipping row with no HS codes or products")
            continue

        customer = Customer(
            id=str(raw_id).strip(),
            name=_get_text(row, df.columns, column_aliases, "name"),
            business_positioning=_get_text(row, df.columns, column_aliases, "business_positioning"),
            region_positioning=_get_text(row, df.columns, column_aliases, "region_positioning"),
            main_products=_get_text(row, df.columns, column_aliases, "main_products"),
            hs_codes=_get_hs_codes(row, df.columns, column_aliases),
            value_weight_ratio=_get_text(row, df.columns, column_aliases, "value_weight_ratio"),
            industry_leader=_get_text(row, df.columns, column_aliases, "industry_leader"),
            leader_revenue=_get_text(row, df.columns, column_aliases, "leader_revenue"),
            local_competitors=_get_text(row, df.columns, column_aliases, "local_competitors"),
            market_size=_get_text(row, df.columns, column_aliases, "market_size"),
            annual_shipment_frequency=_get_text(row, df.columns, column_aliases, "annual_shipment_frequency"),
            annual_china_purchase=_get_text(row, df.columns, column_aliases, "annual_china_purchase"),
            customer_revenue=_get_text(row, df.columns, column_aliases, "customer_revenue"),
            shipping_modes=_get_shipping_modes(row, df.columns, column_aliases),
            profit_level=_get_text(row, df.columns, column_aliases, "profit_level"),
            margin_per_shipment=_get_text(row, df.columns, column_aliases, "margin_per_shipment"),
        )
        customers.append(customer)

    logger.info("Parsed %d customers from %s", len(customers), path)
    return customers


def _get_text(
    row: pd.Series,
    columns: List[str],
    column_aliases: Dict[str, List[str]],
    field: str,
) -> Optional[str]:
    col = resolve_column(columns, column_aliases.get(field, []))
    if not col:
        return None
    return clean_text(row.get(col))


def _get_hs_codes(
    row: pd.Series,
    columns: List[str],
    column_aliases: Dict[str, List[str]],
) -> List[str]:
    col = resolve_column(columns, column_aliases.get("hs_codes", []))
    if not col:
        return []
    value = row.get(col)
    if pd.isna(value):
        return []
    codes = split_values(str(value))
    cleaned: List[str] = []
    for code in codes:
        code = re.sub(r"[^0-9]", "", code)
        if code:
            cleaned.append(code)
    return cleaned


def _get_shipping_modes(
    row: pd.Series,
    columns: List[str],
    column_aliases: Dict[str, List[str]],
) -> List[str]:
    modes: List[str] = []
    aliases = column_aliases.get("shipping_modes", [])
    for alias in aliases:
        col = resolve_column(columns, [alias])
        if col:
            value = row.get(col)
            if not pd.isna(value):
                text = clean_text(value)
                if text:
                    modes.append(text)
    return modes
