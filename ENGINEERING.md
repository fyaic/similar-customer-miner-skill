# Engineering · Trade Wind 2.0.0rc4

This describes the current `codex/tradewind-v2-rc4` branch. The legacy architecture is available in Git history/main; its Apify/Hunter modules and credential setup are not the v2 live pipeline.

`parser → profiler → tradewind.mine → scoring → exporter` is the live path. Demo/test retains the old offline helpers. The CLI ignores local/secrets YAML and clears legacy credentials. `scripts/run.py` is the portable skill entrypoint. `src/tradewind_core` provides the account-scoped SQLite ledger, host allowlist, no redirects, response redaction and exact-query reuse inherited from sps-overseas-peers.

Discovery is bounded per seed; phrases stay intact, hybrid is optional. Exact domain/name deduplication retains first seed association. `src/qualification.py` uses contiguous normalized product phrases, explicit aliases and sentence-level negation guards. Missing/nonmatching text becomes `needs_review`; it is not an irrelevance finding. Operator-provided official-page reviews require exact seed/domain/product, HTTPS, excerpt, reviewer and a timezone-aware check within 90 days. A positive review must contain the product/alias; all target products must be reviewed unrelated to exclude a multi-product candidate. The loader validates supplied data without fetching/authenticating pages. Invalid reviews fail before credential loading or paid calls.

The review queue is available in a dedicated workbook sheet and private `.review.json`; source evidence remains separate. Scope/conflict exclusions retain precedence over product reviews. Explicitly reviewed-unrelated companies never receive contact calls. Business roles are provider-text hints; matching customs samples never establish buying intent, annual procurement or identity independently. `contact_search_enabled: false` disables people/mailbox calls for company-only qualification. No added network API is required.

Contact title heuristics prioritize procurement/supply-chain, operations, then executive fallback. Unknown/unrelated roles are retained only in raw evidence. Work-email domain and employer association must match. Verification accepts documented `result` and compatible `data` envelopes, checks exact subject and seven-day freshness, and requires explicitly false catch-all. Verification citation/time are separate from the source that supplied the email. Employment/authority always remain unverified.

Scoring uses the requested countries and excludes sampled customs counts from shipping strength/frequency. Grades measure field confidence, not confirmed customer quality. No output grade authorizes outreach. Live output adds a review sheet to the original three sheets; additional audit columns expose role, product-review provenance and import status.

Run `python -m pytest -q tests`. The same outcome-based `tests/test_business_acceptance.py` can run in an archived rc1 checkout; see the release review for paired results and selection bias. `scripts/validate_live.py` is explicitly paid; it reuses a specified ledger and stops on partial results. Raw results remain in ignored outputs. Public summaries contain no customer email addresses or key.

`src/tradewind_core/__init__.py` supplies the runtime/build version. Match pyproject, config, SKILL, both READMEs and release reports when releasing. Build allowlists files and generates MANIFEST/DISTRIBUTION metadata. Never publish credential-bearing packages. Package install checks run in a separate directory with ambient keys intentionally different; the bundled key must win unless explicitly overridden.

Recipient packaging excludes `docs/`, engineering documents, tests and evaluation scripts. Runtime API contracts remain included; build strips internal `live_verified`/`live_scope` annotations from the packaged catalog. User-facing Markdown links must resolve within the ZIP. The assigned key appears only in `.credentials/tradewind.env`; metadata records `distribution_profile: recipient`. Internal evaluations remain separately managed in the repository/private outputs. Tag v2.0.0rc2 preserves the prior distribution; rc4 uses its own branch/tag and archive names. Historical reports are retained under docs/releases/2.0.0rc2; current validation files describe rc4 only.

Build with `python scripts/build_skill.py --output /private/path/skill.zip --key-file /private/path/tradewind.env --recipient sps`. Verify exclusion rules, credential placement, local links and portable doctor before delivery.

## rc4 execution audit

Explicit execution mode; per-query/company stage coverage; local ledger receipt checks; new live/cached/injected/legacy provenance separated. Missing domain, product hold and enrichment cap are incomplete. Apollo title filters and single-domain people calls; raw safe/role_account normalization preserves catch-all tri-state. Prior rc3 evidence is archived in docs/releases/2.0.0rc3; current evidence must not be inferred from historical replay.
