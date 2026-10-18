def get_method_volume_defaults(
    method_data
):

    sample_volume = float(
        method_data.get(
            "SAMPLE_VOLUME_DEFAULT",
            ""
        )
    )

    final_volume = float(
        method_data.get(
            "FINAL_VOLUME_DEFAULT",
            ""
        )
    )

    return (
        sample_volume,
        final_volume
    )
