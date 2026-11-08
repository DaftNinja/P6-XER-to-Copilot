import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "parser"))

from xer_to_json import XerError, parse_xer_file  # noqa: E402

SAMPLE = os.path.join(HERE, "fixtures", "sample.xer")
SCRIPT = os.path.join(HERE, "..", "parser", "xer_to_json.py")


class SampleFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = parse_xer_file(SAMPLE)
        cls.acts = {a["id"]: a for a in cls.result["activities"]}

    def test_project(self):
        (proj,) = self.result["projects"]
        self.assertEqual(proj["short_name"], "LON-DC1")
        self.assertEqual(proj["name"], "London DC1 – Hall 2 fit-out")  # cp1252 en dash
        self.assertEqual(proj["data_date"], "2026-11-02T08:00")

    def test_activities_use_visible_activity_id(self):
        self.assertEqual(set(self.acts), {"A1000", "A1010", "A2000", "M9000"})

    def test_status_and_type(self):
        self.assertEqual(self.acts["A1000"]["status"], "complete")
        self.assertEqual(self.acts["A1010"]["status"], "in_progress")
        self.assertEqual(self.acts["M9000"]["type"], "finish_milestone")

    def test_hours_converted_with_activity_calendar(self):
        self.assertEqual(self.acts["A1010"]["original_duration"], 5.0)   # 40h / 8
        self.assertEqual(self.acts["A2000"]["original_duration"], 3.0)   # 72h / 24
        self.assertEqual(self.acts["A2000"]["total_float"], -1.0)        # -24h / 24
        self.assertEqual(self.acts["M9000"]["total_float"], 5.0)

    def test_critical_flag(self):
        self.assertTrue(self.acts["A1010"]["is_critical"])
        self.assertTrue(self.acts["A2000"]["is_critical"])
        self.assertFalse(self.acts["M9000"]["is_critical"])
        self.assertFalse(self.acts["A1000"]["is_critical"])  # complete

    def test_wbs_path_excludes_project_node(self):
        self.assertEqual(self.acts["A1010"]["wbs_path"], "Electrical / HV switchgear")
        self.assertEqual(self.acts["A1010"]["wbs_name"], "HV switchgear")

    def test_relationships_both_directions(self):
        self.assertIn({"id": "A1000", "type": "FS", "lag": 0.0}, self.acts["A1010"]["predecessors"])
        self.assertIn({"id": "A2000", "type": "SS", "lag": 2.0}, self.acts["A1010"]["successors"])

    def test_external_predecessor_kept_and_warned(self):
        self.assertIn({"id": "external:999", "type": "FS", "lag": 0.0}, self.acts["A2000"]["predecessors"])
        self.assertTrue(any("not in this file" in w for w in self.result["metadata"]["warnings"]))

    def test_dates_iso(self):
        self.assertEqual(self.acts["A1000"]["actual_finish"], "2026-09-12T17:00")
        self.assertIsNone(self.acts["A2000"]["actual_start"])


class ErrorTests(unittest.TestCase):
    def test_missing_file(self):
        with self.assertRaises(XerError):
            parse_xer_file("does-not-exist.xer")

    def test_not_an_xer(self):
        with tempfile.NamedTemporaryFile("w", suffix=".xer", delete=False) as f:
            f.write("<?xml version='1.0'?><APIBusinessObjects/>")
        try:
            with self.assertRaises(XerError):
                parse_xer_file(f.name)
        finally:
            os.unlink(f.name)

    def test_cli_exit_codes(self):
        bad = subprocess.run([sys.executable, SCRIPT, "nope.xer"], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        good = subprocess.run([sys.executable, SCRIPT, SAMPLE, "-o", "-"], capture_output=True, text=True)
        self.assertEqual(good.returncode, 0)
        self.assertEqual(json.loads(good.stdout)["metadata"]["activity_count"], 4)


if __name__ == "__main__":
    unittest.main()
