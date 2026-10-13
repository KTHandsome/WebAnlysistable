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

        analyte_variant = row.get(
          "analyte_variant",
          "TOTAL_OR_UNSPECIFIED"
        )

        pdf_sample_tag = row.get(
    "pdf_sample_tag",
    ""
)

        key = (
               keepid,
               row["element"],
               row["wavelength"],
               analyte_variant,
               pdf_sample_tag,
        )

        if key not in groups:
            groups[key] = {
                "keepid": keepid,
                "element": row["element"],
                "wavelength": row["wavelength"],
                "analyte_variant": analyte_variant,
                "pdf_sample_tag": pdf_sample_tag,
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
            "analyte_variant": analyte_variant,
            "pdf_sample_tag": pdf_sample_tag,
        })

    return list(groups.values())

def build_icp_candidate_selections(
    candidate_groups,
    saved_selections=None
):
    """
    建立 ICP 候選量測選取狀態。

    1 筆候選：自動選取。
    2 筆以上：沒有人工選擇時保持待選。
    已儲存選擇：確認序號仍存在後才還原。
    """

    saved_selections = saved_selections or {}
    results = []

    for group in candidate_groups:

        keepid = str(
            group.get("keepid") or ""
        ).strip().upper()

        element = str(
            group.get("element") or ""
        ).strip()

        wavelength = str(
            group.get("wavelength") or ""
        ).strip()

        variant = str(
            group.get("analyte_variant")
            or "TOTAL_OR_UNSPECIFIED"
        ).strip().upper()

        pdf_tag = str(
            group.get("pdf_sample_tag") or ""
        ).strip().upper()

        selection_key = "|".join([
            keepid,
            element,
            wavelength,
            variant,
            pdf_tag
        ])

        candidates = group.get("candidates") or []

        selected_sequence = None
        selection_status = "PENDING_SELECTION"

        if len(candidates) == 1:

            selected_sequence = candidates[0].get(
                "sequence"
            )

            selection_status = "AUTO_SELECTED"

        elif len(candidates) > 1:

            saved = saved_selections.get(
                selection_key
            )

            if isinstance(saved, dict):

                saved_sequence = saved.get(
                    "sequence"
                )

                for candidate in candidates:

                    if str(
                        candidate.get("sequence")
                    ) == str(saved_sequence):

                        selected_sequence = (
                            candidate.get("sequence")
                        )

                        selection_status = (
                            "USER_SELECTED"
                        )

                        break

        results.append({
            **group,
            "selection_key": selection_key,
            "selected_sequence": selected_sequence,
            "selection_status": selection_status,
        })

    return results

