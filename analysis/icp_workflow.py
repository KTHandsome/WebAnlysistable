def build_sample_candidate_groups(rows):
    groups = {}

    for row in rows:
        if row.get("role") != "SAMPLE":
            continue

        if row.get("element_applicability") != "APPLICABLE":
            continue

        keepid = row.get("lims_keepid", "")

        if not keepid:
            continue

        key = (
            keepid,
            row["element"],
            row["wavelength"],
        )

        if key not in groups:
            groups[key] = {
                "keepid": keepid,
                "element": row["element"],
                "wavelength": row["wavelength"],
                "candidates": [],
            }

        groups[key]["candidates"].append({
            "sequence": row["sequence"],
            "sample_label": row["sample_label"],
            "measured_at": row["measured_at"],
            "dilution_factor": row["label_dilution_factor"],
            "instrument_concentration": (
                row["instrument_concentration"]
            ),
            "instrument_concentration_flag": (
                row["instrument_concentration_flag"]
            ),
        })

    return list(groups.values())