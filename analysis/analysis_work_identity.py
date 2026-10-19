from dataclasses import dataclass
from typing import Optional
from uuid import UUID, uuid4


@dataclass(frozen=True)
class AnalysisWorkIdentity:
    work_id: str
    owner_user_id: str
    method_code: str
    formal_analysis_id: Optional[str] = None


def normalize_user_id(user_id):
    value = str(user_id or "").strip()

    if not value:
        raise ValueError(
            "Analysis Work requires a valid user_id."
        )

    return value


def normalize_method_code(method_code):
    value = str(method_code or "").strip().upper()

    if not value:
        raise ValueError(
            "Analysis Work requires a method_code."
        )

    return value


def validate_work_id(work_id):
    value = str(work_id or "").strip()

    try:
        parsed = UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ValueError(
            "Invalid Analysis Work ID."
        )

    if str(parsed) != value.lower():
        raise ValueError(
            "Analysis Work ID must use canonical UUID format."
        )

    return str(parsed)


def create_work_identity(
    owner_user_id,
    method_code,
    formal_analysis_id=None
):
    owner = normalize_user_id(owner_user_id)
    method = normalize_method_code(method_code)

    formal_id = (
        str(formal_analysis_id).strip()
        if formal_analysis_id is not None
        else None
    )

    if formal_id == "":
        formal_id = None

    return AnalysisWorkIdentity(
        work_id=str(uuid4()),
        owner_user_id=owner,
        method_code=method,
        formal_analysis_id=formal_id
    )


def assert_work_access(
    identity,
    user_id,
    method_code
):
    if not isinstance(identity, AnalysisWorkIdentity):
        raise ValueError(
            "Analysis Work does not exist."
        )

    validate_work_id(identity.work_id)

    current_user = normalize_user_id(user_id)
    current_method = normalize_method_code(method_code)

    if identity.owner_user_id != current_user:
        raise PermissionError(
            "Access to this Analysis Work is denied."
        )

    if identity.method_code != current_method:
        raise PermissionError(
            "Analysis Work method does not match."
        )

    return True
