---
name: similar-customer-miner
description: |
  从一份高价值客户清单出发，挖掘相似的海外 B2B 买家（外贸拓客）。
  基于现有客户的行业定位、主营产品、HS 编码、价重比等特征，通过 Apify ImportYeti
  提单数据 + 网络搜索双通道发现候选买家，再用 Hunter 邮箱发现 + OpenCorporates 公司核验
  做富化，最终产出带引用来源、置信度评分和 A/B/C 分级的结构化 lead list。

  触发场景：找相似公司、发现新 B2B 买家、外贸客户挖掘、生成带评分和引用的 lead list。
  关键词：similar customer、buyer discovery、lead mining、外贸拓客、相似客户、B2B 买家挖掘。
---

# Skill: Similar Value Customer Miner

## Description

Mine similar overseas B2B buyers from a list of high-value customers.

## Trigger

Use this skill when the user wants to:

- Find similar companies to existing high-value customers
- Discover new B2B buyers for foreign trade
- Generate a scored lead list with citations and confidence

## Input

- `input`: Path to customer list (Excel/CSV)
- `output`: Path for result file (Excel/CSV/Markdown)
- `config`: Path to configuration file (optional)
- `max_results`: Maximum candidate companies per seed customer (optional)
- `grade`: Minimum grade to include: A, B, or C (optional)
- `mode`: `demo`, `test`, or `live`; demo/test skip local secrets, live loads them unless `--no-local` is set

## Output

A structured lead list with the following for each field:

- `value`
- `citation`
- `confidence` (0-1)
- `notes`

Plus summary statistics and fact-check status.

## Usage

```bash
python -m src.cli --input examples/sample_customers.xlsx --output output/result.xlsx
```

## Example

```bash
python -m src.cli \
  --input examples/sample_customers.xlsx \
  --output output/result.xlsx \
  --max-results 30 \
  --grade B
```

## Notes

- Requires Python 3.10+
- Apify API token recommended for ImportYeti data
- Output citations help human reviewers verify every field
- Confidence scores and grades help prioritize outreach
- Demo fallback data, department emails, and unverified contact channels are explicitly flagged in output notes
- Contact names/titles are populated only from structured person fields, not generic email local parts
- Validate outputs with `python scripts/check_output.py <output.xlsx>`
- Validate live/business usability with `python scripts/check_output.py <output.xlsx> --min-ab 0 --business-fields`
- Optional Google Fact Check integration searches external claim reviews as supplemental citations only; it is not revenue/procurement proof
- Fallback BOL `est_shipping_spend_usd` maps to `china_purchase_value` as estimated shipping spend, explicitly not verified procurement value
- Recommended strict live Apify smoke: `python scripts/live_smoke.py --actor-role fallback --query "apple" --limit 1`
- Primary Actor smoke is diagnostic only while upstream HTTP 403 persists: `python scripts/live_smoke.py --actor-role primary --query "shower faucet" --limit 1`
