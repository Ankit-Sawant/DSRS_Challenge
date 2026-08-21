# AI usage

I used ChatGPT as a development assistant for this screening challenge. I remain responsible for the implementation and verified AI-assisted suggestions against the challenge documentation, repository code, generated data, and test results.

AI assistance included:

- translating the chapter rubrics and output schema into an implementation checklist;
- reviewing SEC/EDGAR endpoint conventions, caching and rate-limit edge cases, XML namespace handling, notice filings, and deterministic Parquet requirements;
- drafting and reviewing parts of the Python pipeline, parser, EDA, tests, and read-only SQL-backed agent architecture;
- debugging CIK reconciliation and ambiguous filer-name matching;
- reviewing security controls for model-generated SQL and source-attribution validation;
- debugging the natural-language agent against the public example questions;
- suggesting test cases and a demonstration flow.

I manually reviewed and adapted the generated code. I ran the frozen `verify.py`, inspected the EDA evidence, ran the pipeline twice and confirmed byte-identical Parquet output, ran the repository unit tests, and tested the agent against the public example questions. I am responsible for understanding and being able to explain or modify every component during the walkthrough.
