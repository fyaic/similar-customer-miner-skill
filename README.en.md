# Similar Customer Miner · Trade Wind 2.0.0rc2

An internal pilot skill for finding product-related overseas B2B company candidates from CSV/Excel customer profiles. Live mode uses Trade Wind only; legacy Apify/Hunter credentials are disabled. Provider selection `hunter` means Trade Wind's upstream source, not a separate Hunter credential.

Python 3.10+ is required. Extract the entire folder including `.credentials/`, install `requirements.txt`, then run `scripts/tradewind_ops.py doctor`. It should report `config_source: bundled` for the internal ZIP. Run `scripts/run.py --input customers.csv --output preview.json --dry-run` before `scripts/run.py --input customers.csv --output leads.xlsx --mode live --max-results 10 --max-credits 2`. Use absolute script paths outside the skill folder. Default demo mode is synthetic and must not be delivered as real leads.

Preserve product phrases such as `hand tools`. Default discovery uses at most two queries per seed, three phrases per query; optional hybrid discovery also uses the company anchor. HS-only discovery is unsupported. Customs is optional verification of existing companies, not buyer discovery. Revenue and purchase profile fields are not automatically mapped to search filters.

Default filtering requires product-text corroboration and rechecks country after enrichment. Uncorroborated candidates stay in evidence instead of the sales sheet; this can reduce recall when descriptions are incomplete or use synonyms. Procurement/operations contacts rank before executive fallbacks. Unrelated or unknown job titles do not become main contacts. Mailbox verification requires a matching address, fresh evidence, valid status, deliverability and explicitly false catch-all; it does not prove employment or buying authority.

Outputs: three-sheet Excel (`线索名单`, `Results`, `Summary`), stats and private raw evidence. Exit 2 means partial completion; exit 0 can still mean no qualified candidates. Local cumulative budgets, exact-query cache and unresolved-billing stops limit cost. Do not delete ledgers to retry uncertain calls. Internal credential-bearing ZIPs are private; Git contains no key.

**Release scope:** tested internal pilot, not demonstrated sales-performance improvement. See [Chinese release review](docs/RELEASE_REVIEW.md), [validation results](docs/validation.json), [package checks](docs/package-validation.json), [workflow](references/workflow.md), and [engineering](ENGINEERING.md). README, SKILL and release reports are bundled together. rc2 supersedes rc1; install into a clean folder.
