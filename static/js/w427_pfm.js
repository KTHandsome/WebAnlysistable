/* PFM save preserves the current preview and uses the real form action attribute. */
(function () {
    "use strict";
    const form = document.getElementById("w427-pfm-save");
    if (!form) return;
    const button = form.querySelector('button[type="submit"]');
    const message = document.getElementById("w427-pfm-save-message");
    let busy = false;
    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        if (busy || button.disabled) return;
        busy = true;
        button.disabled = true;
        message.textContent = "儲存中…";
        try {
            const response = await fetch(form.getAttribute("action"), {
                method: "POST", body: new FormData(form), credentials: "same-origin",
                headers: {"Accept": "application/json"}
            });
            if (!(response.headers.get("content-type") || "").includes("application/json")) {
                throw new Error("登入可能已失效或未取得儲存結果，請確認登入後重試；相同紀錄不重複新增。");
            }
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || "PFM 儲存失敗。");
            message.textContent = data.message;
            message.style.color = "#15803d";
        } catch (error) {
            message.textContent = error.message || "未取得儲存結果，請重試；相同紀錄不重複新增。";
            message.style.color = "#b42318";
        } finally {
            busy = false;
            button.disabled = false;
        }
    });
})();
