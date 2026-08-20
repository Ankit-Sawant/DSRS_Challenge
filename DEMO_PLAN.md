# 3-minute demo plan

Keep the video under three minutes. The goal is to prove the pipeline works from a clean state, the generated dataset passes validation, and the agent can answer from the structured data.

## Before recording

- Put your name, NetID, and eventual MediaSpace URL in `submission/SUBMISSION.md`.
- Make sure `SEC_USER_AGENT` contains a real name and email address.
- Make sure the grading-compatible LLM endpoint variables are configured.
- Practice the commands so you can narrate while they run.
- Do **not** expose API keys or other secrets in the terminal or video.

## Suggested recording flow

### 0:00-0:20 — What the project does

Briefly show the repository and say that the pipeline starts from the manager roster, resolves/validates CIKs, discovers the two in-scope 13F report periods, downloads EDGAR source XML responsibly, parses it into two deterministic Parquet tables, validates the output, and serves answers through a read-only agent.

### 0:20-1:20 — Cold pipeline run

In the terminal:

```bash
rm -rf output .cache
mkdir -p output
python main.py
```

While it runs, point out that requests are rate-limited, retried, and cached; the manager name is treated as authoritative when checking the roster CIK; and notices are preserved as filing rows even though they have no holdings.

Then show:

```bash
python verify.py
```

If time permits, immediately run `python main.py` a second time and mention that SEC responses now come from cache and the Parquet files remain byte-identical.

### 1:20-1:50 — Show the structured data

Show a quick schema/sample using Python or DuckDB/SQLite. Emphasize the two-table design:

- `filings.parquet`: one row per filing, including notices and filing-level metadata.
- `holdings.parquet`: one row per information-table row; duplicate CUSIPs are preserved because they can represent distinct reported positions.

### 1:50-2:40 — Agent live question

Run a public example question, for example:

```bash
python -m agents.answer "Which manager reported the largest position in Apple by value in 2026 Q2?"
```

Show the JSON answer and source accession(s). Explain that the model never receives the full holdings dataset. It proposes a bounded read-only SQL query, the application validates/executes it locally, and only the small result is sent back for answer formatting. Accessions are derived by code from query results rather than trusted from model text.

Optionally show an unsupported-period question:

```bash
python -m agents.answer "What was the average portfolio value across all managers in 2026 Q3?"
```

and show the explicit null answer.

### 2:40-2:58 — Close

Show `submission/ASSUMPTIONS.md` and `submission/AI_USAGE.md`. Mention one judgment call you documented, such as using the information-table XML as the committed raw file for holding reports while retaining the primary document in the cache for filing-level metadata/EDA.
