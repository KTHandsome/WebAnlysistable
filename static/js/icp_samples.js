(function () {
    "use strict";
    function start() {
        const form = document.getElementById("icp-samples-form");
        if (!form) return;
        const rows = Array.from(form.querySelectorAll(".icpd-sample-row"));
        function number(value) {
            if (value === null || value === undefined || String(value).trim() === "") return NaN;
            return Number(value);
        }
        function recalculate(row) {
            const config = JSON.parse(row.dataset.calculation);
            const volume = number(row.querySelector('[name="sample_volume"]').value);
            const finalVolume = number(row.querySelector('[name="final_volume"]').value);
            const dilution = number(row.querySelector('[name="dilution_factor"]').value);
            const signal = number(row.dataset.signal);
            const valid = [volume, finalVolume, dilution].every(v => Number.isFinite(v) && v > 0);
            const measured = valid ? (signal - config.intercept) / config.slope : NaN;
            const result = measured * (config.direct || !config.applyVolume ? 1 : finalVolume / volume)
                * (config.direct ? 1 : dilution * config.prep);
            row.querySelector(".icpd-measured").textContent = Number.isFinite(measured) ? measured.toFixed(config.digits) : "—";
            row.querySelector(".icpd-concentration").textContent = Number.isFinite(result) ? result.toFixed(config.digits) : "—";
            let remark = "";
            if (row.dataset.excluded === "1") remark = "已排除";
            else if (!window.AnalysisInterpretation) remark = "判定模組未載入";
            else if (!Number.isFinite(number(config.mdl))) remark = "未設定 MDL";
            else {
                remark = window.AnalysisInterpretation.evaluateResult({
                    role: row.dataset.role, concentration: result * config.concentrationFactor,
                    mdl: number(config.mdl), qdl: number(config.qdl),
                    blankMdlMultiplier: number(config.blankMdlMultiplier),
                    blankRoles: ["ICBK", "BK", "CCBK"], sampleRoles: ["SAMPLE", "DUP"]
                });
            }
            row.querySelector(".icpd-interpretation").textContent = remark;
        }
        function markQaqcDirty() {
            const result = document.getElementById("icpqc-results");
            const warning = document.getElementById("icpqc-dirty");
            const note = document.getElementById("icpqc-saved-note");
            if (result) result.hidden = true;
            if (warning) warning.hidden = false;
            if (note) note.hidden = true;
        }
        rows.forEach(function (row) {
            row.addEventListener("input", function () { markQaqcDirty(); recalculate(row); });
            row.querySelector(".icpd-row-delete").addEventListener("click", function () {
                if (row.dataset.excluded !== "1" && Number(row.dataset.linkedCount) > 0) {
                    alert("此原樣連結 DUP／MS／MSD，不可直接排除，請先確認品管關聯。");
                    return;
                }
                markQaqcDirty();
                row.dataset.excluded = row.dataset.excluded === "1" ? "0" : "1";
                row.classList.toggle("icpd-row-excluded", row.dataset.excluded === "1");
                this.textContent = row.dataset.excluded === "1" ? "恢復" : "刪除";
                recalculate(row);
            });
            recalculate(row);
        });
        form.addEventListener("submit", async function (event) {
            event.preventDefault();
            const button = form.querySelector('button[type="submit"]');
            if (button.disabled) return;
            button.disabled = true;
            const payload = rows.map(function (row) {
                return {row_id:row.dataset.rowId,
                    sample_volume:row.querySelector('[name="sample_volume"]').value,
                    final_volume:row.querySelector('[name="final_volume"]').value,
                    dilution_factor:row.querySelector('[name="dilution_factor"]').value,
                    is_excluded:row.dataset.excluded === "1"};
            });
            const data = new FormData(form);
            data.set("rows_json", JSON.stringify(payload));
            try {
                const response = await fetch(form.action, {method:"POST", body:data, credentials:"same-origin"});
                const result = await response.json();
                if (!response.ok) { alert(result.message || "分析資料無法暫存。"); return; }
                window.location.assign(window.location.href);
            } catch (error) { alert("無法確認暫存結果，請重新載入頁面確認。"); }
            finally { button.disabled = false; }
        });
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
    else start();
})();
