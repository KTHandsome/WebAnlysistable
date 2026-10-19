import unittest
from dataclasses import FrozenInstanceError
from uuid import uuid4

from analysis.analysis_work_identity import (
    create_work_identity,
    normalize_user_id,
    normalize_method_code,
    validate_work_id,
    assert_work_access,
)


class TestAnalysisWorkIdentity(unittest.TestCase):

    def test_unique_work_ids(self):
        a = create_work_identity("USER001", "W434")
        b = create_work_identity("USER001", "W434")
        self.assertNotEqual(a.work_id, b.work_id)

    def test_method_normalization(self):
        work = create_work_identity("USER001", " w434 ")
        self.assertEqual(work.method_code, "W434")

    def test_user_normalization(self):
        self.assertEqual(
            normalize_user_id(" USER001 "),
            "USER001"
        )

    def test_empty_user_rejected(self):
        for value in ("", "   ", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    create_work_identity(value, "W434")

    def test_empty_method_rejected(self):
        for value in ("", "   ", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    create_work_identity("USER001", value)

    def test_uuid_validation(self):
        work = create_work_identity("USER001", "W434")
        self.assertEqual(
            validate_work_id(work.work_id),
            work.work_id
        )

    def test_invalid_uuid_rejected(self):
        for value in ("invalid", "", None, "12345"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_work_id(value)

    def test_owner_access_allowed(self):
        work = create_work_identity("USER001", "W434")
        self.assertTrue(
            assert_work_access(work, "USER001", "W434")
        )

    def test_cross_user_denied(self):
        work = create_work_identity("USER001", "W434")
        with self.assertRaises(PermissionError):
            assert_work_access(work, "USER002", "W434")

    def test_cross_method_denied(self):
        work = create_work_identity("USER001", "W434")
        with self.assertRaises(PermissionError):
            assert_work_access(work, "USER001", "W330")

    def test_identity_immutable(self):
        work = create_work_identity("USER001", "W434")
        with self.assertRaises(FrozenInstanceError):
            work.owner_user_id = "USER002"


if __name__ == "__main__":
    unittest.main(verbosity=2)
