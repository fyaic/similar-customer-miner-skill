"""Chinese, user-friendly column labels for the Results (audit) sheet.

The exported file shows Chinese headers; all code keeps using the canonical
English column keys. Read boundaries (check_output / run_report / restyle / tests)
call `to_canonical_columns()` right after reading so downstream logic is unchanged.
"""
from typing import List

import pandas as pd

# Per-field base label (each field expands to 值/来源/可信度/说明).
FIELD_LABELS = {
    "company_name": "公司名",
    "country": "国家",
    "website": "官网",
    "main_products": "主营产品",
    "hs_codes": "HS编码",
    "industry_tags": "行业标签",
    "revenue": "营业额",
    "customs_china_purchase": "海关采购额",
    "estimated_shipping_spend": "预估运费支出(proxy)",
    "shipment_frequency": "发货频次",
    "contact_name": "联系人",
    "contact_title": "职位",
    "phone": "电话",
    "email": "邮箱",
    "linkedin": "领英",
    "facebook": "Facebook",
    "twitter": "Twitter/X",
    "youtube": "YouTube",
}

SUFFIX_LABELS = {
    "_value": "",
    "_citation": "·来源",
    "_confidence": "·可信度",
    "_notes": "·说明",
}

# Standalone (non field×suffix) columns.
BASE_LABELS = {
    "source_seed": "种子客户",
    "priority_score": "优先级分",
    "fit_score": "匹配度分",
    "similarity_score": "相似度分",
    "overall_confidence": "综合可信度",
    "grade": "评级",
    "fact_check_status": "核查状态",
    "datasource": "数据来源",
    "procurement_proxy_notes_value": "采购额proxy说明",
    "email_verified": "邮箱已验证",
    "notes": "备注",
    "all_citations": "全部来源",
}


def label_for(col: str) -> str:
    """Canonical English column name -> Chinese display label."""
    if col in BASE_LABELS:
        return BASE_LABELS[col]
    for suffix, suffix_label in SUFFIX_LABELS.items():
        if col.endswith(suffix):
            base = col[: -len(suffix)]
            if base in FIELD_LABELS:
                return FIELD_LABELS[base] + suffix_label
    return col


def _all_canonical() -> List[str]:
    cols = list(BASE_LABELS.keys())
    for field in FIELD_LABELS:
        for suffix in SUFFIX_LABELS:
            cols.append(field + suffix)
    return cols


CANONICAL_TO_CN = {c: label_for(c) for c in _all_canonical()}
CN_TO_CANONICAL = {cn: c for c, cn in CANONICAL_TO_CN.items()}


def to_chinese_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={c: label_for(c) for c in df.columns})


def to_canonical_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map a Chinese-headed Results frame back to canonical English keys."""
    return df.rename(columns={c: CN_TO_CANONICAL.get(c, c) for c in df.columns})
