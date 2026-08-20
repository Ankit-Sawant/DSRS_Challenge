from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from .sec_client import SECClient

LOOKUP_URL = "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt"

MANUAL_CIK_OVERRIDES = {
    "Tudor Investment Corp": "923093",
}
LEGAL_SUFFIXES = {
    "LLC", "L L C", "LP", "L P", "LTD", "LIMITED", "INC", "INCORPORATED",
    "CORP", "CORPORATION", "CO", "COMPANY", "PLC", "PL C", "LLP", "L L P",
}


@dataclass(frozen=True)
class Filer:
    fund_name: str
    given_cik: str
    cik: str
    cik_source: str


def _strip_parenthetical(name: str) -> str:
    return re.sub(r"\([^)]*\)", " ", name)


def normalize_name(name: str) -> str:
    s = _strip_parenthetical(name.upper())

    # SEC sometimes appends state identifiers such as /MA.
    s = re.sub(r"/[A-Z]{2}\s*$", " ", s)

    s = s.replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9]+", " ", s)

    tokens = [t for t in s.split() if t]

    # Ignore a leading "THE".
    if tokens and tokens[0] == "THE":
        tokens = tokens[1:]
    # SEC sometimes appends "ET AL" to institutional manager names.
    # Example: "TUDOR INVESTMENT CORP ET AL".
    if len(tokens) >= 2 and tokens[-2:] == ["ET", "AL"]:
        tokens = tokens[:-2]

    multi_suffixes = [
        ("L", "L", "C"),
        ("L", "L", "P"),
        ("P", "L", "C"),
        ("L", "P"),
    ]

    while tokens:
        removed = False

        for suffix in multi_suffixes:
            n = len(suffix)
            if len(tokens) >= n and tuple(tokens[-n:]) == suffix:
                tokens = tokens[:-n]
                removed = True
                break

        if removed:
            continue

        if tokens[-1] in {
            "LLC",
            "LP",
            "LTD",
            "LIMITED",
            "INC",
            "INCORPORATED",
            "CORP",
            "CORPORATION",
            "PLC",
            "LLP",
        }:
            tokens.pop()
            continue

        break

    return " ".join(tokens)
def parse_lookup_text(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        # SEC format is NAME:CIK: ; split from the right because names can contain punctuation.
        parts = raw.rsplit(":", 2)
        if len(parts) < 2:
            continue
        name = parts[0].strip()
        cik = parts[1].strip().lstrip("0") or "0"
        if cik.isdigit():
            rows.append((name, cik))
    return rows


def write_lookup_csv(rows: list[tuple[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["sec_name", "cik"])
        for name, cik in rows:
            writer.writerow([name, cik])


def _similarity(a: str, b: str) -> float:
    at = set(a.split())
    bt = set(b.split())
    jaccard = len(at & bt) / max(1, len(at | bt))
    seq = SequenceMatcher(None, a, b).ratio()
    return 0.65 * jaccard + 0.35 * seq


def reconcile_filers(
    roster: list[dict[str, str]], lookup_rows: list[tuple[str, str]]
) -> list[Filer]:
    normalized_lookup: dict[str, list[tuple[str, str]]] = {}

    for sec_name, cik in lookup_rows:
        normalized_lookup.setdefault(
            normalize_name(sec_name), []
        ).append((sec_name, cik))

    result: list[Filer] = []
    unresolved: list[tuple[dict[str, str], str]] = []

    for row in roster:
        fund_name = row["fund_name"]
        given = row["cik"].lstrip("0") or "0"
        key = normalize_name(fund_name)
        exact = normalized_lookup.get(key, [])

        if exact:
            ciks = sorted({cik for _, cik in exact}, key=int)

            override = MANUAL_CIK_OVERRIDES.get(fund_name)

            if override is not None:
                if override not in ciks:
                    raise RuntimeError(
                        f"Manual CIK override {override} for {fund_name!r} "
                        f"is not present among SEC matches: {ciks}"
                    )
                chosen = override

            elif given in ciks:
                chosen = given

            elif len(ciks) == 1:
                chosen = ciks[0]

            else:
                raise RuntimeError(
                    f"Ambiguous exact SEC name match for {fund_name!r}: {ciks}. "
                    "Document a manual assumption rather than guessing."
                )

            result.append(
                Filer(
                    fund_name,
                    given,
                    chosen,
                    "given" if chosen == given else "corrected",
                )
            )

        else:
            unresolved.append((row, key))

    # Conservative fuzzy fallback for spelling/punctuation drift.
    for row, key in unresolved:
        fund_name = row["fund_name"]
        given = row["cik"].lstrip("0") or "0"

        scored: list[tuple[float, str, str]] = []
        key_tokens = set(key.split())

        for sec_name, cik in lookup_rows:
            candidate = normalize_name(sec_name)
            cand_tokens = set(candidate.split())

            overlap = len(key_tokens & cand_tokens)

            if overlap < max(
                1,
                min(len(key_tokens), len(cand_tokens)) // 2,
            ):
                continue

            score = _similarity(key, candidate)

            if score >= 0.80:
                scored.append((score, sec_name, cik))

        scored.sort(
            key=lambda x: (-x[0], int(x[2]), x[1])
        )

        if not scored:
            raise RuntimeError(
                f"No safe SEC CIK match for {fund_name!r}"
            )

        best = scored[0]

        if (
            len(scored) > 1
            and best[0] - scored[1][0] < 0.04
            and best[2] != scored[1][2]
        ):
            raise RuntimeError(
                f"Ambiguous fuzzy SEC match for {fund_name!r}: "
                f"{best[1]} ({best[2]}, {best[0]:.3f}) vs "
                f"{scored[1][1]} ({scored[1][2]}, {scored[1][0]:.3f})"
            )

        chosen = best[2]

        result.append(
            Filer(
                fund_name,
                given,
                chosen,
                "given" if chosen == given else "corrected",
            )
        )

    result.sort(key=lambda f: int(f.cik))
    return result

def load_and_reconcile(client: SECClient, roster: list[dict[str, str]], cache_dir: Path) -> list[Filer]:
    text = client.get_text(LOOKUP_URL, "cik/cik-lookup-data.txt")
    rows = parse_lookup_text(text)
    write_lookup_csv(rows, cache_dir / "cik" / "cik_lookup.csv")
    return reconcile_filers(roster, rows)
