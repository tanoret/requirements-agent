import unittest
from src.reporting import build_report


class TestReporting(unittest.TestCase):
    def test_build_report_groups_by_code(self):
        instance = {
            "instance_id": "X",
            "template_id": "T",
            "generated_utc": "2026-02-02T00:00:00Z",
            "valve_profile": {"valve_tag": "RCS-VLV-001"},
            "validation": {
                "overall_status": "pass",
                "error_count": 0,
                "warning_count": 2,
                "info_count": 0,
                "issue_count": 2,
                "issues": [
                    {"severity": "warning", "code": "A", "message": "m1", "requirement_id": "PLV-001"},
                    {"severity": "warning", "code": "A", "message": "m2", "requirement_id": "PLV-002"}
                ]
            }
        }
        r = build_report(instance)
        self.assertEqual(r["counts"]["warning_count"], 2)
        self.assertEqual(len(r["by_code"]), 1)
        self.assertEqual(r["by_code"][0]["code"], "A")
        self.assertEqual(r["by_code"][0]["count"], 2)
        self.assertEqual(r["by_code"][0]["requirement_ids"], ["PLV-001", "PLV-002"])


if __name__ == "__main__":
    unittest.main()
