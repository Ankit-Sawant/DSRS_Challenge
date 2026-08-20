# AI usage

I used ChatGPT as a development assistant for this screening challenge. I remain responsible for the implementation and verified the generated suggestions against the challenge documentation and code.

AI assistance included:

- translating the chapter rubrics and output schema into an implementation checklist;
- reviewing SEC/EDGAR endpoint conventions, caching/rate-limit edge cases, XML namespace handling, notice filings, and deterministic Parquet requirements;
- drafting and reviewing parts of the Python pipeline, parser, EDA, tests, and the read-only SQL-backed agent architecture;
- identifying security checks for model-generated SQL and source-attribution validation;
- suggesting test cases and a demo flow.

I manually reviewed and adapted the generated code. Before submission I will run the repository's frozen `verify.py` and `check_submission.py`, inspect the EDA evidence, run the pipeline twice to confirm byte-identical output, and test the agent against the public example questions. I will update this paragraph so it states only checks I actually completed. I am responsible for understanding and being able to modify every component during the walkthrough.
