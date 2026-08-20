from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .cik import Filer
from .sec_client import SECClient

REPORT_PERIODS = {"2026-03-31", "2026-06-30"}
FILING_DATE_CUTOFF = "2026-08-18"
FORMS = {"13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A"}


@dataclass(frozen=True)
class FilingRef:
    fund_name: str
    cik: str  # unpadded
    accession_number: str  # dashed
    form_type: str
    report_date: str
    filing_date: str
    primary_document: str

    @property
    def cik_padded(self) -> str:
        return self.cik.zfill(10)

    @property
    def accession_nodash(self) -> str:
        return self.accession_number.replace("-", "")


def _recent_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    recent = payload.get("filings", {}).get("recent", {})
    if not recent:
        return []
    keys = list(recent.keys())
    n = len(recent[keys[0]]) if keys else 0
    rows: list[dict[str, Any]] = []
    for i in range(n):
        rows.append({k: recent[k][i] for k in keys})
    return rows


def discover_for_filer(client: SECClient, filer: Filer) -> list[FilingRef]:
    padded = filer.cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded}.json"
    payload = client.get_json(url, f"submissions/CIK{padded}.json")

    refs: list[FilingRef] = []
    for row in _recent_rows(payload):
        form = str(row.get("form", ""))
        report_date = str(row.get("reportDate", ""))
        filing_date = str(row.get("filingDate", ""))
        accession = str(row.get("accessionNumber", ""))
        if form not in FORMS:
            continue
        if report_date not in REPORT_PERIODS:
            continue
        if not filing_date or filing_date > FILING_DATE_CUTOFF:
            continue
        refs.append(
            FilingRef(
                fund_name=filer.fund_name,
                cik=filer.cik,
                accession_number=accession,
                form_type=form,
                report_date=report_date,
                filing_date=filing_date,
                primary_document=str(row.get("primaryDocument", "")),
            )
        )

    refs.sort(key=lambda r: (r.report_date, r.filing_date, r.accession_number))
    return refs


def discover_all(client: SECClient, filers: list[Filer]) -> list[FilingRef]:
    refs: list[FilingRef] = []
    for filer in filers:
        refs.extend(discover_for_filer(client, filer))

    refs.sort(key=lambda r: (int(r.cik), r.report_date, r.filing_date, r.accession_number))
    if len(refs) != 40:
        by_filer: dict[str, int] = {}
        for r in refs:
            by_filer[r.fund_name] = by_filer.get(r.fund_name, 0) + 1
        raise RuntimeError(
            f"Expected 40 in-scope filings, found {len(refs)}. Counts by filer: {by_filer}"
        )
    return refs
