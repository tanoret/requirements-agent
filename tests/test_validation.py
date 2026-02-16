import unittest
from src.validation import validate_requirement_instance, validate_instance


class TestValidation(unittest.TestCase):
    def test_missing_verification_method_is_error(self):
        req = {
            "id": "PLV-999",
            "text": "The valve shall do something.",
            "type": "functional",
            "verification": {"method": [], "acceptance": "OK"},
            "tbd_parameters": []
        }
        issues = validate_requirement_instance(req)
        self.assertTrue(any(i.code == "REQ_VERIFICATION_METHOD_MISSING" and i.severity == "error" for i in issues))

    def test_missing_acceptance_is_error(self):
        req = {
            "id": "PLV-999",
            "text": "The valve shall do something.",
            "type": "functional",
            "verification": {"method": ["test"], "acceptance": ""},
            "tbd_parameters": []
        }
        issues = validate_requirement_instance(req)
        self.assertTrue(any(i.code == "REQ_VERIFICATION_ACCEPTANCE_MISSING" and i.severity == "error" for i in issues))

    def test_unresolved_placeholder_tracked_is_warning(self):
        req = {
            "id": "PLV-999",
            "text": "The valve shall withstand {{dp_max}} without damage.",
            "type": "performance",
            "verification": {"method": ["analysis"], "acceptance": "Meets."},
            "tbd_parameters": ["dp_max"]
        }
        issues = validate_requirement_instance(req)
        self.assertTrue(any(i.code == "REQ_PLACEHOLDER_TBD" and i.severity == "warning" for i in issues))

    def test_unresolved_placeholder_untracked_is_error(self):
        req = {
            "id": "PLV-999",
            "text": "The valve shall withstand {{dp_max}} without damage.",
            "type": "performance",
            "verification": {"method": ["analysis"], "acceptance": "Meets."},
            "tbd_parameters": []
        }
        issues = validate_requirement_instance(req)
        self.assertTrue(any(i.code == "REQ_PLACEHOLDER_UNTRACKED" and i.severity == "error" for i in issues))

    def test_atomicity_andor_is_warning(self):
        req = {
            "id": "PLV-999",
            "text": "The valve shall open and/or close within limits.",
            "type": "performance",
            "verification": {"method": ["test"], "acceptance": "Meets."},
            "tbd_parameters": []
        }
        issues = validate_requirement_instance(req)
        self.assertTrue(any(i.code == "REQ_ATOMICITY_ANDOR" and i.severity == "warning" for i in issues))

    def test_instance_overall_fail_on_errors(self):
        inst = {
            "applicable_requirements": [{
                "id": "PLV-999",
                "text": "The valve shall do something.",
                "type": "functional",
                "verification": {"method": [], "acceptance": ""},
                "tbd_parameters": []
            }]
        }
        v = validate_instance(inst)
        self.assertEqual(v["overall_status"], "fail")
        self.assertGreater(v["error_count"], 0)


if __name__ == "__main__":
    unittest.main()
