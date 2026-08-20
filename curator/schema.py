from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

FILINGS_SCHEMA = pa.schema([
    pa.field("accession_number", pa.string(), nullable=False),
    pa.field("cik", pa.string(), nullable=False),
    pa.field("fund_name", pa.string(), nullable=False),
    pa.field("filing_manager", pa.string(), nullable=False),
    pa.field("form_type", pa.string(), nullable=False),
    pa.field("report_period", pa.date32(), nullable=False),
    pa.field("report_quarter", pa.string(), nullable=False),
    pa.field("filing_date", pa.date32(), nullable=False),
    pa.field("is_amendment", pa.bool_(), nullable=False),
    pa.field("amendment_no", pa.int32(), nullable=True),
    pa.field("amendment_type", pa.string(), nullable=True),
    pa.field("report_type", pa.string(), nullable=False),
    pa.field("form_13f_file_number", pa.string(), nullable=True),
    pa.field("crd_number", pa.string(), nullable=True),
    pa.field("sec_file_number", pa.string(), nullable=True),
    pa.field("other_included_managers_count", pa.int32(), nullable=True),
    pa.field("table_entry_total", pa.int64(), nullable=True),
    pa.field("table_value_total", pa.int64(), nullable=True),
])

HOLDINGS_SCHEMA = pa.schema([
    pa.field("accession_number", pa.string(), nullable=False),
    pa.field("cik", pa.string(), nullable=False),
    pa.field("report_quarter", pa.string(), nullable=False),
    pa.field("name_of_issuer", pa.string(), nullable=False),
    pa.field("title_of_class", pa.string(), nullable=False),
    pa.field("cusip", pa.string(), nullable=False),
    pa.field("figi", pa.string(), nullable=True),
    pa.field("value", pa.int64(), nullable=False),
    pa.field("ssh_prnamt", pa.int64(), nullable=False),
    pa.field("ssh_prnamt_type", pa.string(), nullable=False),
    pa.field("put_call", pa.string(), nullable=True),
    pa.field("investment_discretion", pa.string(), nullable=False),
    pa.field("other_manager", pa.string(), nullable=True),
    pa.field("voting_sole", pa.int64(), nullable=False),
    pa.field("voting_shared", pa.int64(), nullable=False),
    pa.field("voting_none", pa.int64(), nullable=False),
])


def _table(rows: list[dict[str, Any]], schema: pa.Schema) -> pa.Table:
    cols = {field.name: [row.get(field.name) for row in rows] for field in schema}
    return pa.Table.from_pydict(cols, schema=schema)


def write_parquet(
    filings: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Filing order is explicitly deterministic. Holdings already preserve source row order
    # within each filing because docs are parsed in this filing order.
    filings.sort(key=lambda r: (int(r["cik"]), r["report_period"], r["accession_number"]))
    filing_order = {r["accession_number"]: i for i, r in enumerate(filings)}
    indexed = list(enumerate(holdings))
    indexed.sort(key=lambda t: (filing_order[t[1]["accession_number"]], t[0]))
    holdings[:] = [row for _, row in indexed]

    filing_table = _table(filings, FILINGS_SCHEMA)
    holding_table = _table(holdings, HOLDINGS_SCHEMA)

    pq.write_table(
        filing_table,
        output_dir / "filings.parquet",
        compression="snappy",
        use_dictionary=False,
        write_statistics=True,
        version="2.6",
    )
    pq.write_table(
        holding_table,
        output_dir / "holdings.parquet",
        compression="snappy",
        use_dictionary=False,
        write_statistics=True,
        version="2.6",
    )
