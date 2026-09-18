import math


def calculate_calibration(standard_rows):
    """
    W43401 檢量線計算

    standard_rows 格式：
    [
        {
            "sequence_no": 1,
            "sample_id": "0",
            "signal": -0.0,
            "role": "STANDARD",
            "calibration_x": 0.0
        },
        ...
    ]

    計算：
    Y = aX + b

    回算：
    X = (Y - b) / a

    判定：
    r > 0.995
    """

    points = []

    for row in standard_rows:

        if row.get("role") != "STANDARD":
            continue

        x = row.get("calibration_x")
        y = row.get("signal")

        if x is None or y is None:
            continue

        points.append(
            {
                "sequence_no": row.get("sequence_no"),
                "sample_id": row.get("sample_id", ""),
                "x": float(x),
                "y": float(y)
            }
        )

    if len(points) < 2:
        raise ValueError("檢量線至少需要 2 個有效標準點。")

    n = len(points)

    sum_x = sum(p["x"] for p in points)
    sum_y = sum(p["y"] for p in points)

    sum_x2 = sum(
        p["x"] ** 2
        for p in points
    )

    sum_y2 = sum(
        p["y"] ** 2
        for p in points
    )

    sum_xy = sum(
        p["x"] * p["y"]
        for p in points
    )

    denominator = (
        n * sum_x2
        - sum_x ** 2
    )

    if denominator == 0:
        raise ValueError("檢量線 X 值無法進行線性迴歸。")

    slope = (
        n * sum_xy
        - sum_x * sum_y
    ) / denominator

    intercept = (
        sum_y
        - slope * sum_x
    ) / n

    r_denominator = math.sqrt(
        (
            n * sum_x2
            - sum_x ** 2
        )
        *
        (
            n * sum_y2
            - sum_y ** 2
        )
    )

    if r_denominator == 0:
        raise ValueError("無法計算檢量線相關係數 r。")

    r = (
        n * sum_xy
        - sum_x * sum_y
    ) / r_denominator

    calculated_points = []

    for point in points:

        back_calculated_x = None
        back_calculation_error_percent = None

        if slope != 0:

            back_calculated_x = (
                point["y"] - intercept
            ) / slope

       # X = 0 時無法計算百分比偏差
        if point["x"] != 0:

            back_calculation_error_percent = (
                (
                    back_calculated_x
                    - point["x"]
                )
                / point["x"]
                * 100
            )

        calculated_points.append(
            {
                "sequence_no": point["sequence_no"],
                "sample_id": point["sample_id"],
                "x": point["x"],
                "y": point["y"],
                "back_calculated_x": back_calculated_x,
                "back_calculation_error_percent":
                back_calculation_error_percent
            }
        )

    passed = r > 0.995

    return {
        "slope": slope,
        "intercept": intercept,
        "r": r,
        "passed": passed,
        "points": calculated_points
    }

def calculate_sample_concentration(
    signal,
    slope,
    intercept,
    sample_volume=25.0,
    final_volume=50.0,
    dilution_factor=1.0
):
    """
    一般樣品濃度計算。

    X = (Y - b) / a

    最終濃度 =
        X
        × (final_volume / sample_volume)
        × dilution_factor
    """

    if slope == 0:
        raise ValueError("檢量線斜率不得為 0。")

    if sample_volume <= 0:
        raise ValueError("取樣體積必須大於 0。")

    if final_volume <= 0:
        raise ValueError("最終定量體積必須大於 0。")

    if dilution_factor <= 0:
        raise ValueError("樣品稀釋倍數 D 必須大於 0。")

    back_calculated_concentration = (
        float(signal) - float(intercept)
    ) / float(slope)

    volume_factor = (
        float(final_volume)
        / float(sample_volume)
    )

    calculated_concentration = (
        back_calculated_concentration
        * volume_factor
        * float(dilution_factor)
    )

    return {
        "back_calculated_concentration":
            back_calculated_concentration,

        "volume_factor":
            volume_factor,

        "dilution_factor":
            float(dilution_factor),

        "calculated_concentration":
            calculated_concentration
    }
