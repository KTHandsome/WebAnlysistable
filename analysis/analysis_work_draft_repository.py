import json

from sqlalchemy import update
from sqlalchemy.orm import Session

from analysis.analysis_work_identity import (
    AnalysisWorkIdentity,
    assert_work_access,
    validate_work_id,
)
from models import AnalysisWorkDraft


class DraftConflictError(Exception):"""Draft revision does not match."""

def assert_snapshot_consistency(
    draft_state,
    snapshot_state,
    formal_analysis_id
):
    """
    Compare draft and formal analysis snapshot.

    formal_analysis_id is a system-managed field.
    All other analysis fields must remain equal.
    """

    if not isinstance(draft_state, dict):
        raise ValueError(
            "Draft state must be a dict."
        )

    if not isinstance(snapshot_state, dict):
        raise ValueError(
            "Formal snapshot must be a dict."
        )

    formal_id = validate_work_id(
        formal_analysis_id
    )

    snapshot_formal_id = str(
        snapshot_state.get(
            "formal_analysis_id"
        ) or ""
    ).strip()

    if snapshot_formal_id != formal_id:
        raise ValueError(
            "Formal snapshot analysis ID does not match."
        )

    draft_formal_id = str(
        draft_state.get(
            "formal_analysis_id"
        ) or ""
    ).strip()

    if (
        draft_formal_id
        and draft_formal_id != formal_id
    ):
        raise ValueError(
            "Draft formal analysis ID does not match."
        )

    draft_content = dict(draft_state)
    snapshot_content = dict(snapshot_state)

    draft_content.pop(
        "formal_analysis_id",
        None
    )

    snapshot_content.pop(
        "formal_analysis_id",
        None
    )

    if draft_content != snapshot_content:
        raise ValueError(
            "Draft and formal snapshot are inconsistent."
        )

    return True

def assert_work_bundle_consistency(
    draft_bundle,
    formal_snapshot,
    formal_analysis_id
):
    """
    Verify all five JSON sections against a formal snapshot.

    Both arguments must contain the complete five-section bundle.
    """

    if not isinstance(draft_bundle, dict):
        raise ValueError("Draft bundle must be a dict.")

    if not isinstance(formal_snapshot, dict):
        raise ValueError("Formal snapshot must be a dict.")

    sections = (
        "state",
        "form_data",
        "control_data",
        "method_data",
        "report_data",
    )

    for section in sections:
        if section not in draft_bundle:
            raise ValueError(
                "Missing draft section: " + section
            )

        if section not in formal_snapshot:
            raise ValueError(
                "Missing formal section: " + section
            )

        if not isinstance(draft_bundle[section], dict):
            raise ValueError(
                "Invalid draft section: " + section
            )

        if not isinstance(formal_snapshot[section], dict):
            raise ValueError(
                "Invalid formal section: " + section
            )

    assert_snapshot_consistency(
        draft_bundle["state"],
        formal_snapshot["state"],
        formal_analysis_id
    )

    for section in sections[1:]:
        if draft_bundle[section] != formal_snapshot[section]:
            raise ValueError(
                "Draft and formal snapshot are inconsistent: "
                + section
            )

    return True

