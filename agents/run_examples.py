"""Run the 10 public example questions and record actual agent usage.

Run this against the live grading-compatible LLM endpoint after the pipeline
has produced output/filings.parquet and output/holdings.parquet.
"""
from __future__ import annotations

import json
from .answer import main

QUESTIONS = [
    "Which manager held the largest Apple position in 2026 Q2?",
    "Which manager added the most Nvidia shares between 2026 Q1 and 2026 Q2?",
    "How many distinct issuers did Renaissance Technologies LLC report in 2026 Q2?",
    "What was the total reported value of Citadel Advisors LLC's holdings in 2026 Q1?",
    "Which managers in the roster filed a 13F-NT instead of a 13F-HR for 2026 Q2?",
    "Did Pershing Square Capital Management report any Microsoft holdings directly in 2026 Q2?",
    "Which manager reported the most call options in 2026 Q2?",
    "What was Third Point LLC's largest position by value in 2026 Q1, and what was it?",
    "Which manager held Tesla in both 2026 Q1 and 2026 Q2, and did the position grow or shrink?",
    "What was the average portfolio value across all managers in 2026 Q3?",
]


def run() -> None:
    for question in QUESTIONS:
        result = main(question)
        print(json.dumps({"question": question, "result": result}, ensure_ascii=False))


if __name__ == "__main__":
    run()
