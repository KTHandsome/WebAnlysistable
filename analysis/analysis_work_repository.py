from copy import deepcopy

from analysis.analysis_work_identity import (
    AnalysisWorkIdentity,
    assert_work_access,
    validate_work_id,
)


class AnalysisWorkRepository:
    """
    Isolated in-memory analysis work repository.

    Each work_id has an independent identity and state.
    This repository does not provide persistence.
    """

    def __init__(self):
        self._identities = {}
        self._states = {}

    def create_work(self, identity):
        if not isinstance(identity, AnalysisWorkIdentity):
            raise ValueError("Invalid Analysis Work identity.")

        work_id = validate_work_id(identity.work_id)

        if work_id in self._identities:
            raise ValueError("Analysis Work already exists.")

        if not identity.owner_user_id.strip():
            raise ValueError("Analysis Work owner is required.")

        if not identity.method_code.strip():
            raise ValueError("Analysis Work method is required.")

        self._identities[work_id] = identity
        return work_id

    def _require_access(self, work_id, user_id, method_code):
        canonical_id = validate_work_id(work_id)

        identity = self._identities.get(canonical_id)

        assert_work_access(
            identity,
            user_id,
            method_code
        )

        return canonical_id

    def get_work_identity(self, work_id, user_id, method_code):
        canonical_id = self._require_access(
            work_id, user_id, method_code
        )

        return self._identities[canonical_id]

    def save_state(self, work_id, user_id, method_code, state):
        canonical_id = self._require_access(
            work_id, user_id, method_code
        )

        if not isinstance(state, dict):
            raise ValueError("Analysis state must be a dict.")

        self._states[canonical_id] = deepcopy(state)
        return True

    def load_state(self, work_id, user_id, method_code):
        canonical_id = self._require_access(
            work_id, user_id, method_code
        )

        state = self._states.get(canonical_id)

        if state is None:
            return None

        return deepcopy(state)

    def update_state(self, work_id, user_id, method_code, updates):
        canonical_id = self._require_access(
            work_id, user_id, method_code
        )

        if not isinstance(updates, dict):
            raise ValueError("Analysis updates must be a dict.")

        if "parsed_data" in updates:
            raise ValueError(
                "Original parsed_data cannot be updated."
            )

        if canonical_id not in self._states:
            return False

        reserved_fields = {
            "work_id",
            "owner_user_id",
            "method_code",
            "formal_analysis_id",
        }

        if reserved_fields.intersection(updates):
            raise ValueError(
                "Analysis Work identity fields cannot be updated."
            )

        updated_state = deepcopy(self._states[canonical_id])
        updated_state.update(deepcopy(updates))

        self._states[canonical_id] = updated_state
        return True

    def clear_state(self, work_id, user_id, method_code):
        canonical_id = self._require_access(
            work_id, user_id, method_code
        )

        return self._states.pop(canonical_id, None) is not None
