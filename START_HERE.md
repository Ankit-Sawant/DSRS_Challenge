# DSRS starter integration guide

This bundle is meant to be copied **into your private repository created from the official template**. Do not replace frozen files (`filers.csv`, `verify.py`, `check_submission.py`, `agents/llm.py`, `requirements.txt`, `Dockerfile.base`).

## 1. Copy these files

Copy/merge:

- `main.py`
- `Dockerfile` (candidate-owned; keep the frozen `Dockerfile.base` untouched)
- `curator/` (new package)
- `agents/answer.py` (replace scaffold only)
- `agents/usage_report.py` (new)
- `agents/run_examples.py` (new convenience runner)
- `submission/eda.py`
- `submission/ASSUMPTIONS.md`
- `submission/AI_USAGE.md`
- `submission/DEPENDENCIES.md`
- `tests/`
- `requirements-extra.txt` (empty in this design)
- `DEMO_PLAN.md` (optional local guide)

Keep the template's original `agents/llm.py` and all other frozen files. This bundle intentionally does not include `filers.csv` or `agents/llm.py`.

## 2. Run the data pipeline

```bash
python main.py --user-agent "Your Name netid@illinois.edu"
python submission/eda.py
python verify.py
```

Then run the pipeline a second time and compare the Parquet hashes:

```bash
shasum -a 256 output/filings.parquet output/holdings.parquet
python main.py --user-agent "Your Name netid@illinois.edu"
shasum -a 256 output/filings.parquet output/holdings.parquet
cat output/fetch_manifest.json
```

The two Parquet hashes must be unchanged. The second run should show mostly/all cache hits.

## 3. Test without an LLM

```bash
python -m unittest discover -s tests -v
LLM_MODE=mock python -m agents.answer "which manager held the largest Apple position in 2026 Q2?"
```

Mock mode should return a valid null response. It tests wiring, not accuracy.

## 4. Test with a live OpenAI-compatible model

Use the template `.env.example`; do not commit `.env`.

```bash
cp .env.example .env
# fill LLM_BASE_URL / LLM_API_KEY / optional LLM_MODEL
python -m agents.llm
python -m agents.answer "which manager held the largest Apple position in 2026 Q2?"
```

Run every question in `docs/questions-examples.md`. `output/agent_usage.json` is updated by the agent; inspect it and commit a representative live run.

## 5. Before submission

```bash
python verify.py
python check_submission.py

docker build -f Dockerfile.base -t curator-base .
docker build -t curator-submission .
docker run --rm \
  -v "$PWD/output:/app/output" \
  -v "$PWD/.cache:/app/.cache" \
  curator-submission --user-agent "Your Name netid@illinois.edu"
```

Then record a sub-3-minute live demo, upload it to Illinois MediaSpace as Unlisted, fill `submission/SUBMISSION.md`, commit `output/`, push, and confirm `dsrsBOT` has Read access.

## Recommended order

1. Get `output/filers.csv` + exactly 40 raw filing paths correct.
2. Run EDA and inspect the actual evidence rather than accepting the generic conclusions.
3. Get `verify.py` passing and confirm deterministic hashes.
4. Tune the agent on the example questions; fix retrieval patterns before prompt wording.
5. Only then consider the optional bonuses.

## Docker note

The template Dockerfile only copies `main.py` and `agents/`. Because this starter adds a `curator/` package, use the included candidate-owned `Dockerfile`; otherwise the grader container will fail to import the pipeline modules. Do not modify `Dockerfile.base`.

## Before the final agent usage run

Delete any tuning-run usage file so the committed artifact reflects the required public examples, then run them against the live endpoint:

```bash
rm -f output/agent_usage.json
python -m agents.run_examples
```

Inspect every answer before committing `output/agent_usage.json`. The script is a convenience only; the grader still calls `agents.answer.main(question)` directly.

See `DEMO_PLAN.md` for a compact Chapter 5 recording flow.
