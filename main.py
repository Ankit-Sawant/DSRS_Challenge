#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import shutil
from pathlib import Path

from curator.cik import Filer, load_and_reconcile
from curator.discovery import discover_all
from curator.downloads import download_all
from curator.parser import parse_all
from curator.schema import write_parquet
from curator.sec_client import SECClient

ROOT = Path(__file__).resolve().parent
FILERS = ROOT / "filers.csv"
OUTPUT = ROOT / "output"
CACHE = ROOT / ".cache" / "sec"
UA_PATTERN = re.compile(r"^\S.*\s+[^@\s]+@[^@\s]+\.[a-z]{2,}\s*$", re.I)


def load_filers() -> list[dict[str, str]]:
    with FILERS.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_verified_filers(filers: list[Filer], output: Path) -> None:
    path = output / "filers.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["fund_name", "cik", "cik_source"])
        for filer in sorted(filers, key=lambda f: int(f.cik)):
            writer.writerow([filer.fund_name, filer.cik, filer.cik_source])


def run(user_agent: str, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    cache = CACHE
    roster = load_filers()

    with SECClient(user_agent, cache) as client:
        filers = load_and_reconcile(client, roster, cache)
        write_verified_filers(filers, output)

        refs = discover_all(client, filers)
        raw_output = output / "filings"
        if raw_output.exists():
            shutil.rmtree(raw_output)
        docs = download_all(client, refs, output, cache)
        filings, holdings = parse_all(docs)

        if len(filings) != 40:
            raise RuntimeError(f"Expected 40 filing rows, parsed {len(filings)}")

        write_parquet(filings, holdings, output)

        manifest = {
            "in_scope_filings": len(refs),
            "filing_rows": len(filings),
            "holding_rows": len(holdings),
            "cache_hits": client.stats.hits,
            "cache_misses": client.stats.misses,
            "network_requests": client.stats.requests,
        }
        (output / "fetch_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    print(
        f"Built {len(filings)} filings and {len(holdings)} holdings; "
        f"cache hits={manifest['cache_hits']} misses={manifest['cache_misses']}",
        file=sys.stderr,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the DSRS 13F dataset")
    ap.add_argument("--user-agent", required=True, help='SEC User-Agent: "First Last email@illinois.edu"')
    ap.add_argument("--output", type=Path, default=OUTPUT)
    args = ap.parse_args()

    if not UA_PATTERN.match(args.user_agent):
        sys.exit(
            "invalid --user-agent. SEC requires a contact address.\n"
            'example: python main.py --user-agent "Jane Doe jdoe@illinois.edu"'
        )

    run(args.user_agent, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
