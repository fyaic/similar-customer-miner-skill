"""Generate a PRD-level run report (run_report.md) for a mining output.

Reports discovery validity (seed overlap), field coverage, grade + priority
distribution, procurement proxy honesty, datasource split, and — when a run
stats JSON and/or log file are provided — API success/failure and run ids.

Usage:
  python scripts/run_report.py <output.xlsx> [--seed-file seeds.txt] \
      [--stats <output.stats.json>] [--log logs/similar-customer-miner.log] \
      [--out run_report.md]
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower()) if s is not None else ""


def _filled(series):
    return series.notna() & (series.astype(str).str.strip().isin(["", "nan", "None"]) == False)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("output")
    ap.add_argument("--seed-file", default=None)
    ap.add_argument("--stats", default=None)
    ap.add_argument("--log", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    p = Path(args.output)
    df = pd.read_excel(p, sheet_name="Results") if p.suffix == ".xlsx" else pd.read_csv(p)
    from src.field_labels import to_canonical_columns
    df = to_canonical_columns(df)  # Results headers are Chinese; map back to canonical
    n = len(df)

    seeds = set()
    if args.seed_file and Path(args.seed_file).exists():
        seeds = {_norm(x) for x in Path(args.seed_file).read_text(encoding="utf-8").splitlines() if x.strip()}

    stats = {}
    stats_path = args.stats or str(p.with_suffix(".stats.json"))
    if Path(stats_path).exists():
        stats = json.loads(Path(stats_path).read_text(encoding="utf-8"))

    # Discovery validity
    seed_overlap = 0
    if seeds and "company_name_value" in df:
        seed_overlap = int(df["company_name_value"].map(lambda x: _norm(x) in seeds).sum())

    # Field coverage
    cov_fields = ["website", "email", "contact_name", "linkedin", "hs_codes",
                  "estimated_shipping_spend", "shipment_frequency", "revenue"]
    coverage = {}
    for f in cov_fields:
        col = f"{f}_value"
        coverage[f] = int(_filled(df[col]).sum()) if col in df else 0

    # Grade + priority
    grades = df["grade"].value_counts().to_dict() if "grade" in df else {}
    prio = df["priority_score"].describe().to_dict() if "priority_score" in df else {}

    # Proxy honesty
    est_col, note_col = "estimated_shipping_spend_value", "procurement_proxy_notes_value"
    est_filled = int(_filled(df[est_col]).sum()) if est_col in df else 0
    proxy_ok = 0
    if est_col in df and note_col in df:
        proxy_ok = int((_filled(df[est_col]) & _filled(df[note_col])).sum())
    customs_filled = int(_filled(df["customs_china_purchase_value"]).sum()) if "customs_china_purchase_value" in df else 0

    # Datasource split
    ds = df["datasource"].value_counts().to_dict() if "datasource" in df else {}

    # API from log
    api = {}
    if args.log and Path(args.log).exists():
        text = Path(args.log).read_text(encoding="utf-8", errors="ignore")
        api["bol_403"] = len(re.findall(r"BOL verify failed.*403", text))
        api["apify_calls"] = len(re.findall(r"Calling Apify actor", text))
        api["run_ids"] = re.findall(r'"id":\s*"([a-zA-Z0-9]+)"', text)[:10]

    lines = []
    lines.append(f"# 运行报告 — {p.name}\n")
    lines.append(f"- mode: {stats.get('mode','?')} | 输入行: {stats.get('input_rows','?')} | 输出行: {n}\n")
    lines.append("## 发现有效性")
    tw = stats.get("tradewind")
    if tw:
        d = tw.get('discovery', {})
        lines.append(f"- Trade Wind 候选: {tw.get('candidate_count', 0)}；种子排除: {d.get('excluded_seed', 0)}；去重: {d.get('duplicates', 0)}；国家/身份隔离: {d.get('country_mismatch', 0)}")
        lines.append(f"- 发现候选: {tw.get('discovered_candidates', '?')}；产品未佐证: {tw.get('product_unconfirmed_count', 0)}")
        lines.append(f"- 公司补全: {tw.get('enriched_companies', '?')}；待补全: {tw.get('enrichment_deferred_count', '?')}")
        lines.append(f"- 具名候选: {tw.get('named_contacts', 0)}；职位关键词匹配: {tw.get('role_matched_contacts', 0)}；已验证邮箱: {tw.get('verified_mailboxes', 0)}")
        lines.append(f"- 本次新增已知费用: {tw.get('new_credits_known', '?')} credits；复用请求: {tw.get('reused_requests', 0)}；未决账单: {tw.get('budget', {}).get('unresolved_operations', '?')}")
        lines.append(f"- 停止原因: {tw.get('stop_reason') or '无'}；来源响应: {stats.get('evidence_file', '见同名 evidence.json')}")
        lines.append("- API 与职位关键词仅提供候选证据；不证明采购权、任职、采购规模或销售转化。")
    else:
        d = stats.get("discovery", {})
        lines.append(f"- 历史/离线通道: apify={d.get('apify','?')} web_search={d.get('web_search','?')}")
        lines.append(f"- 排除种子/龙头: {d.get('excluded_seed','?')} | 去重剔除: {d.get('deduped','?')}")
    lines.append(f"- 输出中与提供的种子名单重合: {seed_overlap}" if seeds else "- 未提供独立种子名单；此报告不单独验证种子重合。")
    evidence_path = p.with_suffix('.evidence.json')
    if tw and evidence_path.exists():
        evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
        rejected = evidence.get('quarantined', [])
        if rejected:
            lines.append("## 未进入销售页的候选（保留复核）")
            for item in rejected:
                lines.append(f"- {item.get('company', '?')}: {item.get('reason', 'unknown')}")
    lines.append("## 字段覆盖")
    for f, c in coverage.items():
        lines.append(f"- {f}: {c}/{n} ({c/n:.0%})" if n else f"- {f}: 0")
    lines.append("\n## 评分分布")
    lines.append(f"- grade: {grades}")
    if prio:
        lines.append(f"- priority_score: min={prio.get('min',0):.3f} mean={prio.get('mean',0):.3f} max={prio.get('max',0):.3f}")
    lines.append("\n## 采购额诚实性")
    lines.append(f"- estimated_shipping_spend 填充: {est_filled} | 其中带 proxy 标注: {proxy_ok} ({(proxy_ok/est_filled if est_filled else 1):.0%})")
    lines.append(f"- customs_china_purchase 填充: {customs_filled} (非零值需核对真实海关来源)\n")
    lines.append("## 数据来源分布")
    lines.append(f"- {ds}\n")
    if api:
        lines.append("## API 观测 (from log)")
        lines.append(f"- Apify actor 调用: {api.get('apify_calls',0)} | BOL 403(账户封顶): {api.get('bol_403',0)}")
        lines.append(f"- run_ids(sample): {api.get('run_ids',[])}\n")
    lines.append("## 人工抽样核验位 (待人工填写)")
    lines.append("| 公司 | 真实存在? | 真进口该品类? | 联系人有效? |")
    lines.append("|------|-----------|---------------|-------------|")
    for name in (df["company_name_value"].head(5).tolist() if "company_name_value" in df else []):
        lines.append(f"| {name} | | | |")

    out = args.out or str(p.with_name(p.stem + "_run_report.md"))
    Path(out).write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")
    print(f"seed_overlap={seed_overlap} grades={grades} website_cov={coverage.get('website')}/{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