def load_icp_analyte_map(csv_path):
    """
    載入 ICP 適用測項對照表。
    保留一般測項與溶解態測項的獨立身分。
    """
    import csv

    analyte_map = {}

    with open(
        csv_path,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            if str(
                row.get("ACTIVE") or ""
            ).strip().upper() != "Y":
                continue

            examname = str(
                row.get("EXAMNAME") or ""
            ).strip()

            element = str(
                row.get("ELEMENT") or ""
            ).strip()

            variant = str(
                row.get("ANALYTE_VARIANT") or ""
            ).strip().upper()

            if not examname or not element:
                continue

            analyte_map[examname] = {
              "element": element,
              "variant": variant,
              "examname": examname,
              "pdf_sample_tag": str(
                  row.get("PDF_SAMPLE_TAG") or ""
               ).strip().upper(),
            }

    return analyte_map

def match_lims_icp_analytes(lims_rows, analyte_map):
    """
    將 LIMS 委測項目與 ICP 適用測項對照表配對。

    優先 EXAMNAME 精確比對，
    EXALIAS 僅作輔助比對。
    不依 EM_NUM 篩選。
    """
    matched_rows = []
    unmatched_rows = []

    for row in lims_rows:

        examname = str(
            row.get("examname") or ""
        ).strip()

        exalias = str(
            row.get("exalias") or ""
        ).strip()

        matched = analyte_map.get(examname)
        match_source = "EXAMNAME"

        if matched is None and exalias:
            matched = analyte_map.get(exalias)
            match_source = "EXALIAS"

        result = dict(row)

        if matched is not None:
            result["element"] = matched["element"]
            result["analyte_variant"] = matched["variant"]
            result["pdf_sample_tag"] = matched.get(
                   "pdf_sample_tag", ""
                   )
            result["map_examname"] = matched["examname"]
            result["match_source"] = match_source
            result["match_status"] = "MATCHED"

            matched_rows.append(result)

        else:
            result["element"] = ""
            result["analyte_variant"] = ""
            result["map_examname"] = ""
            result["match_source"] = ""
            result["match_status"] = "UNMATCHED"

            unmatched_rows.append(result)

    return {
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows
    }

def build_icp_lims_matches(
    candidate_groups,
    lims_match_groups,
    phyon_method
):
    """
    建立 ICP PDF 候選量測與 LIMS 委測項目的對應。

    不修改原始候選資料。
    不自動選定正式結果。
    不寫入 LIMS。
    """

    phyon_method = str(
        phyon_method or ""
    ).strip().upper()

    candidate_index = {}

    # ========================================
    # 1. 建立 PDF 候選量測索引
    # ========================================
    for group in candidate_groups:

        key = (
            str(group.get("keepid") or "").strip().upper(),
            str(group.get("element") or "").strip(),
            str(
                group.get("analyte_variant")
                or "TOTAL_OR_UNSPECIFIED"
            ).strip().upper(),
            str(group.get("pdf_sample_tag") or "").strip().upper(),
        )

        candidate_index.setdefault(
            key, []
        ).append(group)

    results = []
    matched_candidate_keys = set()

    # ========================================
    # 2. 依 LIMS 正式 EXAMNO 建立配對
    # ========================================
    for lims_group in lims_match_groups:

        keepid = str(
            lims_group.get("keepid") or ""
        ).strip().upper()

        for item in lims_group.get("matched_rows", []):

            element = str(
                item.get("element") or ""
            ).strip()

            variant = str(
                item.get("analyte_variant")
                or "TOTAL_OR_UNSPECIFIED"
            ).strip().upper()

            pdf_tag = str(
                item.get("pdf_sample_tag") or ""
            ).strip().upper()

            key = (
                keepid,
                element,
                variant,
                pdf_tag,
            )

            candidates = candidate_index.get(
                key, []
            )

            if candidates:
                matched_candidate_keys.add(key)

            lims_method = str(
                item.get("em_num") or ""
            ).strip().upper()

            # ========================================
            # 配對狀態判斷
            # ========================================
            if not candidates:
                status = "NO_PDF_MEASUREMENT"

            elif lims_method == phyon_method:
                status = "METHOD_MATCHED"

            else:
                status = "CROSS_METHOD_REVIEW"

            # B 方案：系統預設決定
            if status == "METHOD_MATCHED":
                default_decision = "ACCEPT"

            elif status == "CROSS_METHOD_REVIEW":
                default_decision = "PENDING"

            else:
                default_decision = "REJECT"

            # 每個 LIMS 委測項目只加入一次
            results.append({
                "keepid": keepid,
                "examno": item.get("examno", ""),
                "examname": item.get("examname", ""),
                "exalias": item.get("exalias", ""),
                "element": element,
                "analyte_variant": variant,
                "pdf_sample_tag": pdf_tag,
                "lims_method": lims_method,
                "phyon_method": phyon_method,
                "status": status,
                "candidate_groups": candidates,
                "candidate_group_count": len(candidates),
                "user_decision": default_decision,
            })

    # ========================================
    # 3. 找出 PDF 有量測但 LIMS 未配對的資料
    # ========================================
    for key, candidates in candidate_index.items():

        if key in matched_candidate_keys:
            continue

        keepid, element, variant, pdf_tag = key

        results.append({
            "keepid": keepid,
            "examno": "",
            "examname": "",
            "exalias": "",
            "element": element,
            "analyte_variant": variant,
            "pdf_sample_tag": pdf_tag,
            "lims_method": "",
            "phyon_method": phyon_method,
            "status": "NOT_COMMISSIONED",
            "candidate_groups": candidates,
            "candidate_group_count": len(candidates),
            "user_decision": "REJECT",
        })

    return results