# Similar Customer Miner · Trade Wind 2.0.0rc1

The live pipeline now uses Trade Wind only. Legacy Apify/Hunter credentials are not loaded or passed through BYOK. Customer profiling, seed exclusion, scoring and the three-sheet sales workbook remain available.

See [installation and usage](README.md), [skill instructions](SKILL.md), and [API/billing notes](references/tradewind.md). Internal ZIPs include an assigned Trade Wind credential and must retain `.credentials/`; public source contains no key. Python 3.10+ is required.

Live runs require `--mode live`. The default `demo` uses clearly marked synthetic examples. Unknown billing stops paid work; repeated exact queries reuse account-scoped state. Search hits are candidates, not verified buyers or decision-makers.
