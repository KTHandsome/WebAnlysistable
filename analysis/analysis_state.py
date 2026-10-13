_analysis_states = {}


def save_analysis_state(
    analysis_key,
    state_data
):
    _analysis_states[analysis_key] = state_data


def load_analysis_state(
    analysis_key
):
    return _analysis_states.get(
        analysis_key
    )


def clear_analysis_state(
    analysis_key
):
    if analysis_key in _analysis_states:
        del _analysis_states[
            analysis_key
        ]

def update_analysis_state(analysis_key, updates):
    """
    更新既有分析暫存的指定欄位，
    不覆蓋其他原始資料。

    此版本仍使用記憶體暫存。
    """

    state = load_analysis_state(analysis_key)

    if state is None:
        return False

    if not isinstance(updates, dict):
        raise ValueError(
            "分析暫存更新資料必須為 dict。"
        )

    if "parsed_data" in updates:
        raise ValueError(
            "不得透過此函式覆蓋原始 PDF 解析資料。"
        )

    state.update(updates)

    return True