from __future__ import annotations

import unittest

# This module imports pyarrow through agents.answer; pyarrow is already present in the
# challenge's frozen requirements.txt.
from agents.answer import _validate_sql


class TestAgentSQLValidation(unittest.TestCase):
    def test_accepts_read_only_select_with_source_column(self):
        sql = "SELECT 1 AS answer, '0000000001-26-000001' AS source_accessions"
        self.assertEqual(_validate_sql(sql), sql)

    def test_rejects_write(self):
        with self.assertRaises(ValueError):
            _validate_sql("DELETE FROM holdings RETURNING accession_number AS source_accessions")

    def test_rejects_multiple_statements(self):
        with self.assertRaises(ValueError):
            _validate_sql("SELECT accession_number AS source_accessions FROM filings; DROP TABLE holdings")

    def test_requires_sources_in_retrieval_query(self):
        with self.assertRaises(ValueError):
            _validate_sql("SELECT COUNT(*) FROM holdings")


if __name__ == "__main__":
    unittest.main()
