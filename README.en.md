# Similar Customer Miner · Trade Wind 2.0.0rc6

An internal pilot skill for finding product-related overseas B2B company candidates from CSV/Excel customer profiles. Live mode uses Trade Wind only; legacy Apify/Hunter credentials are disabled. Provider selection `hunter` means Trade Wind's upstream source, not a separate Hunter credential.

Python 3.10+ is required. Extract the entire folder including `.credentials/`, install `requirements.txt`, then run `scripts/tradewind_ops.py doctor`. It should report `config_source: bundled` for the internal ZIP. Run `scripts/run.py --input customers.csv --output preview.json --dry-run` before `scripts/run.py --input customers.csv --output leads.xlsx --mode live --max-results 10 --max-credits 2`. Use absolute script paths outside the skill folder. Execution requires an explicit --mode live/demo/test; only dry-run may omit it. Demo/test are synthetic and cannot be delivered as real leads.

Preserve product phrases such as `hand tools`. Default discovery uses at most two queries per seed, three phrases per query; optional hybrid discovery also uses the company anchor. HS-only discovery is unsupported. Customs is optional verification of existing companies, not buyer discovery. Revenue and purchase profile fields are not automatically mapped to search filters.

Default filtering requires product-text corroboration and rechecks country after enrichment. Uncorroborated candidates appear in the review queue without being labelled irrelevant. Explicit product aliases and dated official-page reviews can corroborate them. See [product review workflow](references/product-review.md); pass `--product-evidence-file reviews.json` and retain the same ledger/budget. The program checks scope and provenance but does not fetch or authenticate websites. Newly eligible contact calls may incur fees. Business-role hints, import evidence and unverified buying qualification are separate fields. Procurement/operations contacts rank before executive fallbacks. Unrelated or unknown job titles do not become main contacts. Mailbox verification requires a matching address, fresh evidence, valid status, deliverability and explicitly false catch-all; it does not prove employment or buying authority.

Outputs: live four-sheet Excel (`线索名单`, `待复核`, `Results`, `Summary`), stats, private raw evidence and `.review.json` (also emitted for CSV/Markdown). Exit 2 means partial completion; exit 0 can still mean no qualified candidates. Local cumulative budgets, exact-query cache and unresolved-billing stops limit cost. Do not delete ledgers to retry uncertain calls. Internal credential-bearing ZIPs are private; Git contains no key.

**Usage scope:** candidate discovery with human review. Product relevance, importer status, current employment and buying authority require separate confirmation. See [skill instructions](SKILL.md), [workflow](references/workflow.md) and [API reference](references/tradewind.md).

The recipient ZIP includes runtime code, configuration, examples and user instructions. Internal comparisons, evaluation reports, test summaries and engineering documents are excluded. `MANIFEST.json` records file hashes; `scripts/verify_package.py` checks them offline. Internal packages include the assigned Trade Wind key in `.credentials/`; retain that folder. rc6 supersedes rc5; install into a clean folder.

## Execution coverage in rc4

New acquisition work must execute Trade Wind business APIs. Company research, health checks and replay are insufficient. People search defaults to Apollo with purchasing/supply-chain/operations/executive title filters, one company domain per request and at most one person enrichment per company. Company APIs still use Hunter through Trade Wind; no legacy provider keys.

The .audit.json tracks each planned seed query and selected company. Product-review holds, missing domains, enrichment caps, missing receipts and billing stops return exit 2. Exit 0 requires complete scoped coverage and new real business receipts; --allow-cached explicitly accepts complete cached coverage without claiming a new online case. Historical receipts without transport provenance remain unproven. Empty results establish execution, not lead quality. Run scripts/audit_run.py leads.evidence.json --ledger /path/to/account/state.sqlite3 to compare the original ledger with request/response records. This is a local audit, not provider-signed attestation.

Mailbox safe/role_account is normalized to valid only when deliverable and safe-to-send are both true. Verification also requires the matching address, a recent receipt, explicitly false catch-all and no explicit unsafe flag. Raw status and tri-state catch-all remain separate; a role mailbox never proves a named decision-maker.

## rc5 network recovery / 网络恢复

rc5 fixes connection-refused classification and failure provenance. Typed pre-connect refusal becomes `not_sent` with released local reserve; timeouts, resets and ambiguous billing still block retries. No automatic retry or proxy bypass. A strict opt-in `recover-refused --apply` command preserves and migrates matching rc4 WinError 10061 records; other unknowns remain blocked.

先执行 `python /path/to/skill/scripts/tradewind_ops.py diagnose --output network-diagnostics.json`，无Trade Wind凭证、不调用收费业务API。小样本使用 `python /path/to/skill/scripts/run.py --input customers.csv --output trial.xlsx --mode live --trial`，首个种子、最多3家候选/补全1家。预算沿用原账户累计预算。给业务侧交付Excel及.status.md中文说明，失败不等于零客户。

完整流程见[网络诊断与恢复](references/network-recovery.md)。Install rc6 into a new directory, retain .credentials, and keep the original working directory/account ledger. rc4 and earlier archives remain unchanged.

## rc6 billing failures

Company, contact and customs work runs before mailbox verification. A terminal single-email 5xx failure with an explicit billing receipt is skipped without retry; missing receipts still retain reservations and block new paid work. Status separates run charges, cumulative charges, reservations and local budget headroom. `tradewind_ops.py billing-report --output billing-handoff.json` produces a local maintenance handoff without a business API call. See [billing recovery](references/billing-recovery.md).

An upgrade cannot settle historical unknown charges or repair a provider's HTTP 500. Preserve the original working directory, account ledger and credentials.
