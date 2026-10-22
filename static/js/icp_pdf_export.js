(function () {
    "use strict";
    const dialog = document.getElementById("icp-pdf-dialog");
    const form = document.getElementById("icp-pdf-form");
    const open = document.getElementById("icp-pdf-open");
    if (!dialog || !form || !open) return;
    const message = document.getElementById("icp-pdf-message");
    function currentInputs() {
        return JSON.stringify(["icp-pfm-form", "icp-samples-form"].map(id => {
            const target = document.getElementById(id);
            return target ? [Array.from(new FormData(target).entries()),
                Array.from(target.querySelectorAll(".icpd-sample-row")).map(row => row.dataset.excluded)] : [];
        }));
    }
    const original = currentInputs();
    function saved() {
        if (original === currentInputs()) return true;
        alert("本頁有尚未暫存的修改，請先暫存分析資料或儲存 PFM，再匯出 PDF。");
        return false;
    }
    open.addEventListener("click", function () {
        if (saved()) { message.textContent = ""; dialog.showModal(); }
    });
    document.getElementById("icp-pdf-close").addEventListener("click", () => dialog.close());
    document.getElementById("icp-pdf-all").addEventListener("click", () => form.querySelectorAll('[name="channels"]').forEach(item => { item.checked = true; }));
    document.getElementById("icp-pdf-none").addEventListener("click", () => form.querySelectorAll('[name="channels"]').forEach(item => { item.checked = false; }));
    let busy = false;
    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        if (busy || !saved()) return;
        if (!form.querySelector('[name="channels"]:checked')) {
            message.textContent = "請至少選擇一個金屬／波長。";
            return;
        }
        const button = form.querySelector('[type="submit"]');
        busy = true; button.disabled = true; message.textContent = "正在產生 PDF…";
        try {
            const response = await fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin" });
            if (!response.ok || !(response.headers.get("Content-Type") || "").includes("application/pdf")) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.message || "PDF 無法產生，請確認登入狀態或重新載入頁面。");
            }
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url; link.download = "ICP_Analysis_Record.pdf";
            document.body.appendChild(link); link.click(); link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 30000);
            message.textContent = "PDF 已產生。";
            dialog.close();
        } catch (error) {
            message.textContent = error.message || "PDF 匯出失敗。";
        } finally {
            busy = false; button.disabled = false;
        }
    });
})();
