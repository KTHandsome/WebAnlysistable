(function () {
    "use strict";
    const form = document.getElementById("sample-qaqc-form");
    const node = document.getElementById("w427-edit-config");
    const pdfButton = document.getElementById("w427-pdf-export");
    const excelButton = document.getElementById("w427-excel-export");
    async function downloadFile(url, options, kind = "pdf") {
        const button = kind === "excel" ? excelButton : pdfButton;
        const label = kind === "excel" ? "LIMS Excel" : "檢驗紀錄表";
        const mime = kind === "excel" ? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" : "application/pdf";
        const filename = kind === "excel" ? "W427_LIMS_Import.xlsx" : "W427_Analysis_Record.pdf";
        const status = document.getElementById("w427-edit-message");
        if (button) button.disabled = true;
        try {
            const response = await fetch(url, options);
            if (!response.ok || !(response.headers.get("Content-Type") || "").includes(mime)) {
                let error = "無法匯出"+label+"，請確認 QA/QC 與批次備註。";
                if ((response.headers.get("Content-Type") || "").includes("application/json")) error = (await response.json()).message || error;
                else if (response.redirected) error = "登入已失效，請重新登入後開啟工作。";
                else {const text=await response.text();if (text && !text.includes("<"))error=text;}
                throw new Error(error);
            }
            const blob=await response.blob(), uri=URL.createObjectURL(blob), link=document.createElement("a");
            link.href=uri;link.download=filename;document.body.appendChild(link);link.click();link.remove();
            window.setTimeout(()=>URL.revokeObjectURL(uri),60000);
            if (status) status.textContent=label+"已匯出；匯出不會變更暫存或送審狀態。";
        } catch(error) {if(status)status.textContent=error.message || "匯出失敗，請重新載入後重試。";}
        finally {if(button)button.disabled=false;}
    }
    if (pdfButton && pdfButton.dataset.exportUrl) pdfButton.addEventListener("click",()=>downloadFile(pdfButton.dataset.exportUrl));
    if (excelButton && excelButton.dataset.exportUrl) excelButton.addEventListener("click",()=>downloadFile(excelButton.dataset.exportUrl, undefined, "excel"));
    if (!form || !node) return;
    const data = JSON.parse(node.textContent), config = data.config;
    const body = form.querySelector("tbody"), message = document.getElementById("w427-edit-message");
    const rows = () => Array.from(body.querySelectorAll(".sample-qaqc-row"));
    const visible = () => rows().filter(row => !row.classList.contains("is-excluded-row"));
    const id = row => Number(row.querySelector('input[name^="source_sequence_"]').value);
    const role = row => row.querySelector('input[name^="role_"]').value;
    const group = row => row.dataset.w430Group;
    const parents = config.parents;
    const canEdit = row => ["SAMPLE", "DUP", "MS", "MSD"].includes(role(row));
    function dirty() { message.textContent = "修改尚未確認，請按「更新樣品及 QA/QC」重新計算；分析資料尚未暫存。"; }
    function blocks() {
        const output = [];
        visible().forEach(row => {
            if (["DUP", "MS", "MSD"].includes(role(row)) && output.length &&
                id(output[output.length-1][0]) === parents[String(id(row))]) output[output.length-1].push(row);
            else output.push([row]);
        });
        return output;
    }
    function order() {
        const list = visible(), chunks = blocks();
        list.forEach((row, index) => {
            row.querySelector(".display-order-text").textContent = index + 1;
            row.querySelector(".display-order-input").value = index + 1;
            const pos = chunks.findIndex(chunk => chunk[0] === row);
            for (const [selector, offset] of [[".move-row-up",-1],[".move-row-down",1]]) {
                const other = chunks[pos + offset];
                row.querySelector(selector).disabled = role(row) !== "SAMPLE" || pos < 0 || !other ||
                    role(other[0]) !== "SAMPLE" || group(other[0]) !== group(row);
            }
        });
    }
    rows().forEach(row => {
        row.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"])').forEach(input => {
            input.readOnly = !(input.classList.contains("dilution-factor-input") && canEdit(row));
        });
        row.querySelector(".dilution-factor-input").min = "0";
    });
    // Exact server-produced bases avoid using rounded visible concentrations.
    const bases = config.bases || {};
    function live(row) {
        const input = row.querySelector(".dilution-factor-input"), d = Number(input.value);
        const base = bases[String(id(row))];
        const valid = input.value.trim() !== "" && Number.isFinite(d) && d > 0 && base && Number.isFinite(base.concentration);
        const concentration = valid ? base.concentration * d : NaN;
        row.querySelector(".calculated-concentration-cell").textContent = Number.isFinite(concentration) ? concentration.toFixed(config.decimals) : "—";
        const result = row.querySelector(".interpretation-cell");
        if (!Number.isFinite(concentration)) result.textContent = "待重新計算";
        else if (config.mdl === null || !window.AnalysisInterpretation) result.textContent = "";
        else result.textContent = window.AnalysisInterpretation.evaluateResult({role:role(row), concentration,
            mdl:config.mdl*d, qdl:base.qdl*d, blankMdlMultiplier:config.blankMultiplier,
            blankRoles:["BK"],sampleRoles:["SAMPLE","DUP"]});
        const spike = row.querySelector('input[name^="spike_concentration_"]');
        if (spike && base && base.spike !== null) spike.value = valid ? String(base.spike*d) : "";
    }
    form.addEventListener("input", event => {
        if (event.target.classList.contains("dilution-factor-input")) {dirty();live(event.target.closest(".sample-qaqc-row"));}
    });
    form.addEventListener("change", event => {
        if (!event.target.classList.contains("sample-delete-checkbox") || !event.target.checked) return;
        if (!window.confirm("確定刪除此列？原樣品的 DUP／MS／MSD 會一併移除；原始匯入資料仍保留。")) {event.target.checked=false;return;}
        const row = event.target.closest(".sample-qaqc-row"), removed = id(row);
        rows().forEach(item => {if (item === row || parents[String(id(item))] === removed) {
            item.classList.add("is-excluded-row");item.hidden = true;
            item.querySelectorAll("input").forEach(input=>input.disabled=true);
        }});
        order();dirty();
    });
    form.addEventListener("click", event => {
        const button = event.target.closest(".move-row-up,.move-row-down");
        if (!button || button.disabled) return;
        const row=button.closest(".sample-qaqc-row"), chunks=blocks(), index=chunks.findIndex(chunk=>chunk[0]===row);
        const offset=button.classList.contains("move-row-up")?-1:1, other=chunks[index+offset];
        if (!other || role(row)!=="SAMPLE" || role(other[0])!=="SAMPLE" || group(row)!==group(other[0])) return;
        if (offset < 0) chunks[index].forEach(item=>body.insertBefore(item,other[0]));
        else other.forEach(item=>body.insertBefore(item,row));
        order();dirty();
    });
    function hidden(name,value) {const n=document.createElement("input");n.type="hidden";n.name=name;n.value=value;form.appendChild(n);return n;}
    const actionInput = hidden("action","recalculate_samples");
    for (const key of ["csrf_token","preview_token","exam_no","instrument_id"]) hidden(key,data[key]);
    const edits=hidden("edits","");
    const remarks=hidden("batch_remarks", "{}");
    const remarkForm=document.getElementById("batch-remark-form");
    if (remarkForm) remarkForm.addEventListener("submit", event=>{event.preventDefault();form.requestSubmit();});
    form.addEventListener("submit", event=>{
        const clicked = event.submitter && event.submitter.id;
        actionInput.value = clicked === "w427-excel-export" ? "export_excel" : clicked === "w427-pdf-export" ? "export_pdf" : clicked === "w427-record-save" ? "submit_record" : clicked === "w427-draft-save" ? "save_draft" : "recalculate_samples";
        const values={};
        document.querySelectorAll('#w427-qaqc input[name^="batch_remark_"]').forEach(input=>{
            values[input.name.slice("batch_remark_".length)] = input.value;
        });
        remarks.value=JSON.stringify(values);
        if (actionInput.value === "submit_record" && !window.confirm("確定儲存分析紀錄並送審？成功後本工作將移出暫存清單，暫存與儲存按鈕會停用。")) {
            event.preventDefault();return;
        }
        if (visible().some(row=>{const input=row.querySelector(".dilution-factor-input");return input.value.trim()==="" || !Number.isFinite(Number(input.value)) || Number(input.value)<=0;})) {
            event.preventDefault();message.textContent="稀釋倍數必須為有效正數。";return;
        }
        edits.value=JSON.stringify(rows().map(row=>({id:id(row),dilution:row.querySelector(".dilution-factor-input").value,
            excluded:row.classList.contains("is-excluded-row") && ["SAMPLE","QC"].includes(role(row))})));
        if (["export_pdf","export_excel"].includes(actionInput.value)) {
            event.preventDefault();
            downloadFile(form.getAttribute("action"),{method:"POST",body:new FormData(form)},actionInput.value === "export_excel" ? "excel" : "pdf");
        }
    });
    function header() {
        const top=document.querySelector(".page-header");
        document.documentElement.style.setProperty("--w427-header-height",(top?top.getBoundingClientRect().height:0)+"px");
    }
    window.addEventListener("resize",header);
    if (window.ResizeObserver) {const top=document.querySelector(".page-header");if(top)new ResizeObserver(header).observe(top);}
    order();header();
})();
