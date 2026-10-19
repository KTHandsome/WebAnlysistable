import unittest
from copy import deepcopy

from analysis.analysis_work_identity import (
    AnalysisWorkIdentity,
    create_work_identity,
)
from analysis.analysis_work_repository import (
    AnalysisWorkRepository,
)


class TestAnalysisWorkRepository(unittest.TestCase):

    def setUp(self):
        self.repo = AnalysisWorkRepository()
        self.a = create_work_identity("USER001", "W434")
        self.b = create_work_identity("USER001", "W434")
        self.c = create_work_identity("USER002", "W330")

        for identity in (self.a, self.b, self.c):
            self.repo.create_work(identity)

    def test_registration(self):
        identity = self.repo.get_work_identity(
            self.a.work_id, "USER001", "W434"
        )
        self.assertEqual(identity, self.a)

    def test_duplicate_registration_rejected(self):
        with self.assertRaises(ValueError):
            self.repo.create_work(self.a)

    def test_invalid_identity_rejected(self):
        with self.assertRaises(ValueError):
            self.repo.create_work({"work_id": "invalid"})

    def test_same_user_work_isolation(self):
        self.repo.save_state(
            self.a.work_id, "USER001", "W434",
            {"sample_id": "SAMPLE-A"}
        )
        self.repo.save_state(
            self.b.work_id, "USER001", "W434",
            {"sample_id": "SAMPLE-B"}
        )
        self.assertEqual(
            self.repo.load_state(
                self.a.work_id, "USER001", "W434"
            )["sample_id"],
            "SAMPLE-A"
        )
        self.assertEqual(
            self.repo.load_state(
                self.b.work_id, "USER001", "W434"
            )["sample_id"],
            "SAMPLE-B"
        )

    def test_cross_user_access_denied(self):
        with self.assertRaises(PermissionError):
            self.repo.load_state(
                self.a.work_id, "USER002", "W434"
            )

    def test_cross_method_access_denied(self):
        with self.assertRaises(PermissionError):
            self.repo.load_state(
                self.a.work_id, "USER001", "W330"
            )

    def test_unregistered_work_rejected(self):
        unknown = create_work_identity(
            "USER001", "W434"
        )
        with self.assertRaises(ValueError):
            self.repo.load_state(
                unknown.work_id, "USER001", "W434"
            )

    def test_save_requires_dict(self):
        with self.assertRaises(ValueError):
            self.repo.save_state(
                self.a.work_id, "USER001", "W434",
                ["invalid"]
            )

    def test_save_deepcopy(self):
        source = {"rows": [{"value": 1}]}
        self.repo.save_state(
            self.a.work_id, "USER001", "W434", source
        )
        source["rows"][0]["value"] = 999
        loaded = self.repo.load_state(
            self.a.work_id, "USER001", "W434"
        )
        self.assertEqual(loaded["rows"][0]["value"], 1)

    def test_load_deepcopy(self):
        self.repo.save_state(
            self.a.work_id, "USER001", "W434",
            {"rows": [{"value": 1}]}
        )
        loaded = self.repo.load_state(
            self.a.work_id, "USER001", "W434"
        )
        loaded["rows"][0]["value"] = 999
        reloaded = self.repo.load_state(
            self.a.work_id, "USER001", "W434"
        )
        self.assertEqual(reloaded["rows"][0]["value"], 1)

    def test_update_state(self):
        self.repo.save_state(
            self.a.work_id, "USER001", "W434",
            {"rows": [1], "remark": "old"}
        )
        self.assertTrue(
            self.repo.update_state(
                self.a.work_id, "USER001", "W434",
                {"remark": "new"}
            )
        )
        state = self.repo.load_state(
            self.a.work_id, "USER001", "W434"
        )
        self.assertEqual(state["rows"], [1])
        self.assertEqual(state["remark"], "new")

    def test_parsed_data_update_denied(self):
        self.repo.save_state(
            self.a.work_id, "USER001", "W434",
            {"parsed_data": {"original": True}}
        )
        with self.assertRaises(ValueError):
            self.repo.update_state(
                self.a.work_id, "USER001", "W434",
                {"parsed_data": {"original": False}}
            )

    def test_identity_fields_update_denied(self):
        self.repo.save_state(
            self.a.work_id, "USER001", "W434",
            {"remark": "initial"}
        )
        for field in (
            "work_id", "owner_user_id",
            "method_code", "formal_analysis_id"
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self.repo.update_state(
                        self.a.work_id, "USER001",
                        "W434", {field: "changed"}
                    )

    def test_clear_selected_work_only(self):
        self.repo.save_state(
            self.a.work_id, "USER001", "W434",
            {"sample_id": "A"}
        )
        self.repo.save_state(
            self.b.work_id, "USER001", "W434",
            {"sample_id": "B"}
        )
        self.assertTrue(
            self.repo.clear_state(
                self.a.work_id, "USER001", "W434"
            )
        )
        self.assertIsNone(
            self.repo.load_state(
                self.a.work_id, "USER001", "W434"
            )
        )
        self.assertEqual(
            self.repo.load_state(
                self.b.work_id, "USER001", "W434"
            )["sample_id"],
            "B"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
