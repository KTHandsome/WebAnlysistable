(function () {
    "use strict";
    const form = document.getElementById("icp-frozen-export");
    if (!form) return;
    const message = document.getElementById("icp-frozen-message");
    document.getElementById("icp-frozen-all").onclick = () => form.querySelectorAll('[name="channels"]').forEach(c => { c.checked = true; });
    document.getElementById("icp-frozen-none").onclick = () => form.querySelectorAll('[name="channels"]').forEach(c => { c.checked = false; });
    let busy = false;
    form.addEventListener("submit", async event => {
        event.preventDefault(); if (busy) return;
        if (!form.querySelector('[name="channels"]:checked')) { message.textContent = "請至少選擇一個金屬／波長。"; return; }
        const button = form.querySelector('[type="submit"]'); busy = true; button.disabled = true;
        message.textContent = "正在產生檔案…";
        try {
            const response = await fetch(form.action, {method: "POST", body: new FormData(form), credentials: "same-origin"});
            const pdf = form.dataset.kind === "pdf";
            const mime = pdf ? "application/pdf" : "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
            if (!response.ok || !(response.headers.get("Content-Type") || "").includes(mime)) {
                const data = await response.json().catch(() => ({})); throw new Error(data.message || "匯出失敗，請確認登入狀態。");
            }
            const url = URL.createObjectURL(await response.blob());
            const a = document.createElement("a"); a.href = url; a.download = pdf ? "ICP_Record.pdf" : "ICP_LIMS_Import.xlsx";
            document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
            message.textContent = "檔案已產生。";
        } catch (error) { message.textContent = error.message; }
        finally { busy = false; button.disabled = false; }
    });
})();
