(function () {

    "use strict";

    function formatLimit(value) {

        if (!Number.isFinite(value)) {
            return "";
        }

        return String(
            Number(
                value.toPrecision(10)
            )
        );
    }


    function evaluateBlankResult(
        concentration,
        mdl,
        blankMdlMultiplier
    ) {

        if (
            !Number.isFinite(concentration)
            || !Number.isFinite(mdl)
            || !Number.isFinite(blankMdlMultiplier)
        ) {
            return "";
        }

        const blankLimit =
            mdl * blankMdlMultiplier;

        if (concentration < blankLimit) {

            return (
                "<"
                + formatLimit(blankMdlMultiplier)
                + "MDL"
            );
        }

        return "";
    }


    function evaluateSampleResult(
        concentration,
        mdl,
        qdl
    ) {

        if (
            !Number.isFinite(concentration)
            || !Number.isFinite(mdl)
        ) {
            return "";
        }

        if (concentration < mdl) {

            return (
                "ND<"
                + formatLimit(mdl)
            );
        }

        if (
            Number.isFinite(qdl)
            && concentration < qdl
        ) {

            return (
                "<QDL="
                + formatLimit(qdl)
            );
        }

        return "";
    }


    function evaluateResult(options) {

        const role =
            String(
                options.role || ""
            ).trim().toUpperCase();

        const concentration =
            Number(options.concentration);

        const mdl =
            Number(options.mdl);

        const qdl =
            Number(options.qdl);

        const blankMdlMultiplier =
            Number(
                options.blankMdlMultiplier
            );


        const blankRoles =
            options.blankRoles || [];

        const sampleRoles =
            options.sampleRoles || [];


        if (blankRoles.includes(role)) {

            return evaluateBlankResult(
                concentration,
                mdl,
                blankMdlMultiplier
            );
        }


        if (sampleRoles.includes(role)) {

            return evaluateSampleResult(
                concentration,
                mdl,
                qdl
            );
        }


        return "";
    }


    window.AnalysisInterpretation = {

        evaluateResult:
            evaluateResult,

        evaluateBlankResult:
            evaluateBlankResult,

        evaluateSampleResult:
            evaluateSampleResult

    };

})();