(function () {

    "use strict";

    let calibrationState = {
        slope: null,
        intercept: null,
        r: null
    };

    let interpretationState = {
    mdl: null,
    qdl: null,
    blankMdlMultiplier: null
};

function loadInterpretationStateFromPage() {

    const mdlElement =
        document.getElementById("analysis-mdl");

    const qdlElement =
        document.getElementById("analysis-qdl");

    const blankMultiplierElement =
        document.getElementById(
            "blank-mdl-multiplier"
        );

    if (
        !mdlElement
        || !blankMultiplierElement
    ) {
        return;
    }

    const mdl =
        parseFloat(mdlElement.value);

    const qdl =
        qdlElement
            ? parseFloat(qdlElement.value)
            : NaN;

    const blankMdlMultiplier =
        parseFloat(
            blankMultiplierElement.value
        );

    if (Number.isFinite(mdl)) {
        interpretationState.mdl = mdl;
    }

    if (Number.isFinite(qdl)) {
        interpretationState.qdl = qdl;
    }

    if (
        Number.isFinite(
            blankMdlMultiplier
        )
    ) {
        interpretationState.blankMdlMultiplier =
            blankMdlMultiplier;
    }
}


    function loadCalibrationStateFromPage() {

        const slopeElement =
            document.getElementById("calibration-slope");

        const interceptElement =
            document.getElementById("calibration-intercept");

        if (!slopeElement || !interceptElement) {
            return false;
        }

        const slope =
            parseFloat(slopeElement.value);

        const intercept =
            parseFloat(interceptElement.value);

        if (
            !Number.isFinite(slope)
            || slope === 0
            || !Number.isFinite(intercept)
        ) {
            return false;
        }

        calibrationState.slope = slope;
        calibrationState.intercept = intercept;

        return true;
    }


    function recalculateSampleRow(row) {

        if (
            !Number.isFinite(calibrationState.slope)
            || calibrationState.slope === 0
            || !Number.isFinite(calibrationState.intercept)
        ) {
            return;
        }

        const signalInput =
            row.querySelector(
                ".sample-signal-input"
            );

        const dilutionInput =
            row.querySelector(
                ".dilution-factor-input"
            );

        const resultCell =
            row.querySelector(
                ".calculated-concentration-cell"
            );

        if (
            !signalInput
            || !dilutionInput
            || !resultCell
        ) {
            return;
        }

        const signal =
            parseFloat(signalInput.value);

        const dilutionFactor =
            parseFloat(dilutionInput.value);

        if (
            !Number.isFinite(signal)
            || !Number.isFinite(dilutionFactor)
            || dilutionFactor <= 0
        ) {
            resultCell.textContent = "-";
            return;
        }

        const sampleVolume = 25.0;
        const finalVolume = 50.0;

        const backCalculatedConcentration =
            (
                signal
                - calibrationState.intercept
            )
            / calibrationState.slope;

        const calculatedConcentration =
            backCalculatedConcentration
            * (finalVolume / sampleVolume)
            * dilutionFactor;

        resultCell.textContent =
            calculatedConcentration.toFixed(6);

            const interpretationCell =
    row.querySelector(
        ".interpretation-cell"
    );

const roleInput =
    row.querySelector(
        'input[name^="role_"]'
    );

if (
    interpretationCell
    && roleInput
    && window.AnalysisInterpretation
) {

    const role =
        roleInput.value;

    const interpretation =
        window.AnalysisInterpretation.evaluateResult(
            {
                role: role,
                concentration:
                    calculatedConcentration,
                mdl:
                    interpretationState.mdl,
                qdl:
                    interpretationState.qdl,
                blankMdlMultiplier:
                    interpretationState.blankMdlMultiplier,

                blankRoles: [
                    "ICBK",
                    "BK",
                    "CCBK"
                ],

                sampleRoles: [
                    "SAMPLE",
                    "DUP"
                ]
            }
        );

    interpretationCell.textContent =
        interpretation;
}
    }


    function recalculateAllSampleRows() {

        const table =
            document.querySelector(
                ".sample-qaqc-table"
            );

        if (!table) {
            return;
        }

        const rows =
            table.querySelectorAll(
                "tbody tr"
            );

        rows.forEach(
            function (row) {
                recalculateSampleRow(row);
            }
        );
    }

    function updateSampleDisplayOrder() {

    const table =
        document.querySelector(
            ".sample-qaqc-table"
        );

    if (!table) {
        return;
    }

    const rows =
        table.querySelectorAll(
            "tbody .sample-qaqc-row:not(.is-excluded-row)"
        );

    rows.forEach(
        function (row, index) {

            const displayOrder =
                index + 1;

            const orderText =
                row.querySelector(
                    ".display-order-text"
                );

            const orderInput =
                row.querySelector(
                    ".display-order-input"
                );

            if (orderText) {
                orderText.textContent =
                    displayOrder;
            }

            if (orderInput) {
                orderInput.value =
                    displayOrder;
            }


            const upButton =
                row.querySelector(
                    ".move-row-up"
                );

            const downButton =
                row.querySelector(
                    ".move-row-down"
                );


            if (upButton) {
                upButton.disabled =
                    index === 0;
            }

            if (downButton) {
                downButton.disabled =
                    index === rows.length - 1;
            }
        }
    );
}

function bindSampleDeleteEvents() {

    const table =
        document.querySelector(
            ".sample-qaqc-table"
        );

    if (!table) {
        return;
    }

    table.addEventListener(
        "change",
        function (event) {

            const target =
                event.target;

            if (
                !target.classList.contains(
                    "sample-delete-checkbox"
                )
            ) {
                return;
            }

            if (!target.checked) {
                return;
            }

            const row =
                target.closest(
                    ".sample-qaqc-row"
                );

            if (!row) {
                return;
            }

            const confirmed =
                window.confirm(
                    "確定刪除此筆樣品結果？"
                );

            if (!confirmed) {

                target.checked = false;
                return;
            }

            row.classList.add(
                "is-excluded-row"
            );

            row.style.display = "none";

            updateSampleDisplayOrder();
        }
    );
}

function bindSampleRowMoveEvents() {

    const table =
        document.querySelector(
            ".sample-qaqc-table"
        );

    if (!table) {
        return;
    }

    table.addEventListener(
        "click",
        function (event) {

            const target =
                event.target;

            const row =
                target.closest(
                    ".sample-qaqc-row"
                );

            if (!row) {
                return;
            }


            if (
                target.classList.contains(
                    "move-row-up"
                )
            ) {

                const previousRow =
                    row.previousElementSibling;

                if (previousRow) {

                    row.parentNode.insertBefore(
                        row,
                        previousRow
                    );

                    updateSampleDisplayOrder();
                }

                return;
            }


            if (
                target.classList.contains(
                    "move-row-down"
                )
            ) {

                const nextRow =
                    row.nextElementSibling;

                if (nextRow) {

                    row.parentNode.insertBefore(
                        nextRow,
                        row
                    );

                    updateSampleDisplayOrder();
                }
            }
        }
    );
}


    function bindSampleTableEvents() {

        const table =
            document.querySelector(
                ".sample-qaqc-table"
            );

        if (!table) {
            return;
        }

        table.addEventListener(
            "input",
            function (event) {

                const target =
                    event.target;

                if (
                    !target.classList.contains(
                        "sample-signal-input"
                    )
                    &&
                    !target.classList.contains(
                        "dilution-factor-input"
                    )
                ) {
                    return;
                }

                const row =
                    target.closest("tr");

                if (row) {
                    recalculateSampleRow(row);
                }
            }
        );
    }

    function calculateLinearRegression(points) {

    const count =
        points.length;

    if (count < 2) {
        return null;
    }

    let sumX = 0;
    let sumY = 0;
    let sumXY = 0;
    let sumXX = 0;
    let sumYY = 0;

    points.forEach(
        function (point) {

            sumX += point.x;
            sumY += point.y;

            sumXY +=
                point.x * point.y;

            sumXX +=
                point.x * point.x;

            sumYY +=
                point.y * point.y;
        }
    );


    const denominator =
        count * sumXX
        - sumX * sumX;

    if (denominator === 0) {
        return null;
    }


    const slope =
        (
            count * sumXY
            - sumX * sumY
        )
        / denominator;


    const intercept =
        (
            sumY
            - slope * sumX
        )
        / count;


    const correlationDenominator =
        Math.sqrt(
            (
                count * sumXX
                - sumX * sumX
            )
            *
            (
                count * sumYY
                - sumY * sumY
            )
        );


    if (correlationDenominator === 0) {
        return null;
    }


    const r =
        (
            count * sumXY
            - sumX * sumY
        )
        / correlationDenominator;


    return {
        slope: slope,
        intercept: intercept,
        r: r
    };
}

function getCalibrationPointsFromPage() {

    const rows =
        document.querySelectorAll(
            ".calibration-row"
        );

    const points = [];

    for (const row of rows) {

        const x =
            parseFloat(
                row.dataset.calibrationX
            );

        const signalInput =
            row.querySelector(
                ".calibration-signal-input"
            );

        if (!signalInput) {
            return null;
        }

        const y =
            parseFloat(
                signalInput.value
            );

        if (
            !Number.isFinite(x)
            || !Number.isFinite(y)
        ) {
            return null;
        }

        points.push(
            {
                row: row,
                x: x,
                y: y
            }
        );
    }

    return points;
}

function updateCalibrationDisplay(
    points,
    result
) {

    const slopeDisplay =
        document.getElementById(
            "calibration-slope-display"
        );

    const interceptDisplay =
        document.getElementById(
            "calibration-intercept-display"
        );

    const rDisplay =
        document.getElementById(
            "calibration-r-display"
        );

    const passDisplay =
        document.getElementById(
            "calibration-pass-display"
        );

    const equationDisplay =
        document.getElementById(
            "calibration-equation-display"
        );


    if (slopeDisplay) {

        slopeDisplay.textContent =
            result.slope.toFixed(5);
    }


    if (interceptDisplay) {

        interceptDisplay.textContent =
            result.intercept.toFixed(5);
    }


    if (rDisplay) {

        rDisplay.textContent =
            result.r.toFixed(6);
    }


    const passed =
        result.r > 0.995;


    if (passDisplay) {

        passDisplay.textContent =
            passed
                ? "合格"
                : "不合格";

        passDisplay.style.color =
            passed
                ? "#22863a"
                : "#c62828";
    }


    if (equationDisplay) {

        const sign =
            result.intercept >= 0
                ? "+"
                : "-";

        equationDisplay.textContent =
            "Y = "
            + result.slope.toFixed(5)
            + " X "
            + sign
            + " "
            + Math.abs(
                result.intercept
            ).toFixed(5);
    }


    points.forEach(
        function (point) {

            const backCalcCell =
                point.row.querySelector(
                    ".calibration-backcalc-cell"
                );

            const errorCell =
                point.row.querySelector(
                    ".calibration-error-cell"
                );


            const backCalculatedX =
                (
                    point.y
                    - result.intercept
                )
                / result.slope;


            if (backCalcCell) {

                backCalcCell.textContent =
                    backCalculatedX.toFixed(7);
            }


            if (errorCell) {

                if (point.x === 0) {

                    errorCell.textContent =
                        "-";

                } else {

                    const errorPercent =
                        (
                            (
                                backCalculatedX
                                - point.x
                            )
                            / point.x
                        )
                        * 100;

                    errorCell.textContent =
                        errorPercent.toFixed(2);
                }
            }
        }
    );
}

function recalculateCalibration() {

    const points =
        getCalibrationPointsFromPage();

    if (
        !points
        || points.length < 2
    ) {
        return;
    }


    const result =
        calculateLinearRegression(
            points
        );

    if (!result) {
        return;
    }


    updateCalibrationDisplay(
        points,
        result
    );


    document.dispatchEvent(
        new CustomEvent(
            "calibrationUpdated",
            {
                detail: {
                    slope:
                        result.slope,

                    intercept:
                        result.intercept,

                    r:
                        result.r
                }
            }
        )
    );
}

function bindCalibrationTableEvents() {

    const calibrationRows =
        document.querySelectorAll(
            ".calibration-row"
        );

    if (
        calibrationRows.length === 0
    ) {
        return;
    }


    calibrationRows.forEach(
        function (row) {

            const signalInput =
                row.querySelector(
                    ".calibration-signal-input"
                );

            if (!signalInput) {
                return;
            }


            signalInput.addEventListener(
                "input",
                function () {

                    recalculateCalibration();
                }
            );
        }
    );
}

    function bindCalibrationUpdateEvent() {

        document.addEventListener(
            "calibrationUpdated",
            function (event) {

                if (!event.detail) {
                    return;
                }

                const slope =
                    parseFloat(
                        event.detail.slope
                    );

                const intercept =
                    parseFloat(
                        event.detail.intercept
                    );

                const r =
                    parseFloat(
                        event.detail.r
                    );

                if (
                    !Number.isFinite(slope)
                    || slope === 0
                    || !Number.isFinite(intercept)
                ) {
                    return;
                }

                calibrationState.slope =
                    slope;

                calibrationState.intercept =
                    intercept;

                const slopeElement =
                    document.getElementById(
                        "calibration-slope"
                    );

                const interceptElement =
                    document.getElementById(
                        "calibration-intercept"
                    );

                if (slopeElement) {
                    slopeElement.value = slope;
                }

                if (interceptElement) {
                    interceptElement.value = intercept;
                }

                if (Number.isFinite(r)) {
                    calibrationState.r = r;
                }

                recalculateAllSampleRows();
            }
        );
    }


function initializeAnalysisCalculation() {

    const calibrationLoaded =
        loadCalibrationStateFromPage();

    loadInterpretationStateFromPage();

    bindCalibrationTableEvents();

    bindSampleTableEvents();

    bindSampleDeleteEvents();

    bindSampleRowMoveEvents();

    bindCalibrationUpdateEvent();

    updateSampleDisplayOrder();

    if (calibrationLoaded) {
        recalculateAllSampleRows();
    }
}


    document.addEventListener(
        "DOMContentLoaded",
        initializeAnalysisCalculation
    );


    window.AnalysisCalculation = {

        recalculateSampleRow:
            recalculateSampleRow,

        recalculateAllSampleRows:
            recalculateAllSampleRows

    };

})();