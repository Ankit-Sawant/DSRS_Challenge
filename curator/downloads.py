from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .discovery import FilingRef
from .sec_client import SECClient


@dataclass(frozen=True)
class FilingDocuments:
    ref: FilingRef
    primary_path: Path
    information_table_path: Path | None
    output_path: Path


def _items(index_payload: dict[str, Any]) -> list[dict[str, Any]]:
    directory = index_payload.get("directory", {})
    items = directory.get("item", [])
    return items if isinstance(items, list) else []


def _choose_primary(ref: FilingRef, names: list[str]) -> str:
    if ref.primary_document:
        if ref.primary_document in names and ref.primary_document.lower().endswith(".xml"):
            return ref.primary_document
        # EDGAR often lists HTML as primaryDocument while an XML sibling has same stem.
        stem = ref.primary_document.rsplit(".", 1)[0]
        sibling = stem + ".xml"
        if sibling in names:
            return sibling

    xmls = [n for n in names if n.lower().endswith(".xml")]
    primaryish = [n for n in xmls if "primary" in n.lower()]
    if primaryish:
        return sorted(primaryish)[0]
    if not xmls:
        raise RuntimeError(f"No XML document found for {ref.accession_number}")
    return sorted(xmls)[0]


def _choose_information_table(primary: str, items: list[dict[str, Any]]) -> str | None:
    candidates = [it for it in items if str(it.get("name", "")).lower().endswith(".xml")]
    candidates = [it for it in candidates if str(it.get("name")) != primary]
    if not candidates:
        return None

    def score(it: dict[str, Any]) -> tuple[int, int, str]:
        name = str(it.get("name", ""))
        lower = name.lower()
        hint = 0
        if "info" in lower:
            hint += 10
        if "table" in lower:
            hint += 5
        if "13f" in lower:
            hint += 2
        try:
            size = int(it.get("size") or 0)
        except Exception:
            size = 0
        return (hint, size, name)

    candidates.sort(key=score, reverse=True)
    return str(candidates[0]["name"])


def download_filing(
    client: SECClient,
    ref: FilingRef,
    output_dir: Path,
    cache_dir: Path,
) -> FilingDocuments:
    accession_dir = ref.accession_nodash
    base = f"https://www.sec.gov/Archives/edgar/data/{ref.cik}/{accession_dir}"
    rel = f"archive/{ref.cik}/{accession_dir}"
    index_payload = client.get_json(f"{base}/index.json", f"{rel}/index.json")
    items = _items(index_payload)
    names = [str(it.get("name", "")) for it in items]

    primary_name = _choose_primary(ref, names)
    is_notice = ref.form_type.startswith("13F-NT")
    info_name = None if is_notice else _choose_information_table(primary_name, items)

    primary_bytes = client.get_bytes(f"{base}/{primary_name}", f"{rel}/{primary_name}")
    primary_path = cache_dir / rel / primary_name

    info_path: Path | None = None
    info_bytes: bytes | None = None
    if info_name is not None:
        info_bytes = client.get_bytes(f"{base}/{info_name}", f"{rel}/{info_name}")
        info_path = cache_dir / rel / info_name

    if not is_notice and info_bytes is None:
        raise RuntimeError(f"Holdings filing has no information-table XML: {ref.accession_number}")

    # Assumption documented in submission/ASSUMPTIONS.md:
    # output/filings stores the information-table XML for holdings filings, and the
    # primary XML for notices. Both raw XML documents remain in .cache for parsing.
    output_path = output_dir / "filings" / ref.cik / f"{ref.accession_nodash}.xml"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    chosen = primary_bytes if is_notice else info_bytes
    assert chosen is not None
    output_path.write_bytes(chosen)

    return FilingDocuments(ref, primary_path, info_path, output_path)


def download_all(
    client: SECClient,
    refs: list[FilingRef],
    output_dir: Path,
    cache_dir: Path,
) -> list[FilingDocuments]:
    docs = [download_filing(client, ref, output_dir, cache_dir) for ref in refs]
    return docs
