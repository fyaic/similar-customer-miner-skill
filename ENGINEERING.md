# Engineering · Trade Wind 2.0.0rc2

This describes the current `codex/tradewind-v2` branch. The legacy architecture is available in Git history/main; its Apify/Hunter modules and credential setup are not the v2 live pipeline.

`parser → profiler → tradewind.mine → scoring → exporter` is the live path. Demo/test retains the old offline helpers. The CLI ignores local/secrets YAML and clears legacy credentials. `scripts/run.py` is the portable skill entrypoint. `src/tradewind_core` provides the account-scoped SQLite ledger, host allowlist, no redirects, response redaction and exact-query reuse inherited from sps-overseas-peers.

Discovery is bounded per seed; phrases stay intact, hybrid is optional. Deduplication is exact by domain/name. Product relevance uses normalized token containment in provider descriptions/industries, not an LLM classifier; no synonyms, legal-entity proof or importer proof are implied. Country conflicts are quarantined. Candidates are ranked before bounded enrichment. Unknown/uncorroborated products are excluded by default, retained in raw evidence; missing country remains unknown. Repeated candidates across seeds retain the first association (multi-seed attribution remains a limitation).

Contact title heuristics prioritize procurement/supply-chain, operations, then executive fallback. Unknown/unrelated roles are retained only in raw evidence. Work-email domain and employer association must match. Verification accepts documented `result` and compatible `data` envelopes, checks exact subject and seven-day freshness, and requires explicitly false catch-all. Verification citation/time are separate from the source that supplied the email. Employment/authority always remain unverified.

Scoring uses the requested countries and excludes sampled customs counts from shipping strength/frequency. Grades measure field confidence, not confirmed customer quality. No output grade authorizes outreach. The full three-sheet layout is retained; additional audit columns expose role, product and verification state.

Run `python -m pytest -q tests`. The same outcome-based `tests/test_business_acceptance.py` can run in an archived rc1 checkout; see the release review for paired results and selection bias. `scripts/validate_live.py` is explicitly paid; it reuses a specified ledger and stops on partial results. Raw results remain in ignored outputs. Public summaries contain no customer email addresses or key.

`src/tradewind_core/__init__.py` supplies the runtime/build version. Match pyproject, config, SKILL, both READMEs and release reports when releasing. Build allowlists files and generates MANIFEST/DISTRIBUTION metadata. Never publish credential-bearing packages. Package install checks run in a separate directory with ambient keys intentionally different; the bundled key must win unless explicitly overridden.

Recipient packaging excludes `docs/`, engineering documents, tests and evaluation scripts. Runtime API contracts remain included; build strips internal `live_verified`/`live_scope` annotations from the packaged catalog. User-facing Markdown links must resolve within the ZIP. The assigned key appears only in `.credentials/tradewind.env`; metadata records `distribution_profile: recipient`. Internal evaluations remain separately managed in the repository/private outputs. This packaging-only revision retains runtime version rc2; distinguish artifacts by source revision and SHA-256.

Build with `python scripts/build_skill.py --output /private/path/skill.zip --key-file /private/path/tradewind.env --recipient sps`. Verify exclusion rules, credential placement, local links and portable doctor before delivery.
