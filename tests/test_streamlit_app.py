import sys
import types
import unittest

sys.modules.setdefault("streamlit", types.SimpleNamespace())

from src.streamlit_app import _required_schema_keys


class TestStreamlitAppHelpers(unittest.TestCase):
    def test_required_schema_keys_only_returns_required_sorted(self):
        properties = {"b": {}, "a": {}, "c": {}}
        required = {"b", "a"}

        self.assertEqual(_required_schema_keys(properties, required), ["a", "b"])

    def test_required_schema_keys_empty_when_no_required_fields(self):
        properties = {"optional_field": {}}

        self.assertEqual(_required_schema_keys(properties, set()), [])


if __name__ == "__main__":
    unittest.main()
