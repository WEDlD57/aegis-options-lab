from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from aegis.cli import generate


class ExportTests(unittest.TestCase):
    def test_report_is_embedded_and_all_export_records_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)
            with redirect_stdout(io.StringIO()):
                data=generate(out,42,20,("normal",),("aegis",),10)
            html=(out/"report.html").read_text(encoding="utf-8")
            self.assertNotIn("/*__DATA__*/",html)
            self.assertNotIn("/*__MATH__*/",html)
            self.assertNotIn("<script src=",html)
            self.assertNotIn("fetch(",html)
            self.assertEqual(json.loads((out/"replay.json").read_text(encoding="utf-8")),data)
            records=[json.loads(line) for line in (out/"audit.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertTrue(records)
            self.assertTrue(all(row["policy"]=="aegis" for row in records))
            self.assertGreater((out/"trades.csv").stat().st_size,100)
