(function () {
    "use strict";
    document.querySelectorAll(".icp-delete-work-form").forEach(form => {
        let busy = false;
        form.addEventListener("submit", async event => {
            event.preventDefault();
            if (busy || !confirm("確定刪除暫存工作「" + form.dataset.filename + "」？\n此工作中的匯入資料與暫存修改將一併刪除。")) return;
            busy = true;
            const button = form.querySelector('[type="submit"]'); button.disabled = true;
            try {
                const response = await fetch(form.action, {method: "POST", body: new FormData(form), credentials: "same-origin"});
                const data = await response.json().catch(() => ({}));
                if (!response.ok || !data.redirect_url) throw new Error(data.message || "無法確認刪除結果，請重新整理清單確認。");
                window.location.assign(data.redirect_url);
            } catch (error) { alert(error.message); }
            finally { busy = false; button.disabled = false; }
        });
    });
})();
