from services.icp_batch_category_service import build_batch_memberships
from analysis.icp_batch_adoption import context, excluded, group_is_active, filter_lims_matches
"""Read-only ICP channel view; never changes imported work or calculates results."""
from copy import deepcopy
from services.icp_lims_decision_service import manual_adoption_options
from analysis.icp_workflow import (
    build_sample_candidate_groups, build_icp_candidate_selections,
)


def _text(value):
    return str(value if value is not None else "").strip()


def build_icp_data_view(work, lims_matches, lookup_error=None, include_excluded=False):
    _, assignments, hidden = context(work)
    if not include_excluded:
        lims_matches = filter_lims_matches(work, lims_matches)
    manual_options = manual_adoption_options(work, lims_matches) if not lookup_error else {}
    rows = (work.get("parsed_data") or {}).get("rows") or []
    memberships = build_batch_memberships(rows)
    groups = build_icp_candidate_selections(
        build_sample_candidate_groups(rows), work.get("candidate_selections") or {},
    )
    channels = {}
    for source in rows:
        element, wavelength = _text(source.get("element")), _text(source.get("wavelength"))
        if not element or not wavelength:
            continue
        key = element + "|" + wavelength
        channel = channels.setdefault(key, {
            "key": key, "label": element + wavelength + "nm",
            "element": element, "wavelength": wavelength,
            "rows": [], "standards": [], "performance": [],
            "sample_groups": [], "qaqc_rows": [], "other_rows": [],
        })
        row_batches = memberships.get(_text(source.get("sequence")), [])
        if not include_excluded and (key in hidden or (row_batches and all(excluded(work, bid, key) for bid in row_batches))):
            continue
        row = deepcopy(source)
        channel["rows"].append(row)
        role = _text(row.get("role")).upper()
        if role in {"PFM", "PRM"} or _text(row.get("sample_label")).upper() == "PFM":
            channel["performance"].append(row)
        elif role == "STANDARD":
            channel["standards"].append(row)
        elif role in {"ICBK", "ICV", "BK", "QC", "DUP", "MS", "MSD", "CCBK", "CCV"}:
            channel["qaqc_rows"].append(row)
        elif role != "SAMPLE":
            channel["other_rows"].append(row)
    decisions = work.get("lims_decisions") or {}
    for source in groups:
        channel_key = _text(source.get("element")) + "|" + _text(source.get("wavelength"))
        channel = channels.get(channel_key)
        if channel is None:
            continue
        if not include_excluded and not group_is_active(work, source, assignments, hidden):
            continue
        group = deepcopy(source)
        chosen = [candidate for candidate in group["candidates"]
                  if group["selected_sequence"] is not None
                  and str(candidate.get("sequence")) == str(group["selected_sequence"])]
        group["selected"] = chosen[0] if len(chosen) == 1 else None
        group["lims_items"] = []
        identity = (_text(group.get("keepid")).upper(), _text(group.get("element")),
                    _text(group.get("analyte_variant") or "TOTAL_OR_UNSPECIFIED").upper(),
                    _text(group.get("pdf_sample_tag")).upper())
        for item in lims_matches:
            item_identity = (_text(item.get("keepid")).upper(), _text(item.get("element")),
                             _text(item.get("analyte_variant") or "TOTAL_OR_UNSPECIFIED").upper(),
                             _text(item.get("pdf_sample_tag")).upper())
            if item_identity != identity:
                continue
            entry = deepcopy(item)
            key = identity[0] + "|" + _text(item.get("examno")).upper()
            saved = decisions.get(key)
            allowed = {"ACCEPT", "PENDING", "REJECT"} if item.get("status") == "METHOD_MATCHED" else (
                {"PENDING", "REJECT"} if item.get("status") == "CROSS_METHOD_REVIEW" else {"REJECT"})
            decision = _text(item.get("user_decision") or "REJECT").upper()
            if isinstance(saved, dict) and _text(saved.get("decision")).upper() in allowed:
                decision = _text(saved["decision"]).upper()
            entry["user_decision"] = decision if decision in allowed else "PENDING"
            group["lims_items"].append(entry)
        option = manual_options.get(group["selection_key"], {})
        group["manual_adoption"] = (deepcopy(option.get("record"))
                                    if option.get("decision") == "ACCEPT" else None)
        group["ready_for_next_step"] = bool(group["selected"] and not lookup_error and (
            group["manual_adoption"] or any(
                x.get("examno") and x["user_decision"] == "ACCEPT" for x in group["lims_items"])))
        channel["sample_groups"].append(group)
    if not include_excluded:
        channels = {key: value for key, value in channels.items() if key not in hidden}
    result = sorted(channels.values(), key=lambda item: (item["element"], item["wavelength"]))
    for channel in result:
        channel["sample_count"] = len(channel["sample_groups"])
        channel["selected_count"] = sum(bool(x["selected"]) for x in channel["sample_groups"])
        channel["accepted_count"] = sum(x["ready_for_next_step"] for x in channel["sample_groups"])
    return result