class AnalysisWorkDraftRepository:

    def __init__(self, db):
        if not isinstance(db, Session):
            raise TypeError(
                "A SQLAlchemy Session is required."
            )
        self.db = db

    def create_draft(self, identity, state=None):
        if not isinstance(identity, AnalysisWorkIdentity):
            raise ValueError("Invalid work identity.")

        validate_work_id(identity.work_id)
        assert_work_access(
            identity,
            identity.owner_user_id,
            identity.method_code
        )

        if identity.formal_analysis_id is not None:
            raise ValueError(
                "New draft cannot have a formal analysis ID."
            )

        if state is None:
            state = {}

        if not isinstance(state, dict):
            raise ValueError("Draft state must be a dict.")

        existing = self.db.query(
            AnalysisWorkDraft
        ).filter(
            AnalysisWorkDraft.work_id == identity.work_id
        ).first()

        if existing is not None:
            raise ValueError("Draft already exists.")

        draft = AnalysisWorkDraft(
            work_id=identity.work_id,
            owner_user_id=identity.owner_user_id,
            method_code=identity.method_code,
            work_status="EDITING",
            revision=0,
            state_json=json.dumps(
                state,
                ensure_ascii=False
            )
        )

        self.db.add(draft)
        self.db.flush()

        return identity.work_id

    def load_draft(self, work_id, user_id, method_code):
        canonical_id = validate_work_id(work_id)

        draft = self.db.query(
            AnalysisWorkDraft
        ).filter(
            AnalysisWorkDraft.work_id == canonical_id
        ).first()

        if draft is None:
            raise ValueError("Draft does not exist.")

        identity = AnalysisWorkIdentity(
            work_id=draft.work_id,
            owner_user_id=draft.owner_user_id,
            method_code=draft.method_code,
            formal_analysis_id=draft.formal_analysis_id
        )

        assert_work_access(
            identity,
            user_id,
            method_code
        )

        def decode_section(value, section_name):
            try:
                decoded = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                raise ValueError(
                    "Invalid JSON in " + section_name
                )

            if not isinstance(decoded, dict):
                raise ValueError(
                    section_name + " must contain a JSON object."
                )

            return decoded

        state = decode_section(
            draft.state_json,
            "state_json"
        )

        form_data = decode_section(
            draft.form_data_json,
            "form_data_json"
        )

        control_data = decode_section(
            draft.control_data_json,
            "control_data_json"
        )

        method_data = decode_section(
            draft.method_data_json,
            "method_data_json"
        )

        report_data = decode_section(
            draft.report_data_json,
            "report_data_json"
        )

        return {
            "work_id": draft.work_id,
            "revision": draft.revision,
            "work_status": draft.work_status,
            "formal_analysis_id": draft.formal_analysis_id,
            "state": state,
            "form_data": form_data,
            "control_data": control_data,
            "method_data": method_data,
            "report_data": report_data
        }

    def resume_draft(
        self,
        work_id,
        user_id,
        method_code,
        expected_revision
    ):
        from models import (
            AnalysisRecord,
            AnalysisWorkState,
        )

        current = self.load_draft(
            work_id,
            user_id,
            method_code
        )

        if current["work_status"] != "SUBMITTED":
            raise ValueError(
                "Only SUBMITTED drafts can be resumed."
            )

        if (
            type(expected_revision) is not int
            or expected_revision < 0
        ):
            raise ValueError(
                "Invalid expected revision."
            )

        formal_id = validate_work_id(
            current["formal_analysis_id"]
        )

        record = self.db.query(
            AnalysisRecord
        ).filter(
            AnalysisRecord.analysis_id == formal_id
        ).first()

        if record is None:
            raise ValueError(
                "Formal analysis record does not exist."
            )

        if record.status != "REJECTED":
            raise ValueError(
                "Formal analysis must be REJECTED."
            )

        if (
            str(record.analyst_user_id or "").strip()
            != str(user_id or "").strip()
        ):
            raise PermissionError(
                "Only the original analyst can resume this draft."
            )

        if (
            str(record.method_code or "").strip().upper()
            != str(method_code or "").strip().upper()
        ):
            raise ValueError(
                "Formal analysis method does not match."
            )

        snapshot = self.db.query(
            AnalysisWorkState
        ).filter(
            AnalysisWorkState.analysis_id == formal_id
        ).first()

        if snapshot is None:
            raise ValueError(
                "Formal analysis snapshot does not exist."
            )

        # Verify all five sections before resuming.
        snapshot_fields = (
            ("state", "state_json"),
            ("form_data", "form_data_json"),
            ("control_data", "control_data_json"),
            ("method_data", "method_data_json"),
            ("report_data", "report_data_json"),
        )

        formal_bundle = {}

        for section_name, column_name in snapshot_fields:
            raw_value = getattr(snapshot, column_name)

            try:
                decoded = json.loads(raw_value)
            except (json.JSONDecodeError, TypeError):
                raise ValueError(
                    "Invalid formal snapshot JSON: "
                    + column_name
                )

            if not isinstance(decoded, dict):
                raise ValueError(
                    "Formal snapshot must contain an object: "
                    + column_name
                )

            formal_bundle[section_name] = decoded

        assert_work_bundle_consistency(
            current,
            formal_bundle,
            formal_id
        )

        result = self.db.execute(
            update(AnalysisWorkDraft)
            .where(
                AnalysisWorkDraft.work_id
                == current["work_id"],
                AnalysisWorkDraft.owner_user_id
                == str(user_id).strip(),
                AnalysisWorkDraft.method_code
                == str(method_code).strip().upper(),
                AnalysisWorkDraft.formal_analysis_id
                == formal_id,
                AnalysisWorkDraft.work_status
                == "SUBMITTED",
                AnalysisWorkDraft.revision
                == expected_revision
            )
            .values(
                work_status="EDITING",
                revision=expected_revision + 1
            )
        )

        if result.rowcount != 1:
            raise DraftConflictError(
                "Draft was modified by another request."
            )

        self.db.flush()

        return expected_revision + 1

    def submit_draft(
        self,
        work_id,
        user_id,
        method_code,
        expected_revision,
        formal_analysis_id
    ):
        from models import (
            AnalysisRecord,
            AnalysisWorkState,
        )

        current = self.load_draft(
            work_id,
            user_id,
            method_code
        )

        if current["work_status"] != "EDITING":
            raise ValueError(
                "Only EDITING drafts can be submitted."
            )

        if (
            type(expected_revision) is not int
            or expected_revision < 0
        ):
            raise ValueError(
                "Invalid expected revision."
            )

        formal_id = str(
            formal_analysis_id or ""
        ).strip()

        formal_id = validate_work_id(formal_id)

        if (
            current["formal_analysis_id"] is not None
            and current["formal_analysis_id"] != formal_id
        ):
            raise ValueError(
                "Draft is already linked to another analysis."
            )

        record = self.db.query(
            AnalysisRecord
        ).filter(
            AnalysisRecord.analysis_id == formal_id
        ).first()

        if record is None:
            raise ValueError(
                "Formal analysis record does not exist."
            )

        if record.status != "UNDER_REVIEW":
            raise ValueError(
                "Formal analysis must be UNDER_REVIEW."
            )

        # Verify the formal record belongs to this analyst.
        record_owner = str(
            record.analyst_user_id or ""
        ).strip()

        current_user = str(
            user_id or ""
        ).strip()

        if not record_owner or record_owner != current_user:
            raise PermissionError(
                "Formal analysis record access denied."
            )

        if (
            record.method_code.strip().upper()
            != str(method_code).strip().upper()
        ):
            raise ValueError(
                "Formal analysis method does not match."
            )

        # Verify the saved formal snapshot before submission.
        snapshot = self.db.query(
            AnalysisWorkState
        ).filter(
            AnalysisWorkState.analysis_id == formal_id
        ).first()

        if snapshot is None:
            raise ValueError(
                "Formal analysis snapshot does not exist."
            )

        if (
            str(snapshot.method_code or "").strip().upper()
            != str(method_code or "").strip().upper()
        ):
            raise ValueError(
                "Formal snapshot method does not match."
            )

        # Decode all five formal snapshot sections.
        snapshot_fields = (
            ("state", "state_json"),
            ("form_data", "form_data_json"),
            ("control_data", "control_data_json"),
            ("method_data", "method_data_json"),
            ("report_data", "report_data_json"),
        )

        formal_bundle = {}

        for section_name, column_name in snapshot_fields:
            raw_value = getattr(snapshot, column_name)

            try:
                decoded = json.loads(raw_value)
            except (json.JSONDecodeError, TypeError):
                raise ValueError(
                    "Invalid formal snapshot JSON: "
                    + column_name
                )

            if not isinstance(decoded, dict):
                raise ValueError(
                    "Formal snapshot must contain an object: "
                    + column_name
                )

            formal_bundle[section_name] = decoded

        assert_work_bundle_consistency(
            current,
            formal_bundle,
            formal_id
        )

        result = self.db.execute(
            update(AnalysisWorkDraft)
            .where(
                AnalysisWorkDraft.work_id
                == current["work_id"],
                AnalysisWorkDraft.owner_user_id
                == str(user_id).strip(),
                AnalysisWorkDraft.method_code
                == str(method_code).strip().upper(),
                AnalysisWorkDraft.work_status
                == "EDITING",
                AnalysisWorkDraft.revision
                == expected_revision
            )
            .values(
                formal_analysis_id=formal_id,
                work_status="SUBMITTED",
                revision=expected_revision + 1
            )
        )

        if result.rowcount != 1:
            raise DraftConflictError(
                "Draft was modified by another request."
            )

        self.db.flush()

        return expected_revision + 1

    def save_work_bundle(
        self,
        work_id,
        user_id,
        method_code,
        expected_revision,
        state=None,
        form_data=None,
        control_data=None,
        method_data=None,
        report_data=None
    ):
        current = self.load_draft(
            work_id,
            user_id,
            method_code
        )

        if current["work_status"] != "EDITING":
            raise ValueError(
                "Draft is not editable."
            )

        if (
            type(expected_revision) is not int
            or expected_revision < 0
        ):
            raise ValueError(
                "Invalid expected revision."
            )

        updates = {}

        if state is not None:

            if not isinstance(state, dict):
                raise ValueError(
                    "state must be a dict."
                )

            original_state = current["state"]

            if "parsed_data" in original_state:

                original_parsed_data = original_state[
                    "parsed_data"
                ]

                if (
                    "parsed_data" in state
                    and state["parsed_data"]
                    != original_parsed_data
                ):
                    raise ValueError(
                        "Original parsed_data cannot be modified."
                    )

                state_to_save = dict(state)
                state_to_save[
                    "parsed_data"
                ] = original_parsed_data

            else:
                state_to_save = dict(state)

            updates["state_json"] = json.dumps(
                state_to_save,
                ensure_ascii=False
            )

        sections = (
            ("form_data_json", form_data),
            ("control_data_json", control_data),
            ("method_data_json", method_data),
            ("report_data_json", report_data),
        )

        for column_name, value in sections:

            if value is None:
                continue

            if not isinstance(value, dict):
                raise ValueError(
                    column_name + " must be a dict."
                )

            updates[column_name] = json.dumps(
                value,
                ensure_ascii=False
            )

        if not updates:
            raise ValueError(
                "No work data was provided."
            )

        updates["revision"] = (
            expected_revision + 1
        )

        result = self.db.execute(
            update(AnalysisWorkDraft)
            .where(
                AnalysisWorkDraft.work_id
                == current["work_id"],
                AnalysisWorkDraft.owner_user_id
                == str(user_id).strip(),
                AnalysisWorkDraft.method_code
                == str(method_code).strip().upper(),
                AnalysisWorkDraft.work_status
                == "EDITING",
                AnalysisWorkDraft.revision
                == expected_revision
            )
            .values(**updates)
        )

        if result.rowcount != 1:
            raise DraftConflictError(
                "Draft was modified by another request."
            )

        self.db.flush()

        return expected_revision + 1

    def save_draft(
        self,
        work_id,
        user_id,
        method_code,
        expected_revision,
        state
    ):
        if not isinstance(state, dict):
            raise ValueError("Draft state must be a dict.")

        current = self.load_draft(
            work_id,
            user_id,
            method_code
        )

        if current["work_status"] != "EDITING":
            raise ValueError("Draft is not editable.")

        if (
            type(expected_revision) is not int
            or expected_revision < 0
        ):
            raise ValueError(
                "Invalid expected revision."
            )

        # Preserve original instrument parsing data.
        original_state = current["state"]

        if "parsed_data" in original_state:

            original_parsed_data = original_state[
                "parsed_data"
            ]

            if (
                "parsed_data" in state
                and state["parsed_data"] != original_parsed_data
            ):
                raise ValueError(
                    "Original parsed_data cannot be modified."
                )

            state_to_save = dict(state)
            state_to_save["parsed_data"] = original_parsed_data

        else:
            state_to_save = dict(state)

        result = self.db.execute(
            update(AnalysisWorkDraft)
            .where(
                AnalysisWorkDraft.work_id
                == current["work_id"],
                AnalysisWorkDraft.owner_user_id
                == str(user_id).strip(),
                AnalysisWorkDraft.method_code
                == str(method_code).strip().upper(),
                AnalysisWorkDraft.work_status
                == "EDITING",
                AnalysisWorkDraft.revision
                == expected_revision
            )
            .values(
                state_json=json.dumps(
                    state_to_save,
                    ensure_ascii=False
                ),
                revision=expected_revision + 1
            )
        )

        if result.rowcount != 1:
            raise DraftConflictError(
                "Draft was modified by another request."
            )

        self.db.flush()

        return expected_revision + 1
