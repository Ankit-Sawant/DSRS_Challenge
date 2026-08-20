#!/usr/bin/env python3
"""Chapter 2 EDA for the DSRS 13F challenge.

FINDINGS
--------
This script is evidence-first: it scans the Chapter 1 XML, prints concrete counts and
accession examples, and (when the pipeline cache is present) compares cover-page
summary totals with the information table actually downloaded.

The parser implications tested here are:
1. XML namespace prefixes cannot be hard-coded; match by local name/namespace.
2. A notice can have a cover page but zero infoTable elements, so filings and holdings
   need separate grains.
3. CUSIP is a 9-character string; duplicates inside one filing are legitimate and must
   not be deduplicated.
4. putCall, figi, and otherManager are optional/variable and must be nullable.
5. Declared tableEntryTotal/tableValueTotal are validation evidence, not a reason to
   discard or synthesize rows.

Run from the repository root after Chapter 1:
    python submission/eda.py
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
FILINGS_DIR = ROOT / "output" / "filings"
CACHE_ARCHIVE = ROOT / ".cache" / "sec" / "archive"

# Every required schema field mapped to its source. "derived" means computed by us,
# not copied from an XML element.
SCHEMA_MAPPING = {
    # filings.parquet
    "filings.accession_number": "submissions API accessionNumber",
    "filings.cik": "verified roster/SEC CIK, formatted to 10 characters",
    "filings.fund_name": "supplied filers.csv fund_name",
    "filings.filing_manager": "coverPage/filingManager/name",
    "filings.form_type": "submissions API form",
    "filings.report_period": "coverPage/reportCalendarOrQuarter (fallback periodOfReport)",
    "filings.report_quarter": "derived from report_period",
    "filings.filing_date": "submissions API filingDate",
    "filings.is_amendment": "coverPage/isAmendment; form suffix /A is a consistency check",
    "filings.amendment_no": "coverPage/amendmentNo",
    "filings.amendment_type": "coverPage/amendmentType",
    "filings.report_type": "coverPage/reportType",
    "filings.form_13f_file_number": "coverPage/form13FFileNumber",
    "filings.crd_number": "coverPage/crdNumber",
    "filings.sec_file_number": "coverPage/secFileNumber",
    "filings.other_included_managers_count": "summaryPage/otherIncludedManagersCount",
    "filings.table_entry_total": "summaryPage/tableEntryTotal (declared count)",
    "filings.table_value_total": "summaryPage/tableValueTotal (declared total value)",
    # holdings.parquet
    "holdings.accession_number": "parent filing accession_number",
    "holdings.cik": "parent filing CIK (denormalized)",
    "holdings.report_quarter": "parent filing report_quarter (denormalized)",
    "holdings.name_of_issuer": "infoTable/nameOfIssuer",
    "holdings.title_of_class": "infoTable/titleOfClass",
    "holdings.cusip": "infoTable/cusip",
    "holdings.figi": "infoTable/figi (optional)",
    "holdings.value": "infoTable/value (whole USD for in-scope 2026 filings)",
    "holdings.ssh_prnamt": "infoTable/shrsOrPrnAmt/sshPrnamt",
    "holdings.ssh_prnamt_type": "infoTable/shrsOrPrnAmt/sshPrnamtType",
    "holdings.put_call": "infoTable/putCall (optional)",
    "holdings.investment_discretion": "infoTable/investmentDiscretion",
    "holdings.other_manager": "infoTable/otherManager (optional reference, not a name)",
    "holdings.voting_sole": "infoTable/votingAuthority/Sole",
    "holdings.voting_shared": "infoTable/votingAuthority/Shared",
    "holdings.voting_none": "infoTable/votingAuthority/None",
}


def local_name(element: etree._Element) -> str:
    return etree.QName(element).localname


def parse(path: Path) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False, huge_tree=True)
    return etree.parse(str(path), parser).getroot()


def descendants(root: etree._Element, name: str) -> list[etree._Element]:
    return root.xpath(f".//*[local-name()='{name}']")


def child_text(node: etree._Element, name: str) -> str | None:
    found = node.xpath(f"./*[local-name()='{name}']")
    if not found or found[0].text is None:
        return None
    return found[0].text.strip()


def first_text(root: etree._Element, name: str) -> str | None:
    found = descendants(root, name)
    if not found or found[0].text is None:
        return None
    return found[0].text.strip()


def accession_from_path(path: Path) -> str:
    raw = path.stem
    # 000123456726000123 -> 0001234567-26-000123
    if len(raw) == 18 and raw.isdigit():
        return f"{raw[:10]}-{raw[10:12]}-{raw[12:]}"
    return raw


def iter_output_xml() -> Iterable[Path]:
    if not FILINGS_DIR.exists():
        raise SystemExit("output/filings/ not found. Run main.py first.")
    yield from sorted(FILINGS_DIR.glob("*/*.xml"), key=lambda p: (int(p.parent.name), p.name))


def find_primary_in_cache(path: Path) -> Path | None:
    """Find a cached primary document for this output accession, if Chapter 1 cache exists."""
    accession_nodash = path.stem
    cik = path.parent.name
    filing_dir = CACHE_ARCHIVE / cik / accession_nodash
    if not filing_dir.exists():
        return None
    xmls = sorted(filing_dir.glob("*.xml"))
    if not xmls:
        return None
    # Primary XML contains coverPage; information table normally does not.
    for candidate in xmls:
        try:
            root = parse(candidate)
        except Exception:
            continue
        if descendants(root, "coverPage"):
            return candidate
    return None


def print_mapping() -> None:
    print("\n=== Schema mapping ===")
    for field, source in SCHEMA_MAPPING.items():
        print(f"{field:42s} <- {source}")


def main() -> int:
    paths = list(iter_output_xml())
    if not paths:
        raise SystemExit("No XML files under output/filings/. Run main.py first.")

    print(f"Scanned {len(paths)} Chapter-1 XML files")
    print_mapping()

    namespace_uris: Counter[str] = Counter()
    namespace_prefixes: defaultdict[str, set[str]] = defaultdict(set)
    root_names: Counter[str] = Counter()
    info_counts: dict[str, int] = {}
    duplicate_examples: list[tuple[str, str, int]] = []
    cins_examples: list[tuple[str, str]] = []
    put_call_values: Counter[str] = Counter()
    files_with_figi = 0
    files_with_other_manager = 0
    files_with_info = 0
    files_without_info = 0
    malformed_cusips: list[tuple[str, str]] = []

    # Declared-vs-actual comparisons need the primary cover XML. Chapter 1 caches it;
    # the script remains useful if .cache has been removed, but reports the limitation.
    cover_checked = 0
    entry_mismatches: list[tuple[str, int, int]] = []
    value_mismatches: list[tuple[str, int, int]] = []
    notice_examples: list[str] = []

    for path in paths:
        accession = accession_from_path(path)
        root = parse(path)
        root_names[local_name(root)] += 1

        for prefix, uri in (root.nsmap or {}).items():
            if uri:
                namespace_uris[str(uri)] += 1
                namespace_prefixes[str(uri)].add("<default>" if prefix is None else str(prefix))

        info_rows = descendants(root, "infoTable")
        info_counts[accession] = len(info_rows)
        if info_rows:
            files_with_info += 1
        else:
            files_without_info += 1

        cusips: list[str] = []
        file_has_figi = False
        file_has_other = False
        for row in info_rows:
            cusip = child_text(row, "cusip") or ""
            cusips.append(cusip)
            if len(cusip) != 9:
                malformed_cusips.append((accession, cusip))
            if cusip and cusip[0].isalpha() and len(cins_examples) < 10:
                cins_examples.append((accession, cusip))

            put_call = child_text(row, "putCall")
            if put_call is not None:
                put_call_values[put_call] += 1
            if child_text(row, "figi") is not None:
                file_has_figi = True
            if child_text(row, "otherManager") is not None:
                file_has_other = True

        for cusip, count in Counter(cusips).items():
            if cusip and count > 1 and len(duplicate_examples) < 15:
                duplicate_examples.append((accession, cusip, count))

        files_with_figi += int(file_has_figi)
        files_with_other_manager += int(file_has_other)

        primary_path = find_primary_in_cache(path)
        if primary_path is None:
            # For a notice, the committed output is itself the primary XML.
            if descendants(root, "coverPage"):
                primary_path = path
            else:
                continue

        primary = parse(primary_path)
        cover_checked += 1
        report_type = first_text(primary, "reportType") or ""
        if "NOTICE" in report_type.upper():
            notice_examples.append(accession)

        declared_entries_text = first_text(primary, "tableEntryTotal")
        declared_value_text = first_text(primary, "tableValueTotal")
        if declared_entries_text is not None:
            declared_entries = int(declared_entries_text.replace(",", ""))
            actual_entries = len(info_rows)
            if declared_entries != actual_entries:
                entry_mismatches.append((accession, declared_entries, actual_entries))

        if declared_value_text is not None and info_rows:
            declared_value = int(declared_value_text.replace(",", ""))
            actual_value = sum(int((child_text(row, "value") or "0").replace(",", "")) for row in info_rows)
            if declared_value != actual_value:
                value_mismatches.append((accession, declared_value, actual_value))

    print("\n=== XML shape / namespace evidence ===")
    print("Root element names:", dict(root_names))
    print(f"Files with infoTable rows: {files_with_info}; without: {files_without_info}")
    for uri, count in namespace_uris.most_common():
        print(f"namespace {uri!r}: seen on {count} roots; prefixes={sorted(namespace_prefixes[uri])}")

    print("\n=== Holding-level edge cases ===")
    print(f"Files containing FIGI: {files_with_figi}/{len(paths)}")
    print(f"Files containing otherManager references: {files_with_other_manager}/{len(paths)}")
    print("putCall values/capitalization:", dict(put_call_values))
    print(f"Malformed CUSIPs (length != 9): {len(malformed_cusips)}")
    if malformed_cusips:
        print("  examples:", malformed_cusips[:5])
    print(f"Files/CUSIPs with duplicate entries (sample count): {len(duplicate_examples)}")
    for ex in duplicate_examples[:5]:
        print(f"  duplicate: accession={ex[0]} cusip={ex[1]} rows={ex[2]}")
    if cins_examples:
        print("CINS examples (letter-leading 9-char identifiers):")
        for accession, cusip in cins_examples[:5]:
            print(f"  {accession}: {cusip}")

    print("\n=== Cover-page declarations vs downloaded table ===")
    print(f"Cover pages available for comparison: {cover_checked}/{len(paths)}")
    print(f"tableEntryTotal mismatches: {len(entry_mismatches)}")
    for accession, declared, actual in entry_mismatches[:5]:
        print(f"  {accession}: declared={declared}, actual_infoTable_rows={actual}")
    print(f"tableValueTotal mismatches: {len(value_mismatches)}")
    for accession, declared, actual in value_mismatches[:5]:
        print(f"  {accession}: declared={declared}, sum_infoTable_value={actual}")
    print(f"Notice filings observed from available cover pages: {len(notice_examples)}")
    if notice_examples:
        print("  notice examples:", notice_examples[:5])

    print("\n=== Conclusions for the parser ===")
    print("- Match XML by local name/namespace, not a literal prefix.")
    print("- Keep a filing table separate from holdings so notice filings do not disappear.")
    print("- Preserve every infoTable row and source order; duplicate CUSIPs are evidence, not dirt.")
    print("- Keep CUSIP as a 9-character string; letter-leading CINS values are valid.")
    print("- Treat putCall, figi, and otherManager as optional nullable fields.")
    if entry_mismatches or value_mismatches:
        print("- At least one cover-page declaration differs from parsed table evidence; validate and surface it, do not silently 'fix' rows.")
    else:
        print("- In the files compared here, declared totals matched parsed table evidence; retain the comparison as a validation check rather than assuming they always will.")
    if cover_checked < len(paths):
        print("- Some primary cover XML was unavailable because .cache was absent; rerun main.py before EDA for full cover-vs-table evidence.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
