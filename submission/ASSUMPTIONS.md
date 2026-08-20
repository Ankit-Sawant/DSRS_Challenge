# Assumptions and design decisions

## Source

- The supplied **fund name is authoritative when a supplied CIK disagrees with SEC's lookup**, so CIK reconciliation matches names first and records `given` vs `corrected` in `output/filers.csv`.
- I use the SEC submissions endpoint for discovery and filter on `reportDate` (`2026-03-31` and `2026-06-30`), then apply the inclusive `filingDate <= 2026-08-18` cutoff and the four in-scope 13F form types.
- For each filing I use EDGAR archive `index.json` to locate XML documents. A holdings filing normally has separate cover/primary XML and information-table XML. To satisfy the Chapter 1 one-file-per-filing output convention, `output/filings/{cik}/{accession}.xml` stores the **information-table XML for 13F-HR** and the **primary/cover XML for 13F-NT**. Both documents are retained in `.cache/sec/archive/...` for parsing and EDA. This is the main interpretation I would confirm with the challenge team if clarification arrives.
- Cache entries are treated as immutable for the challenge's fixed report periods and cutoff. A second run reads those bytes instead of refetching them.

## Structure

- Namespace prefixes are not trusted. XML elements are selected by local name so default namespaces and filer-specific prefixes parse the same way.
- Holding rows are never deduplicated. Source information-table order is preserved within each filing; only the deterministic filing order is imposed across filings.
- `table_entry_total` and `table_value_total` are the manager-declared cover-page values. They are not recomputed to replace the declarations.
- `13F-NT` produces one filing row, zero holding rows, and null `table_entry_total`/`table_value_total`.
- Amendment fields are parsed generically even though the challenge slice is expected not to contain an in-scope amendment.

## Agent

- The agent uses an in-memory SQLite copy of the committed Parquet files. SQLite is put in `query_only` mode and a connection authorizer rejects write/DDL/PRAGMA operations.
- The model never receives the full holdings dataset. It first proposes a bounded read-only SQL query; the code validates and executes it; only the small result set is sent back for answer formatting.
- Model-produced SQL and source selections are untrusted. SQL is syntax/keyword constrained and every returned source must match an accession already present in the SQL result.
- If the query is unsupported, the result is empty, model output is invalid, no supporting accession can be established, or execution fails, the agent returns `{"answer": null, "unit": "NONE", "sources": []}` and logs the reason to stderr.
- The design uses at most two model calls for a normal answer: one retrieval-plan call and one answer-formatting call.

## Known limitations / deliberate non-bonus scope

- The core pipeline does **not** perform Bonus 1 notice-attribution recovery or Bonus 2 external CUSIP validation. I would only add these after the 30-point core passes `verify.py`, repeatability checks, and agent tests.
- Free-text issuer matching in agent-generated SQL is necessarily approximate because issuer names in 13F filings are not standardized. CUSIP-based comparisons are preferred when the question identifies a security unambiguously.
