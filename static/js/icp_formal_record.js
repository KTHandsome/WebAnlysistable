(function () {
    "use strict";
    const form = document.getElementById("icp-formal-form");
    if (!form) return;
    function inputs() {
        return JSON.stringify(["icp-pfm-form", "icp-samples-form"].map(id => {
            const target = document.getElementById(id);
            return target ? [Array.from(new FormData(target).entries()),
                Array.from(target.querySelectorAll(".icpd-sample-row")).map(row => row.dataset.excluded)] : [];
        }));
    }
    const original = inputs();
    let busy = false;
    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        if (busy) return;
        if (original !== inputs()) {
            alert("本頁有尚未暫存的修改，請先暫存分析資料或儲存 PFM，再儲存正式紀錄。");
            return;
        }
        const button = form.querySelector('[type="submit"]');
        busy = true; button.disabled = true;
        try {
            const response = await fetch(form.action, {method: "POST", body: new FormData(form), credentials: "same-origin"});
            const data = await response.json().catch(() => ({}));
            if (!response.ok || !data.redirect_url) throw new Error(data.message || "無法確認儲存結果，請重新載入後確認。");
            alert(data.message);
            window.location.assign(data.redirect_url);
        } catch (error) {
            alert(error.message || "無法確認儲存結果，請重新載入後確認。");
        } finally { busy = false; button.disabled = false; }
    });
})();
