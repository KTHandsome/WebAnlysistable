import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from models import AnalysisRecord, AnalysisWorkDraft
from analysis.analysis_work_identity import (
    create_work_identity,
)
from analysis.analysis_work_draft_repository import (
    AnalysisWorkDraftRepository,
    DraftConflictError,
)


class TestAnalysisWorkDraftRepository(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        AnalysisRecord.__table__.create(bind=self.engine)
        AnalysisWorkDraft.__table__.create(bind=self.engine)

        from models import AnalysisWorkState
        AnalysisWorkState.__table__.create(bind=self.engine)

        self.db = Session(self.engine)
        self.repo = AnalysisWorkDraftRepository(self.db)

        self.a = create_work_identity("USER001", "W434")
        self.b = create_work_identity("USER001", "W434")

        self.repo.create_draft(self.a, {"sample_id": "A"})
        self.repo.create_draft(self.b, {"sample_id": "B"})
        self.db.commit()

    def tearDown(self):
        self.db.rollback()
        self.db.close()
        self.engine.dispose()

    def load_a(self):
        return self.repo.load_draft(
            self.a.work_id, "USER001", "W434"
        )

    def test_create_revision_zero(self):
        self.assertEqual(self.load_a()["revision"], 0)

    def test_initial_state(self):
        self.assertEqual(
            self.load_a()["state"]["sample_id"], "A"
        )

    def test_independent_drafts(self):
        self.assertEqual(
            self.repo.load_draft(
                self.b.work_id, "USER001", "W434"
            )["state"]["sample_id"],
            "B"
        )

    def test_cross_user_denied(self):
        with self.assertRaises(PermissionError):
            self.repo.load_draft(
                self.a.work_id, "USER002", "W434"
            )

    def test_cross_method_denied(self):
        with self.assertRaises(PermissionError):
            self.repo.load_draft(
                self.a.work_id, "USER001", "W330"
            )

    def test_duplicate_draft_denied(self):
        with self.assertRaises(ValueError):
            self.repo.create_draft(self.a)

    def test_invalid_state_denied(self):
        identity = create_work_identity("USER001", "W434")
        with self.assertRaises(ValueError):
            self.repo.create_draft(identity, ["invalid"])

    def test_revision_increment(self):
        revision = self.repo.save_draft(
            self.a.work_id, "USER001", "W434",
            0, {"sample_id": "A2"}
        )
        self.db.commit()
        self.assertEqual(revision, 1)
        self.assertEqual(self.load_a()["revision"], 1)

    def test_stale_revision_denied(self):
        self.repo.save_draft(
            self.a.work_id, "USER001", "W434",
            0, {"sample_id": "A2"}
        )
        self.db.commit()

        with self.assertRaises(DraftConflictError):
            self.repo.save_draft(
                self.a.work_id, "USER001", "W434",
                0, {"sample_id": "STALE"}
            )
        self.db.rollback()

        self.assertEqual(
            self.load_a()["state"]["sample_id"], "A2"
        )

    def test_invalid_revision_denied(self):
        for revision in (-1, None, "0", True):
            with self.subTest(revision=revision):
                with self.assertRaises(ValueError):
                    self.repo.save_draft(
                        self.a.work_id, "USER001",
                        "W434", revision, {}
                    )

    def test_submitted_draft_denied(self):
        draft = self.db.query(AnalysisWorkDraft).filter(
            AnalysisWorkDraft.work_id == self.a.work_id
        ).one()
        draft.work_status = "SUBMITTED"
        self.db.commit()

        with self.assertRaises(ValueError):
            self.repo.save_draft(
                self.a.work_id, "USER001",
                "W434", 0, {}
            )

    def test_parsed_data_preserved_when_omitted(self):
        original = {
            "source": "OI1030W",
            "rows": [1, 2, 3]
        }

        self.repo.save_draft(
            self.a.work_id,
            "USER001",
            "W434",
            0,
            {
                "parsed_data": original,
                "remark": "original"
            }
        )
        self.db.commit()

        self.repo.save_draft(
            self.a.work_id,
            "USER001",
            "W434",
            1,
            {"remark": "updated"}
        )
        self.db.commit()

        saved = self.load_a()

        self.assertEqual(saved["revision"], 2)
        self.assertEqual(
            saved["state"]["parsed_data"],
            original
        )
        self.assertEqual(
            saved["state"]["remark"],
            "updated"
        )

    def test_parsed_data_modification_denied(self):
        original = {"rows": [1, 2, 3]}

        self.repo.save_draft(
            self.a.work_id,
            "USER001",
            "W434",
            0,
            {"parsed_data": original}
        )
        self.db.commit()

        with self.assertRaises(ValueError):
            self.repo.save_draft(
                self.a.work_id,
                "USER001",
                "W434",
                1,
                {"parsed_data": {"rows": [9, 9, 9]}}
            )

        self.db.rollback()

    def test_rejected_parsed_data_update_is_atomic(self):
        original = {"rows": [1, 2, 3]}

        self.repo.save_draft(
            self.a.work_id,
            "USER001",
            "W434",
            0,
            {
                "parsed_data": original,
                "remark": "original"
            }
        )
        self.db.commit()

        with self.assertRaises(ValueError):
            self.repo.save_draft(
                self.a.work_id,
                "USER001",
                "W434",
                1,
                {
                    "parsed_data": {"rows": []},
                    "remark": "invalid"
                }
            )

        self.db.rollback()

        saved = self.load_a()

        self.assertEqual(saved["revision"], 1)
        self.assertEqual(
            saved["state"]["parsed_data"],
            original
        )
        self.assertEqual(
            saved["state"]["remark"],
            "original"
        )

    def _create_formal_record(
        self,
        owner="USER001",
        status="UNDER_REVIEW",
        method="W434"
    ):
        from datetime import date
        from uuid import uuid4
        from models import AnalysisRecord

        formal_id = str(uuid4())

        record = AnalysisRecord(
            analysis_id=formal_id,
            status=status,
            ctrl_year="2026",
            category="W",
            exam_no="TOC",
            exam_name="TOC",
            method_code=method,
            method_name=method,
            instrument_id="TEST-INSTRUMENT",
            form_date=date(2026, 10, 19),
            analysis_start_date=date(2026, 10, 19),
            analysis_end_date=date(2026, 10, 19),
            analyst_user_id=owner
        )

        self.db.add(record)
        self.db.commit()

        return formal_id

    def _create_matching_snapshot(self, formal_id):
        import json
        from models import AnalysisWorkState

        draft_state = self.load_a()["state"]

        snapshot_state = dict(draft_state)
        snapshot_state["formal_analysis_id"] = formal_id

        snapshot = AnalysisWorkState(
            analysis_id=formal_id,
            method_code="W434",
            state_json=json.dumps(
                snapshot_state,
                ensure_ascii=False
            ),
            form_data_json='{"method_code":"W434"}'
        )

        self.db.add(snapshot)
        self.db.commit()

        return snapshot

    def test_submit_draft_success(self):
        formal_id = self._create_formal_record()
        self._create_matching_snapshot(formal_id)
        revision = self.repo.submit_draft(
            self.a.work_id,
            "USER001",
            "W434",
            expected_revision=0,
            formal_analysis_id=formal_id
        )
        self.db.commit()

        saved = self.load_a()

        self.assertEqual(revision, 1)
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(saved["work_status"], "SUBMITTED")
        self.assertEqual(saved["formal_analysis_id"], formal_id)
        self.assertEqual(saved["state"]["sample_id"], "A")

    def test_submit_foreign_record_denied(self):
        formal_id = self._create_formal_record(
            owner="USER002"
        )
        self._create_matching_snapshot(formal_id)
        with self.assertRaises(PermissionError):
            self.repo.submit_draft(
                self.a.work_id,
                "USER001",
                "W434",
                expected_revision=0,
                formal_analysis_id=formal_id
            )

        self.db.rollback()

        saved = self.load_a()

        self.assertEqual(saved["revision"], 0)
        self.assertEqual(saved["work_status"], "EDITING")
        self.assertIsNone(saved["formal_analysis_id"])

    def test_submit_missing_snapshot_denied(self):
        formal_id = self._create_formal_record()

        with self.assertRaises(ValueError):
            self.repo.submit_draft(
                self.a.work_id,
                "USER001",
                "W434",
                expected_revision=0,
                formal_analysis_id=formal_id
            )

        self.db.rollback()

        saved = self.load_a()
        self.assertEqual(saved["work_status"], "EDITING")
        self.assertEqual(saved["revision"], 0)
        self.assertIsNone(saved["formal_analysis_id"])

    def test_submit_snapshot_mismatch_denied(self):
        import json
        from models import AnalysisWorkState

        formal_id = self._create_formal_record()
        self._create_matching_snapshot(formal_id)

        snapshot = self.db.query(
            AnalysisWorkState
        ).filter(
            AnalysisWorkState.analysis_id == formal_id
        ).one()

        snapshot.state_json = json.dumps({
            "sample_id": "DIFFERENT",
            "formal_analysis_id": formal_id
        })
        self.db.commit()

        with self.assertRaises(ValueError):
            self.repo.submit_draft(
                self.a.work_id,
                "USER001",
                "W434",
                expected_revision=0,
                formal_analysis_id=formal_id
            )

        self.db.rollback()

        saved = self.load_a()
        self.assertEqual(saved["work_status"], "EDITING")
        self.assertEqual(saved["revision"], 0)
        self.assertIsNone(saved["formal_analysis_id"])

    def test_submit_snapshot_method_mismatch_denied(self):
        from models import AnalysisWorkState

        formal_id = self._create_formal_record()
        self._create_matching_snapshot(formal_id)

        snapshot = self.db.query(
            AnalysisWorkState
        ).filter(
            AnalysisWorkState.analysis_id == formal_id
        ).one()

        snapshot.method_code = "W330"
        self.db.commit()

        with self.assertRaises(ValueError):
            self.repo.submit_draft(
                self.a.work_id,
                "USER001",
                "W434",
                expected_revision=0,
                formal_analysis_id=formal_id
            )

        self.db.rollback()

        saved = self.load_a()
        self.assertEqual(saved["work_status"], "EDITING")
        self.assertEqual(saved["revision"], 0)
        self.assertIsNone(saved["formal_analysis_id"])

    def test_submit_stale_revision_denied(self):
        formal_id = self._create_formal_record()
        self._create_matching_snapshot(formal_id)
        self.repo.save_draft(
            self.a.work_id,
            "USER001",
            "W434",
            expected_revision=0,
            state={"sample_id": "A2"}
        )
        self.db.commit()

        from analysis.analysis_work_draft_repository import (
            DraftConflictError,
        )

        # Keep the formal snapshot consistent with
        # the latest draft so this test isolates
        # the stale revision conflict.
        import json
        from models import AnalysisWorkState

        snapshot = self.db.query(
            AnalysisWorkState
        ).filter(
            AnalysisWorkState.analysis_id == formal_id
        ).one()

        latest_state = self.load_a()["state"]

        snapshot_state = dict(latest_state)
        snapshot_state["formal_analysis_id"] = formal_id

        snapshot.state_json = json.dumps(
            snapshot_state,
            ensure_ascii=False
        )

        self.db.commit()

        with self.assertRaises(DraftConflictError):
            self.repo.submit_draft(
                self.a.work_id,
                "USER001",
                "W434",
                expected_revision=0,
                formal_analysis_id=formal_id
            )

        self.db.rollback()

        saved = self.load_a()

        self.assertEqual(saved["revision"], 1)
        self.assertEqual(saved["work_status"], "EDITING")
        self.assertIsNone(saved["formal_analysis_id"])

    def _prepare_submitted_draft(self):
        import json
        from models import AnalysisWorkState

        formal_id = self._create_formal_record()

        draft_state = self.load_a()["state"]

        snapshot_state = dict(draft_state)
        snapshot_state["formal_analysis_id"] = formal_id

        snapshot = AnalysisWorkState(
            analysis_id=formal_id,
            method_code="W434",
            state_json=json.dumps(snapshot_state),
            form_data_json='{"method_code":"W434"}'
        )

        self.db.add(snapshot)
        self.db.commit()

        self.repo.submit_draft(
            self.a.work_id,
            "USER001",
            "W434",
            expected_revision=0,
            formal_analysis_id=formal_id
        )
        self.db.commit()

        return formal_id

    def _set_formal_status(self, formal_id, status):
        from models import AnalysisRecord

        record = self.db.query(AnalysisRecord).filter(
            AnalysisRecord.analysis_id == formal_id
        ).one()

        record.status = status
        self.db.commit()

    def test_submit_transaction_rollback(self):
        import json
        from models import (
            AnalysisRecord,
            AnalysisWorkState,
        )

        formal_id = self._create_formal_record(
            status="REJECTED"
        )

        original_state = self.load_a()["state"]

        original_snapshot = dict(original_state)
        original_snapshot["formal_analysis_id"] = formal_id

        snapshot = AnalysisWorkState(
            analysis_id=formal_id,
            method_code="W434",
            state_json=json.dumps(
                original_snapshot,
                ensure_ascii=False
            ),
            form_data_json='{"method_code":"W434"}'
        )

        self.db.add(snapshot)
        self.db.commit()

        original_json = snapshot.state_json

        record = self.db.query(AnalysisRecord).filter(
            AnalysisRecord.analysis_id == formal_id
        ).one()

        # Simulate changes within one transaction.
        record.status = "UNDER_REVIEW"

        snapshot.state_json = json.dumps({
            "sample_id": "INCONSISTENT",
            "formal_analysis_id": formal_id
        })

        self.db.flush()

        with self.assertRaisesRegex(
            ValueError,
            "inconsistent"
        ):
            self.repo.submit_draft(
                self.a.work_id,
                "USER001",
                "W434",
                expected_revision=0,
                formal_analysis_id=formal_id
            )

        self.db.rollback()
        self.db.expire_all()

        saved_record = self.db.query(
            AnalysisRecord
        ).filter(
            AnalysisRecord.analysis_id == formal_id
        ).one()

        saved_snapshot = self.db.query(
            AnalysisWorkState
        ).filter(
            AnalysisWorkState.analysis_id == formal_id
        ).one()

        saved_draft = self.load_a()

        self.assertEqual(
            saved_record.status,
            "REJECTED"
        )

        self.assertEqual(
            saved_snapshot.state_json,
            original_json
        )

        self.assertEqual(
            saved_draft["work_status"],
            "EDITING"
        )

        self.assertEqual(
            saved_draft["revision"],
            0
        )

        self.assertIsNone(
            saved_draft["formal_analysis_id"]
        )

        self.assertEqual(
            saved_draft["state"],
            original_state
        )

    def test_resume_draft_success(self):
        formal_id = self._prepare_submitted_draft()
        self._set_formal_status(formal_id, "REJECTED")

        next_revision = self.repo.resume_draft(
            self.a.work_id,
            "USER001",
            "W434",
            expected_revision=1
        )
        self.db.commit()

        saved = self.load_a()

        self.assertEqual(next_revision, 2)
        self.assertEqual(saved["work_status"], "EDITING")
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(saved["formal_analysis_id"], formal_id)
        self.assertEqual(saved["work_id"], self.a.work_id)
        self.assertEqual(saved["state"]["sample_id"], "A")

    def test_resume_non_rejected_denied(self):
        self._prepare_submitted_draft()

        with self.assertRaises(ValueError):
            self.repo.resume_draft(
                self.a.work_id, "USER001", "W434", 1
            )

        self.db.rollback()
        self.assertEqual(
            self.load_a()["work_status"], "SUBMITTED"
        )

    def test_resume_snapshot_mismatch_denied(self):
        import json
        from models import AnalysisWorkState

        formal_id = self._prepare_submitted_draft()
        self._set_formal_status(formal_id, "REJECTED")

        snapshot = self.db.query(AnalysisWorkState).filter(
            AnalysisWorkState.analysis_id == formal_id
        ).one()

        snapshot.state_json = json.dumps({
            "sample_id": "DIFFERENT",
            "formal_analysis_id": formal_id
        })
        self.db.commit()

        with self.assertRaises(ValueError):
            self.repo.resume_draft(
                self.a.work_id, "USER001", "W434", 1
            )

        self.db.rollback()
        self.assertEqual(
            self.load_a()["work_status"], "SUBMITTED"
        )

    def test_resume_missing_snapshot_denied(self):
        from models import AnalysisWorkState

        formal_id = self._prepare_submitted_draft()
        self._set_formal_status(formal_id, "REJECTED")

        snapshot = self.db.query(AnalysisWorkState).filter(
            AnalysisWorkState.analysis_id == formal_id
        ).one()

        self.db.delete(snapshot)
        self.db.commit()

        with self.assertRaises(ValueError):
            self.repo.resume_draft(
                self.a.work_id, "USER001", "W434", 1
            )

        self.db.rollback()
        self.assertEqual(
            self.load_a()["work_status"], "SUBMITTED"
        )

    def test_resume_stale_revision_denied(self):
        formal_id = self._prepare_submitted_draft()
        self._set_formal_status(formal_id, "REJECTED")

        with self.assertRaises(DraftConflictError):
            self.repo.resume_draft(
                self.a.work_id, "USER001", "W434", 0
            )

        self.db.rollback()

        saved = self.load_a()
        self.assertEqual(saved["work_status"], "SUBMITTED")
        self.assertEqual(saved["revision"], 1)

    def test_other_draft_unchanged(self):
        self.repo.save_draft(
            self.a.work_id, "USER001", "W434",
            0, {"sample_id": "A2"}
        )
        self.db.commit()

        self.assertEqual(
            self.repo.load_draft(
                self.b.work_id, "USER001", "W434"
            )["state"]["sample_id"],
            "B"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
