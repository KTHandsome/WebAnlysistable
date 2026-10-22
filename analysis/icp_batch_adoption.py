"""Explicit per-batch/channel exclusions; raw imported rows are never changed."""
from analysis.icp_workflow import build_sample_candidate_groups, build_icp_candidate_selections

EXCLUDE_VALUE = "__EXCLUDE__"


def text(value):
    return str(value if value is not None else "").strip()


def identity(item):
    return (text(item.get("keepid")).upper(), text(item.get("element")),
            text(item.get("analyte_variant") or "TOTAL_OR_UNSPECIFIED").upper(),
            text(item.get("pdf_sample_tag")).upper())


def excluded(work, batch_id, channel_key):
    entry = ((work.get("batch_categories") or {}).get(text(batch_id)) or {})
    return (entry.get("is_excluded") is True or entry.get("category") == EXCLUDE_VALUE
            or ((entry.get("channels") or {}).get(channel_key) or {}).get("is_excluded") is True)


def context(work):
    from services.icp_batch_category_service import build_batches
    rows = (work.get("parsed_data") or {}).get("rows") or []
    batches, assignments, _ = build_batches(rows)
    keys = {text(r.get("element")) + "|" + text(r.get("wavelength")) for r in rows
            if text(r.get("element")) and text(r.get("wavelength"))}
    hidden = {key for key in keys if batches and all(excluded(work, b["id"], key) for b in batches)}
    return rows, assignments, hidden


def group_is_active(work, group, assignments, hidden):
    key = text(group.get("element")) + "|" + text(group.get("wavelength"))
    if key in hidden:
        return False
    selected = group.get("selected_sequence")
    sequences = ([selected] if selected is not None else
                 [c.get("sequence") for c in group.get("candidates", [])])
    return any(not excluded(work, assignments.get(text(seq)), key) for seq in sequences)


def filter_lims_matches(work, matches):
    if not isinstance(work, dict):
        return matches
    rows, assignments, hidden = context(work)
    groups = build_icp_candidate_selections(build_sample_candidate_groups(rows), work.get("candidate_selections") or {})
    by_identity = {}
    for group in groups:
        by_identity.setdefault(identity(group), []).append(group)
    known = {text(r.get("element")) for r in rows if text(r.get("element"))}
    active_elements = {text(r.get("element")) for r in rows
                       if text(r.get("element")) + "|" + text(r.get("wavelength")) not in hidden}
    result = []
    for item in matches:
        candidates = by_identity.get(identity(item), [])
        if candidates:
            if any(group_is_active(work, g, assignments, hidden) for g in candidates):
                result.append(item)
        elif text(item.get("element")) not in known or text(item.get("element")) in active_elements:
            result.append(item)
    return result


def filter_lims_groups(work, groups):
    """Apply the same exclusion to the supplementary LIMS details table."""
    from copy import deepcopy
    result = []
    for source in groups:
        group = deepcopy(source)
        mapped = [dict(item, keepid=group["keepid"]) for item in group.get("matched_rows", [])]
        active = filter_lims_matches(work, mapped)
        kept = {text(item.get("examno")).upper() for item in active}
        removed = {text(item.get("examno")).upper() for item in mapped} - kept
        group["matched_rows"] = [item for item in group.get("matched_rows", [])
                                 if text(item.get("examno")).upper() not in removed]
        group["analysis_rows"] = [item for item in group.get("analysis_rows", [])
                                  if text(item.get("examno")).upper() not in removed]
        if source.get("found") and not group["analysis_rows"]:
            continue
        result.append(group)
    return result


def active_candidate_groups(work, groups):
    """Skip excluded batches before LIMS I/O, preserving raw/candidate previews."""
    if not isinstance(work, dict):
        return groups
    _, assignments, hidden = context(work)
    selected = build_icp_candidate_selections(groups, work.get("candidate_selections") or {})
    return [group for group in selected if group_is_active(work, group, assignments, hidden)]
