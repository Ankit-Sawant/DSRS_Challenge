from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from lxml import etree

from .downloads import FilingDocuments


def _root(path: Path) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False, remove_blank_text=False, huge_tree=True)
    return etree.parse(str(path), parser).getroot()


def _nodes(node: etree._Element, local_name: str) -> list[etree._Element]:
    return node.xpath(f".//*[local-name()='{local_name}']")


def _first_text(node: etree._Element, local_name: str, default: str | None = None) -> str | None:
    found = _nodes(node, local_name)
    if not found:
        return default
    text = found[0].text
    return text.strip() if text is not None else default


def _child_text(node: etree._Element, local_name: str, default: str | None = None) -> str | None:
    found = node.xpath(f"./*[local-name()='{local_name}']")
    if not found:
        return default
    text = found[0].text
    return text.strip() if text is not None else default


def _desc_text(node: etree._Element, local_name: str, default: str | None = None) -> str | None:
    found = node.xpath(f".//*[local-name()='{local_name}']")
    if not found:
        return default
    text = found[0].text
    return text.strip() if text is not None else default


def _int_or_none(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value.replace(",", ""))


def _bool(value: str | None, fallback: bool = False) -> bool:
    if value is None:
        return fallback
    return value.strip().lower() in {"true", "1", "yes", "y"}


def _parse_mmddyyyy(value: str) -> date:
    return datetime.strptime(value, "%m-%d-%Y").date()


def _quarter(d: date) -> str:
    q = ((d.month - 1) // 3) + 1
    return f"{d.year}Q{q}"


def parse_filing(doc: FilingDocuments) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ref = doc.ref
    primary = _root(doc.primary_path)

    cover_nodes = primary.xpath(".//*[local-name()='coverPage']")
    if not cover_nodes:
        raise RuntimeError(f"Missing coverPage in {ref.accession_number}")
    cover = cover_nodes[0]

    manager_nodes = cover.xpath("./*[local-name()='filingManager']")
    filing_manager = _desc_text(manager_nodes[0], "name") if manager_nodes else None
    if not filing_manager:
        raise RuntimeError(f"Missing filing manager name in {ref.accession_number}")

    report_period_text = _child_text(cover, "reportCalendarOrQuarter") or _first_text(primary, "periodOfReport")
    if not report_period_text:
        raise RuntimeError(f"Missing report period in {ref.accession_number}")
    report_period = _parse_mmddyyyy(report_period_text)

    report_type = _child_text(cover, "reportType")
    if not report_type:
        raise RuntimeError(f"Missing reportType in {ref.accession_number}")

    is_amendment = ref.form_type.endswith("/A")
    amendment_no = _int_or_none(_child_text(cover, "amendmentNo"))
    amendment_type = _child_text(cover, "amendmentType")
    if amendment_type:
        amendment_type = amendment_type.strip().upper()

    summary_nodes = primary.xpath(".//*[local-name()='summaryPage']")
    summary = summary_nodes[0] if summary_nodes else None

    filing_row: dict[str, Any] = {
        "accession_number": ref.accession_number,
        "cik": ref.cik.zfill(10),
        "fund_name": ref.fund_name,
        "filing_manager": filing_manager,
        "form_type": ref.form_type,
        "report_period": report_period,
        "report_quarter": _quarter(report_period),
        "filing_date": date.fromisoformat(ref.filing_date),
        "is_amendment": is_amendment,
        "amendment_no": amendment_no,
        "amendment_type": amendment_type,
        "report_type": report_type,
        "form_13f_file_number": _child_text(cover, "form13FFileNumber"),
        "crd_number": _child_text(cover, "crdNumber"),
        "sec_file_number": _child_text(cover, "secFileNumber"),
        "other_included_managers_count": _int_or_none(_child_text(summary, "otherIncludedManagersCount")) if summary is not None else None,
        "table_entry_total": _int_or_none(_child_text(summary, "tableEntryTotal")) if summary is not None else None,
        "table_value_total": _int_or_none(_child_text(summary, "tableValueTotal")) if summary is not None else None,
    }

    holdings: list[dict[str, Any]] = []
    if doc.information_table_path is None:
        return filing_row, holdings

    info_root = _root(doc.information_table_path)
    for info in info_root.xpath(".//*[local-name()='infoTable']"):
        issuer = _child_text(info, "nameOfIssuer")
        title = _child_text(info, "titleOfClass")
        cusip = _child_text(info, "cusip")
        value = _int_or_none(_child_text(info, "value"))
        discretion = _child_text(info, "investmentDiscretion")
        shrs_nodes = info.xpath("./*[local-name()='shrsOrPrnAmt']")
        vote_nodes = info.xpath("./*[local-name()='votingAuthority']")
        shrs = shrs_nodes[0] if shrs_nodes else info
        vote = vote_nodes[0] if vote_nodes else info

        row = {
            "accession_number": ref.accession_number,
            "cik": ref.cik.zfill(10),
            "report_quarter": filing_row["report_quarter"],
            "name_of_issuer": issuer,
            "title_of_class": title,
            "cusip": cusip,
            "figi": _child_text(info, "figi"),
            "value": value,
            "ssh_prnamt": _int_or_none(_child_text(shrs, "sshPrnamt")),
            "ssh_prnamt_type": _child_text(shrs, "sshPrnamtType"),
            "put_call": _child_text(info, "putCall"),
            "investment_discretion": discretion,
            "other_manager": _child_text(info, "otherManager"),
            "voting_sole": _int_or_none(_child_text(vote, "Sole")),
            "voting_shared": _int_or_none(_child_text(vote, "Shared")),
            "voting_none": _int_or_none(_child_text(vote, "None")),
        }

        required = [
            "name_of_issuer", "title_of_class", "cusip", "value", "ssh_prnamt",
            "ssh_prnamt_type", "investment_discretion", "voting_sole",
            "voting_shared", "voting_none",
        ]
        missing = [k for k in required if row[k] is None]
        if missing:
            raise RuntimeError(f"Missing required holding fields {missing} in {ref.accession_number}")
        if len(str(cusip)) != 9:
            raise RuntimeError(f"CUSIP must be 9 characters, got {cusip!r} in {ref.accession_number}")
        holdings.append(row)

    return filing_row, holdings


def parse_all(docs: list[FilingDocuments]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    filings: list[dict[str, Any]] = []
    holdings: list[dict[str, Any]] = []
    for doc in docs:
        filing, rows = parse_filing(doc)
        filings.append(filing)
        holdings.extend(rows)
    return filings, holdings
