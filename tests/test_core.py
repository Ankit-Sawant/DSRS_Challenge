from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from curator.cik import reconcile_filers
from curator.discovery import discover_for_filer
from curator.cik import Filer
from curator.downloads import FilingDocuments
from curator.parser import parse_filing


class FakeClient:
    def __init__(self, payload):
        self.payload = payload

    def get_json(self, url, cache_key):
        return self.payload


class TestCIKReconciliation(unittest.TestCase):
    def test_name_wins_when_given_cik_is_wrong(self):
        roster = [{"fund_name": "Situational Awareness LP", "cik": "1697748"}]
        lookup = [("SITUATIONAL AWARENESS LP", "2045724")]
        result = reconcile_filers(roster, lookup)
        self.assertEqual(result[0].cik, "2045724")
        self.assertEqual(result[0].cik_source, "corrected")


class TestDiscovery(unittest.TestCase):
    def test_filters_report_period_form_and_cutoff(self):
        payload = {
            "filings": {
                "recent": {
                    "form": ["13F-HR", "13F-HR", "13F-HR", "10-K", "13F-NT"],
                    "reportDate": ["2026-03-31", "2026-06-30", "2025-12-31", "2026-06-30", "2026-06-30"],
                    "filingDate": ["2026-05-10", "2026-08-19", "2026-02-10", "2026-08-10", "2026-08-14"],
                    "accessionNumber": [
                        "0000000001-26-000001", "0000000001-26-000002",
                        "0000000001-26-000003", "0000000001-26-000004",
                        "0000000001-26-000005",
                    ],
                    "primaryDocument": ["a.xml", "b.xml", "c.xml", "d.xml", "e.xml"],
                }
            }
        }
        filer = Filer("Example", "1", "1", "given")
        refs = discover_for_filer(FakeClient(payload), filer)
        self.assertEqual([r.accession_number for r in refs], [
            "0000000001-26-000001", "0000000001-26-000005"
        ])


class TestParser(unittest.TestCase):
    def test_namespace_agnostic_and_preserves_duplicate_cusip_rows(self):
        primary_xml = b'''<?xml version="1.0"?>
        <ns1:edgarSubmission xmlns:ns1="urn:test-cover">
          <ns1:periodOfReport>03-31-2026</ns1:periodOfReport>
          <ns1:coverPage>
            <ns1:reportCalendarOrQuarter>03-31-2026</ns1:reportCalendarOrQuarter>
            <ns1:isAmendment>false</ns1:isAmendment>
            <ns1:filingManager><ns1:name>Example Legal Manager LLC</ns1:name></ns1:filingManager>
            <ns1:reportType>13F HOLDINGS REPORT</ns1:reportType>
            <ns1:form13FFileNumber>028-12345</ns1:form13FFileNumber>
          </ns1:coverPage>
          <ns1:summaryPage>
            <ns1:otherIncludedManagersCount>0</ns1:otherIncludedManagersCount>
            <ns1:tableEntryTotal>2</ns1:tableEntryTotal>
            <ns1:tableValueTotal>300</ns1:tableValueTotal>
          </ns1:summaryPage>
        </ns1:edgarSubmission>'''
        info_xml = b'''<?xml version="1.0"?>
        <informationTable xmlns="urn:test-info">
          <infoTable>
            <nameOfIssuer>ACME &amp; CO</nameOfIssuer><titleOfClass>COM</titleOfClass>
            <cusip>012345678</cusip><value>100</value>
            <shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
            <investmentDiscretion>SOLE</investmentDiscretion>
            <votingAuthority><Sole>10</Sole><Shared>0</Shared><None>0</None></votingAuthority>
          </infoTable>
          <infoTable>
            <nameOfIssuer>ACME &amp; CO</nameOfIssuer><titleOfClass>CALL</titleOfClass>
            <cusip>012345678</cusip><value>200</value><putCall>Call</putCall>
            <shrsOrPrnAmt><sshPrnamt>20</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
            <investmentDiscretion>OTR</investmentDiscretion><otherManager>1</otherManager>
            <votingAuthority><Sole>0</Sole><Shared>20</Shared><None>0</None></votingAuthority>
          </infoTable>
        </informationTable>'''
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            primary = td / "primary.xml"
            info = td / "info.xml"
            primary.write_bytes(primary_xml)
            info.write_bytes(info_xml)
            ref = type("Ref", (), {
                "accession_number": "0000000001-26-000001",
                "cik": "1",
                "fund_name": "Example Fund",
                "form_type": "13F-HR",
                "filing_date": "2026-05-10",
            })()
            doc = FilingDocuments(ref, primary, info, td / "out.xml")
            filing, holdings = parse_filing(doc)

        self.assertEqual(filing["cik"], "0000000001")
        self.assertEqual(filing["report_quarter"], "2026Q1")
        self.assertEqual(filing["table_entry_total"], 2)
        self.assertEqual(len(holdings), 2)
        self.assertEqual(holdings[0]["cusip"], holdings[1]["cusip"])
        self.assertEqual(holdings[0]["name_of_issuer"], "ACME & CO")
        self.assertIsNone(holdings[0]["put_call"])
        self.assertEqual(holdings[1]["put_call"], "Call")

    def test_notice_has_filing_row_and_zero_holdings(self):
        primary_xml = b'''<?xml version="1.0"?>
        <edgarSubmission xmlns="urn:test-cover">
          <coverPage>
            <reportCalendarOrQuarter>06-30-2026</reportCalendarOrQuarter>
            <isAmendment>false</isAmendment>
            <filingManager><name>Notice Manager</name></filingManager>
            <reportType>13F NOTICE</reportType>
          </coverPage>
        </edgarSubmission>'''
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            primary = td / "primary.xml"
            primary.write_bytes(primary_xml)
            ref = type("Ref", (), {
                "accession_number": "0000000002-26-000001",
                "cik": "2",
                "fund_name": "Notice Fund",
                "form_type": "13F-NT",
                "filing_date": "2026-08-14",
            })()
            doc = FilingDocuments(ref, primary, None, td / "out.xml")
            filing, holdings = parse_filing(doc)

        self.assertEqual(filing["report_type"], "13F NOTICE")
        self.assertIsNone(filing["table_entry_total"])
        self.assertEqual(holdings, [])


if __name__ == "__main__":
    unittest.main()
