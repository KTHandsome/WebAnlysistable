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