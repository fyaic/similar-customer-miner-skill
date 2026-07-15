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
