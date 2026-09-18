from calculations.w43401 import calculate_calibration


rows = [
    {
        "sequence_no": 1,
        "sample_id": "std0",
        "signal": 0.0000,
        "role": "STANDARD",
        "calibration_x": 0.0
    },
    {
        "sequence_no": 2,
        "sample_id": "std1",
        "signal": 0.0027,
        "role": "STANDARD",
        "calibration_x": 0.25
    },
    {
        "sequence_no": 3,
        "sample_id": "std2",
        "signal": 0.0089,
        "role": "STANDARD",
        "calibration_x": 0.5
    },
    {
        "sequence_no": 4,
        "sample_id": "std3",
        "signal": 0.0182,
        "role": "STANDARD",
        "calibration_x": 1.0
    },
    {
        "sequence_no": 5,
        "sample_id": "std4",
        "signal": 0.0505,
        "role": "STANDARD",
        "calibration_x": 2.5
    },
    {
        "sequence_no": 6,
        "sample_id": "std5",
        "signal": 0.0993,
        "role": "STANDARD",
        "calibration_x": 5.0
    }
]


result = calculate_calibration(rows)

print("Slope a =", result["slope"])
print("Intercept b =", result["intercept"])
print("r =", result["r"])
print("Pass =", result["passed"])
print()

for point in result["points"]:

    print(
        point["sample_id"],
        "X =",
        point["x"],
        "Y =",
        point["y"],
        "回算 X =",
        point["back_calculated_x"],
        "偏差 % =",
        point["back_calculation_error_percent"]
    )