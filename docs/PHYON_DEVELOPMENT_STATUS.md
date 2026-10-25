# Phyon 開發進度與跨聊天室交接紀錄

> 文件版本：V1.2｜更新日期：2026-10-20
> 目的：保留已驗證功能、目前開發主線、暫停工作、關鍵設計決策及接續位置。  
> 注意：本文件依目前對話整理；未實際執行的測試、尚未確認的 Commit 與正式儲存功能，不得標示為完成。

## 0. 最新進度與接續位置（2026-10-20）

本節為目前交接依據；後續第 2～7 節保留 2026-10-16 的歷史紀錄。舊紀錄中的優先主線、未提交狀態及待辦，若與本節衝突，以本節已確認事項為準；未重新驗證的舊問題仍保留，不推定已解決。

### 0.1 名稱與合作約定

- 儀器性能查核統一使用 **PFM**；既有 `prm_*`、類別及工具檔名保留，不全面更名。
- 每完成一個 Stage 或一組完整修改並驗收後，更新本文件：記錄修改檔案、行為變更、驗收結果、Git 狀態與下一步。
- 部分完成可記錄，但必須明列未驗收內容，不得將語法檢查當成執行或交易一致性驗收。
- 一次處理一個明確目標；先核對現有檔案及定位，再修改；優先瀏覽器實際驗收。

### 0.2 四個檢項與 PE900 PFM 驗收

已完成分析功能及 PFM 整合：

| 方法 | 測項 | 儀器 |
|---|---|---|
| W532 | TOC | OI 1030W |
| W434 | As | PE900 |
| W341 | Se | PE900 |
| W330 | Hg | RA7000 |

W434、W341 已通過 PDF 解析、PFM 判定、檢量線、分析紀錄儲存與性能查核歷程查詢的實際操作驗收。

- PE900 Sample ID `PFM` 獨立分流，不參與 STD0～STD5 檢量線。
- As PFM：0.1490；實際測定時間：2026-10-15 14:32:37。
- Se PFM：0.2194；實際測定時間：2026-10-15 13:23:13。
- 管制版本依基本資料的儀器編號及 `analysis_start_date` 查詢。
- 性能事件識別採 PDF 實際測定日期時間。
- 管制上下限讀取資料庫正式發布的 ACTIVE Performance 設定，不直接讀取開發 CSV。開發資料庫為 SQLite，Server 為 Firebird。

已確認 Commit：

- `aa26c07` — Fix PFM release history guard for existing ACTIVE batch
- `cc52951` — Integrate PE900 As Se PFM control and measurement history

### 0.3 Server 程式與 Firebird 驗收

- 開發目錄：`D:\PhyonWeb`；Server：`E:\PhyonWeb`。
- GitHub：`KTHandsome/WebAnlysistable`。
- Server 已同步至 `cc52951`（當時 HEAD/main、origin/main、origin/HEAD 相同）。
- Server 目前仍為測試環境，尚未正式啟用；「發布環境」為程式依 Firebird 模式顯示的標籤，不代表已正式上線。
- `run_server.py` 為未追蹤的 Server 本機檔案，必須保留，不得刪除或覆蓋。
- `database.py` 讀取 `PHYON_DB_TYPE`，未設定時預設 SQLite；Server 啟動明確設定為 `firebird`。
- Phyon Firebird 目標：主機 `192.168.0.5`、主機端路徑 `E:/PhyonDatabase/PHYON.FDB`；不得與 LIMS 連線混為一談。
- `instance/phyon.db` 雖存在且為 0 bytes，不是本次 Server 使用的分析資料庫。
- 發現 Port 80 舊程序自 2026-10-12 啟動，pull 後未重啟；停止舊程序後，以 Server 虛擬環境啟動更新程式，網頁已顯示「發布環境」及性能查核匯入功能。
- 查詢曾出現 Firebird -204：`PERFORMANCE_ANALYSIS_LINK` 不存在。唯讀結構檢查確認既有 `analysis_record` 存在，但四張 PFM 表均缺少。
- 已依現有模型，限縮指定四張表執行 `create_all(..., tables=..., checkfirst=True)`，回報 `PFM tables created successfully.`：
  - `performance_import_history`
  - `instrument_performance_control`
  - `performance_measurement_history`
  - `performance_analysis_link`
- 未複製開發 SQLite 至 Server，未執行全庫重建。
- 2026-10-20 使用者回報：Server Web 各項功能均可正常操作。本次操作驗收通過；不推定已完成多人並行、備份還原或所有資料完整性專項驗證。
- 當時服務以 PowerShell 前景執行；後續是否已改為常駐服務尚未確認。
- 部署原則：Git pull 只同步程式碼；執行中的服務須重啟，資料庫結構更新須獨立處理。

### 0.4 Stage 35B～35F：既有基礎

依使用者提供的階段交接，已完成：

| 階段 | 完成內容 |
|---|---|
| 35B | Work Identity、工作所有權隔離 |
| 35C | SQLite Draft Repository、送審與退回恢復 |
| 35D | 快照一致性與交易 Rollback |
| 35E | 提交成功後的 Rollback |
| 35F | 五組 JSON 共用 Revision、完整讀寫及一致性驗證 |

上述為 Repository 層基礎，不代表正式路由已具備多使用者隔離；正式儲存仍需逐步脫離 Flask Session 與 `W434_CURRENT` 資料來源。

### 0.5 Stage 35G：進行中，尚未完成

目標：指定 `work_id`，驗證登入者與分析方法，讀取同一 Revision 的五組 JSON（分析、基本資料、管制、方法、報告設定），保留原有計算及 QA/QC 規則，在同一交易更新正式分析紀錄、工作快照與 Draft；PFM 事件及關聯亦須包含於相同交易。舊紀錄沒有 Draft 時，維持退回修正相容性。

**已完成的檢查與局部修改：**

- 檢查最新版 `services/analysis_record_service.py`：原服務自行建立 Session，並負責 Commit／Rollback／Close；PFM 同步透過同一 `db` 在 Commit 前執行。
- 已由使用者修改 `save_analysis_record(..., current_user, db=None)`，支援外部傳入 Session。
- `owns_session = db is None`；僅自行建立 Session 時負責 Commit／Refresh、Rollback 與 Close。
- 外部傳入 Session 時只 Flush，交易由外層統一管理；PFM 同步位置保留。
- 使用者回報 `py_compile` 語法檢查通過。

**驗收與限制：**

- 修改後檔案尚未重新讀取核對；目前依使用者修改及語法檢查回報記錄。
- 既有呼叫流程已以 W532（TOC）完成瀏覽器操作驗收：正式紀錄儲存成功，查詢頁顯示「待審核」，對應 PFM 歷程正常顯示。其他方法尚未逐項回歸。
- 驗收初次遇到 `local variable 'db' referenced before assignment`；經使用者修正後重新儲存成功。修改後完整檔案仍待核對，不推定具體漏改位置。
- 介面實際用詞為「待審核」，不得因先前口述「送審中」而修改既有狀態規則。
- 外部 Session 共同交易已以 W532 實際快照、記憶體 SQLite 驗證通過（詳見 0.7）；尚未完成網頁路由整合及 Firebird 共同交易驗收。
- Draft Repository 及正式路由尚未接入，不得宣稱 Stage 35G 或多人隔離已完成。
- 本次局部修改尚未確認 Git Commit／Push，亦未部署 Server。
- 本步無資料庫結構變更，不執行 Migration。

**下次接續：**規劃並接入網頁的工作建立／保存／讀取與送審流程，使 work_id、Revision 及五組 JSON 真正由 Draft 提供。共同交易服務已通過 W532 記憶體 SQLite 整合驗證；現有網頁仍未使用該服務。修改路由前須重新核對最新檔案，不能沿用舊行號。

### 0.6 後續主線排序

1. Stage 35G：工作資料一致性、多使用者隔離及正式路由整合。
2. ICP5800：完整分析流程、多波長與正式檢驗紀錄串接，尚未完成。
3. PFM V2 發布簡化：保留 Excel／CSV 編輯匯入，後續改善為一鍵發布。

### 0.7 Stage 35G 共同送審服務子步驟（2026-10-20）

新增檔案：`services/analysis_work_submission_service.py`。

- 新增 `submit_analysis_work(db, work_id, method_code, expected_revision, current_user)`。
- 使用外部 Session；服務不 Commit／Rollback／Close，呼叫端必須成功時提交、例外時回復。
- 驗證登入者、方法、Draft 所有權、EDITING 狀態及預期 Revision。
- 從 Draft 讀取五組 JSON，不依賴 Flask Session 或全域分析狀態。
- 檢查表單方法、正式紀錄關聯、原分析人員與退回狀態。
- 呼叫既有 `validate_qaqc_export_ready()` 與 `save_analysis_record(..., db=db)`，保留原有驗證和儲存規則。
- 正式儲存後呼叫 `submit_draft()`，核對五組快照並以 Revision 條件更新。
- `app.py` 尚未改接；此子步驟不代表多使用者網頁流程已完成。

使用者執行整合驗證：只讀開發資料庫最新 W532 正式快照，將快照內容複製至獨立記憶體 SQLite，實際呼叫正式儲存服務。開發及 Server 資料庫未新增測試資料。

| 驗證項目 | 結果 |
|---|---|
| 新服務建立及語法檢查 | PASS |
| 正式儲存後模擬 Draft 提交例外，外層 Rollback 清除主檔、快照、PFM 並還原 Draft | PASS |
| 正式儲存與 Draft 提交成功後，外層 Rollback 仍完整回復 | PASS |
| 外層 Commit 保留正式紀錄、快照與 SUBMITTED Draft 關聯 | PASS |
| 正式狀態 UNDER_REVIEW（介面：待審核） | PASS |
| PFM Event／Link | 各 1 筆 |

測試輸出：`PASS: Stage 35G shared transaction integration.`

驗證範圍限 W532、記憶體 SQLite、單一工作。跨使用者、過期 Revision、重複送審、退回重送及真正並行的服務整合案例尚未在本次驗證涵蓋；Repository 既有案例不能替代完整網頁驗收。Firebird 共同交易與部署未進行。新服務與本次修改尚未確認 Commit／Push。

### 0.8 Stage 35G 網頁測試包與舊紀錄相容性（2026-10-20）

- 已確認 Commit：`c8db435 — Add shared transaction service for analysis work submission`，共 3 檔（正式儲存服務、共同送審服務、進度 MD）；Push 尚未確認。
- Commit 前已核對服務 Diff；中文字串以 `ascii()` 檢查確認正確，先前 Diff 顯示問號屬顯示／複製編碼問題。修復字串的保護指令停止，沒有修改檔案。
- 已提供並由使用者套用 W434 網頁測試包，共 9 個程式／模板檔。備份：`D:\PhyonWeb\backups\stage35g_web_20261020_102439_415089`。
- 新增 `analysis/analysis_work_web.py`；僅明確設定 `PHYON_ENABLE_STAGE35G_WEB=1` 才建立 W434（As）新 Draft，預設關閉。W532／W341／W330 仍沿用既有流程。
- 工作隔離從 Draft 建立後開始；基本資料頁多分頁隔離仍未完成。
- 網頁測試包的 11 項隔離測試使用 Flask harness、實際 Repository／models 與部分測試替身；非完整 Phyon 瀏覽器端到端驗收。
- 開發端實際 SQLite 尚缺 `analysis_work_draft`。此時驗收舊紀錄退回修正，新增 managed-draft 檢查直接查表而出現 `no such table`。
- 已提供程式修正：以 `inspect(db.connection()).has_table(AnalysisWorkDraft.__tablename__)` 確認表存在才查詢；不為修復舊流程而先建表。表存在／不存在兩種 guard 情境檢查通過。
- 缺表錯誤排除後，使用者遇到既有的「目前已有其他分析工作」衝突提示，並確認有 ICP 暫存。既有程式只要 Session 存在 `icp_work_key` 就阻擋；本次未移除檢查或刪除 ICP 暫存。
- 使用者要求衝突時留在原頁，以訊息視窗提示；已修改 `templates/analysis_record_detail.html` 的進入修正表單，使用 fetch 提交，失敗時 alert，成功重新導向。模板與 JavaScript 語法檢查通過；後續截圖已確認衝突彈窗留在原明細頁，操作驗收通過。
- 使用者回報：登出後再次操作可正常進入分析數據頁，修正並再次儲存後進入「待審核」。**舊紀錄退回進入與重新送審操作驗收通過**。登出後成功支持 Session 狀態涉及阻擋，不能據此推定 ICP 暫存已刪除或所有衝突來源均已排除。
- 本次未確認新建 Draft 流程已啟用或驗收；不可標示 W434 網頁隔離或 Stage 35G 完成。後續須先明確準備開發 Draft 資料表，再啟用新流程驗收。
- 新 Draft 的退回修正與原分析員／審核者權限銜接仍未完成，關聯新 Draft 的紀錄暫阻擋舊 resume，避免回退全域狀態。沒有 Draft 的舊紀錄維持原權限及既有流程。
- 網頁測試包、缺表相容性修正及明細頁提示調整，均尚未確認 Commit／Push；不得部署 Server 或標示全部回歸通過。

### 0.9 舊紀錄工作切換與退回重送回歸完成（2026-10-20）

- 發現已正式儲存的 W434 As 工作，仍被舊 `has_resume_work_conflict()` 當成未完成工作，阻擋 W532 TOC 進入修正。
- 修改 `routes/analysis_record_routes.py` 的衝突判定：核對目前狀態／基本資料與正式快照、正式關聯、登入者及方法；確認已儲存且一致時，允許切換至退回紀錄。未儲存差異、關聯不明或權限不符仍阻擋；保留 `icp_work_key` 的 ICP 暫存保護。
- 修正指令執行及語法檢查通過；備份：`backups/analysis_record_routes_before_saved_work_fix_20261020_105747_150486.py`。
- 隔離測試 11 項通過，涵蓋已儲存工作切換、未儲存差異、ICP 暫存保護與所有權；未改動 ICP 暫存或正式資料。
- 使用者瀏覽器驗收：TOC 可進入修正，再儲存後回到「待審核」。2026-10-20 11:06 截圖確認 ID 1 TOC／W532 與 ID 2 砷／W434 兩筆正式紀錄均存在且皆為「待審核」。
- 衝突提示以訊息視窗顯示並留在原明細頁，已由前次截圖確認。
- 一次性 `fix_resume_saved_work.py` 與 `stage35g_patch` 資料夾已由使用者刪除；執行所需模組與備份保留。
- 本節完成的是舊紀錄相容性回歸，不代表 Stage 35G 全部完成。新 Draft 建立仍預設關閉，實際開發 Draft 表準備、新工作隔離及新 Draft 退回權限銜接尚待處理。
- 本次網頁及相容性修正尚未確認 Commit／Push；Server 未部署。

下一步：先核對開發端 Draft 資料表與啟用條件，再準備 W434 新工作流程驗收；ICP 開發主線仍暫停，保留既有 ICP 暫存。


### 0.10 W434 新 Draft 送審與防覆寫操作驗收（2026-10-20 14:17）

本節更新並優先於 0.8／0.9 的當時待驗收狀態；Stage 35G 整體仍進行中。

- 開發端確認使用 SQLite，原無 `analysis_work_draft`；依現有模型的限定建表指令執行，使用者回報建表成功。該指令先以 SQLite backup API 備份並檢查備份完整性，再只建立此表；實際備份路徑輸出未貼回，不補記虛構路徑。
- 開發 PowerShell 設定 `PHYON_ENABLE_STAGE35G_WEB=1` 後重啟，W434 新工作網址帶 UUID。PDF 匯入、PFM 0.149 合格、暫存與 F5 讀回正常。
- 首次工作 `21569f7d-888e-4c17-b469-ea1f6d1a20ea` 正式儲存後，唯讀查詢確認 Draft SUBMITTED／Revision 5，關聯正式 ID 3／UNDER_REVIEW。
- 新增模板修改 `templates/methods/w43401.html`：將工作控制腳本移出 title 區塊；送審後停用表單與外部 form 按鈕；工作表單以 fetch 操作，錯誤 alert 留在原頁；波長確認成功改為 GET saved=1，避免 reload 重送上一個匯入 POST 造成 Revision Conflict。模板與 JavaScript 語法檢查通過；使用者後續儲存後按鈕停用。
- 發現第二工作 `8027bf1b-ad60-4846-8e96-99a89bfc894b` 亦為 SUBMITTED／Revision 4，卻關聯同一正式 ID 3。核對服務確認：既有 Analysis Identity 搜尋允許更新 UNDER_REVIEW，因此不同 Draft 可沿用已送審紀錄。不能將此結果當作防重複成功；是否改變數值未查證。
- 修正 `services/analysis_record_service.py`：新增 `strict_work_identity=False`，預設保留舊呼叫行為。嚴格模式下，新工作遇到相同 Identity 的既有正式紀錄，在資料更新前拒絕；明確綁定的紀錄必須存在且 Identity 一致、屬於原分析員且 REJECTED 才能重送。
- 修改 `services/analysis_work_submission_service.py`：呼叫正式服務明確傳入 `strict_work_identity=True`。同一 Session 與外層交易管理方式保留。
- Python 3.8 語法檢查、實際紀錄選取／guard 區段的 12 個獨立 SQLite 案例通過。此測試非完整服務或並行驗收，未宣稱資料庫唯一性／跨交易競爭已全部解決。
- 使用者 14:17 操作驗收：重複正式紀錄被拒絕後，F5 仍保留分析資料且工作可繼續編輯；使用者自行刪除所有測試資料後，重新匯入並儲存，暫存／正式儲存按鈕反白停用。上述兩條 UI 操作路徑通過。未對清除後資料庫重新查詢 ID、Revision 或 PFM 數量，不推定清除範圍及舊 Draft 關聯均已清理。
- 所有修正未對 Server 執行 Migration 或部署；新網頁與 guard 修正 Commit／Push 仍未確認。
- 訊息視窗決議：後續改共用自訂對話框時，開發環境可用「老闆說」彩蛋，發布環境用「Phyon 提示」。尚未實作；目前仍為瀏覽器原生 alert。

**下一步：**核對最新版退回路由與 Draft 恢復服務，完成新 Draft 的退回修正及重新送審整合，再驗證不同工作／使用者隔離與過期 Revision。既有新 Draft resume 阻擋尚未解除；不能直接套用舊紀錄恢復流程。ICP 主線仍暫停。完成子步驟後再更新本文件，Stage 35G 未標示完成。

### 0.11 新 Draft 退回修訂與重新送審整合驗收（2026-10-20 15:17）

**目前接續依據：本節優先於 0.8～0.10 當時的待辦描述。這輪功能驗收結束，先更新文件與核對 Git；Stage 35G 整體仍保留未完成項目。**

#### 權限決議與身分保留

- 使用者明確要求保留審核者代為修正的既有設計：原分析員或登入 Session 具 REVIEW_ANALYSIS 者，可恢復退回工作、修訂及重送。不能將新版權限縮減成僅原分析員。
- 已讀取最新版 auth_session.py，can_review_analysis() 經 has_permission() 判定 Session permissions。授權不接受前端傳入審核者旗標。
- 新版正式紀錄重送保留原 analyst_user_id／analyst_employee_id／analyst_name；RESUBMIT 記錄當次實際操作者。原 Draft owner 不移轉。
- 新增 analysis/analysis_work_access.py：後端核對 actor、審核權限、Draft owner、原正式紀錄及方法後，回傳明確的 repository owner_id。這是資源所有者識別，不偽造 current_user；實際操作者另存歷程。
- Repository、auth_session.py 及 models.py 均未因本次整合修改。

#### 整合修改

| 檔案 | 行為 |
|---|---|
| analysis/analysis_work_access.py | 新增後端工作授權與實際操作者歷程 helper |
| analysis/analysis_work_web.py | 授權審核者存取原工作；修訂限正式紀錄 REJECTED；寫入 EDIT_DRAFT 歷程，與 Draft 共同交易 |
| routes/analysis_record_routes.py | 唯一關聯 Draft 呼叫原 resume_draft()，恢復原 work_id、Revision +1，寫 RESUME_DRAFT 歷程；已 EDITING 可重開，不覆蓋修訂；多筆關聯拒絕自動恢復；舊紀錄保留原流程 |
| services/analysis_work_submission_service.py | 區分實際 actor 與 repository owner，授權後重送原正式紀錄 |
| services/analysis_record_service.py | 延續防覆寫及原分析員保護，允許後端授權審核者更新 REJECTED；RESUBMIT 寫實際 actor |

- 2026-10-20 15:10 安裝工具來源、依賴與語法檢查通過，使用者套用成功。備份：D:\PhyonWeb\backups\stage35g_resume_20261020_151042_507585。
- 未執行資料庫初始化、Migration、正式資料覆蓋或環境變數變更；未部署 Server。
- Python 3.8 語法及 17 項隔離檢查通過。使用實際 models／Repository／恢復路由／Web bridge／授權 helper／共同送審服務，並檢查實際正式服務 guard 與身分賦值區段；身分工具及完整正式計算儲存部分使用替身。不得當成完整 PDF/PFM、Firebird 或真正並行驗收。

#### 使用者瀏覽器操作驗收

測試帳號；本輪工作 ID：c705c07a-6446-4b6c-a4ae-cc868270bdd8。

| 項目 | 結果 |
|---|---|
| 退回後按進入修正，無原先「尚待完成驗收」阻擋 | 通過 |
| 進入原工作頁，資料保留，暫存／儲存可操作 | 通過 |
| 修改樣品稀釋倍數、暫存、F5 後值保留且 work_id 不變 | 通過 |
| 重新送審後原紀錄回到待審核，未多出紀錄 | 通過 |
| 返回工作頁後暫存／儲存按鈕停用 | 通過 |

連同 0.9／0.10 的匯入、暫存讀回、新紀錄送審、重複 Identity 防覆寫與失敗後可編輯，這輪功能操作驗收完成，不重複擴測。

#### 明確未驗收項目與下一步

- 使用者決議：暫不安排不同帳號區分原分析員／審核者的實際操作；程式已整合且有隔離檢查，不標示跨帳號瀏覽器驗收通過。
- 使用者尚未另貼實際 DB 的新 RESUME_DRAFT／EDIT_DRAFT／RESUBMIT 操作者及原分析員欄位查詢，不宣稱這些欄位已完成實際 DB 專項驗收。
- 跨工作／多分頁／多使用者隔離、過期 Revision、真正並行、基本資料頁隔離及 Firebird 專項保留後續；Stage 35G 整體不標示全部完成。
- 新 Draft 旗標已在開發端啟用測試；Server 狀態不可據此推定變更。ICP 開發主線仍暫停。
- 本輪收尾：更新本文件後，取得 git status --short 與 git diff --stat，核對本次修改、新模組及差異，再逐檔 git add／Commit。不可 git add .，不處理無關 PDF、CSV、instance、backups、run_server.py 或一次性安裝工具。
- 本輪網頁、相容性、防覆寫、操作者與退回整合尚未確認新 Commit／Push；最後已知共同交易服務 Commit 仍為 c8db435。收尾確認後再記錄實際 Commit，不預填。

### 0.12 工作隔離與過期版本瀏覽器驗收（2026-10-20 15:33）

本節為最新接續依據，更新前節當時的 Git 與待驗收狀態。

- 已確認 Commit：`83acc1d — Integrate W434 draft submission and reviewer-assisted revision`。共 14 檔，845 行新增、138 行刪除；新增 analysis_work_access.py、analysis_work_web.py。本次檔案已提交，使用者回報 Push 完成；Server 尚未部署。
- 提交前 git diff --cached --check 通過；提交後 git status 僅剩無關未追蹤檔案，未刪除或加入 PDF、CSV、instance、backups、run_server.py、一次性安裝工具及其他無關測試檔。
- 本輪同一測試帳號，以同一份 As PDF 建立不同工作；不需要第二份測試檔案。

| 工作 | work_id |
|---|---|
| A | 71c15641-f955-4f43-8c87-9da15cdce332 |
| B／B2（同工作、不同分頁） | 193976a0-f647-40d8-aebd-23df48f792af |

| 實際操作驗收 | 結果 |
|---|---|
| 新工作 B 空白，沒有帶入 A 的分析數據 | 通過 |
| B 匯入同一份 PDF、完成必要確認並暫存 | 使用者回報正常 |
| B 修改樣品稀釋倍數並暫存，A F5 後仍維持自己的原值 | 通過 |
| B2 開啟同一工作並修改暫存後，原 B 不刷新直接暫存 | 出現「此頁面已不是最新版本，請重新載入後再操作。」 |
| 原 B F5 後顯示 B2 最後暫存的值，而不是被拒絕的舊頁修改 | 通過，未覆蓋新資料 |

**本輪結論：**W434 同帳號不同工作之數據隔離、同工作不同分頁的過期 Revision 拒絕，以及拒絕後讀回最新暫存值，均已通過瀏覽器驗收。本輪未再正式送審 B／B2；不將此驗收延伸為所有方法、跨帳號或真正同時交易的全面驗證。

**保留範圍：**基本資料頁跨分頁隔離、不同登入者實測（依使用者決議暫不做）、Firebird 部署／交易專項及真正並行仍未完成。Stage 35G 不宣稱全範圍完成，但本輪 W434 功能與上述工作隔離／版本保護可結束重複測試。

**下一步：**將本節文件更新存回開發目錄並獨立提交文件紀錄；再核對 ICP5800 暫停位置，接回完整分析流程及正式檢驗紀錄串接。保留既有 ICP 暫存，不將本輪 W434 測試結果當成 ICP 已具備相同流程。此 MD 更新尚未包含於 83acc1d；文件後續 Commit／Push 待回報。

## 1. 專案環境與開發約定

- 專案：Phyon Web；本機工作目錄：`D:\PhyonWeb`。
- 後端：Python 3.8、Flask、SQLAlchemy；開發資料庫 SQLite：`instance\phyon.db`，另有 Firebird／LIMS 連線工作。
- 虛擬環境：`.venv\Scripts\python.exe`；版本控制：Git。
- 開發合作規則：每次只處理一個小步驟；先指出檔名與原有程式定位、修改範圍及既有功能風險，再提供 Code；測試 PASS 後才進入下一步。新增檔案先說明用途與放置位置。
- 切勿因換聊天室而重複修改已完成且測試通過的部分；修改前先確認目前 Git status／最新 Commit 及現存檔案內容。

## 2. PRM V2 儀器性能查核（核心功能已完成）

### 2.1 PRM V2 關鍵設計原則

2026-10-16 正式採用 PRM V2。

**儀器性能確校的管制標準不以 D／G／W 檢測類別區分，而是依儀器、管制項目及性能查核類型管理。**

主要配對條件：

- `instrument_id`：LIMS 儀器編號，例如 `A0087-02`。
- `monitor_item`：管制項目，例如 TOC、Hg、As、Se。
- `performance_type`：性能查核類型，例如 `CAL_HIGH_SIGNAL`。
- 年度、有效日期、啟用狀態及唯一 ACTIVE 發布批次。

保留 `category` 作為分析歷程的來源資訊，但不參與性能管制標準配對。

不新增 `PROFILE_CODE`，目前沿用既有管制識別方式。

同一儀器、同一日期允許多次合法性能查核；不能只以儀器及日期判定重複。

### 2.2 PRM V2 管制資料

正式管制 CSV 採既有 23 欄結構，本次 V2 共 6 筆設定。

主要內容：

- TOC：`A0087-02`，管制項目 `TOC`，性能類型 `CAL_HIGH_SIGNAL`。
- Hg：`A0085-02`，跨基質共用性能管制。
- As、Se：`A0018-06`，依不同測項及分析條件區分。
- ICP：`A0082-03`，包含 Pb/Cu 訊號比值及 CHECK_ELEMENT 性能查核設定。

其中未啟用的管制設定不得視為已正式投入使用。

TOC 已驗證管制值：

| 項目 | 數值 |
|---|---:|
| 參考值 | 204718 |
| 管制下限 | 190221 |
| 管制上限 | 219214 |
| PDF PERFORMANCE Area | 210635 |
| 判定 | PASS |

TOC 原始 Area 不扣除 Reagent Blank，也不可當作樣品濃度。

### 2.3 已完成與實際驗證

| 功能 | 驗證結果 |
|---|---|
| PRM V2 CSV、JSONL、SQLite 三方一致性 | PASS |
| SQLite 唯一 ACTIVE 發布批次 | PASS |
| TOC 跨基質管制標準配對 | PASS |
| TOC PDF PERFORMANCE 解析與分流 | PASS |
| PRM 結果顯示及合格判定 | PASS |
| 正式分析儲存時寫入 PRM 歷程 | PASS |
| PRM 歷程獨立查詢 | PASS |
| 分析紀錄刪除時同步刪除 PRM | PASS |
| 刪除稽核紀錄保留 | PASS |
| 舊孤兒 PRM 歷程清理 | PASS |
| 左側「性能確校查詢」選單 | PASS |
| 查詢結果「查看趨勢圖」 | PASS |
| 趨勢 Modal、實測點及三條管制線 | PASS |
| 移除檢測類別查詢條件 | PASS |
| 趨勢圖隱藏內部性能類型代碼 | PASS |

### 2.4 PRM 正式歷程與刪除完整性

資料表：`PerformanceMeasurementHistory`。

正式分析儲存透過既有分析紀錄服務，將 PRM 歷程與 `AnalysisRecord.analysis_id` 關聯。

已驗證：

1. PDF 解析出的 PRM 可隨正式分析紀錄保存。
2. 歷程包含儀器、管制項目、性能類型、分析日期、實測值及判定結果。
3. 歷程保留當次適用的參考值與管制上下限。
4. 重新儲存同一分析紀錄時應避免重複新增歷程；已有既有同步流程及相關測試。
5. 刪除分析紀錄時，同步清除該分析紀錄所屬的 PRM 歷程。
6. `AnalysisDeleteHistory` 刪除稽核紀錄必須保留。

2026-10-16 實測刪除結果：

- 被刪除的分析主紀錄：0 筆。
- 對應 PRM 歷程：0 筆。
- 刪除稽核歷程：1 筆。
- 其他分析主紀錄與 PRM 歷程：各保留 1 筆。
- `PRM DELETE CASCADE TEST: PASS`。

舊孤兒 PRM ID 1 已清理，保留有效 PRM ID 2。

### 2.5 PRM 趨勢圖與獨立查詢

已完成共用趨勢圖 Modal：

`templates/components/analysis/performance_trend_modal.html`

API：

`/analysis/performance-trend`

查詢條件以：

`instrument_id + monitor_item + performance_type`

識別性能歷程，預設顯示最近 30 筆。

圖表顯示：

- 實測值。
- 歷史參考值。
- 歷史管制上限。
- 歷史管制下限。
- 分析日期。

已驗證只有 1 筆歷程時，實測點與三條管制參考線均正常。

獨立查詢頁面：

`/performance-history`

模板：

`templates/performance_history_query.html`

左側選單已整合至 `templates/base.html`。

查詢介面已移除 D／G／W 類別篩選，趨勢圖已隱藏 `CAL_HIGH_SIGNAL` 等內部類型代碼，但查詢 API 仍保留必要參數。

### 2.6 Git 版本檢查點

已確認：

`dc57790 (HEAD -> main) Implement PRM V2 controls, history, query and delete integrity`

此 Commit 包含 PRM V2 核心服務、資料模型、TOC 整合、正式儲存、刪除完整性、歷程查詢及趨勢圖相關程式。

**注意：** 此 Commit 之後的左側選單及查詢介面精簡修改，尚未確認已 Commit 或 Push。

### 2.7 後續待辦

- PRM V2 查詢介面修改與開發文件建立下一個 Git Commit。
- PRM 管制標準停用及重複配對的專項驗證。
- PRM 手動輸入功能及驗證規則尚待設計。
- Performance CSV 發布流程自動化及安全驗證。
- 正式多人環境的工作狀態持久化與隔離。
- 其他分析附屬資料表的孤兒紀錄與外鍵完整性檢查。
- 正式環境、不同方法與不同儀器性能模式的完整回歸測試。


## 2.8 PFM V2.1 儀器性能確校事件與分析關聯（2026-10-16）

### 2.8.1 核心設計

PFM V2.1 採用「獨立性能確校事件 + 正式分析關聯」架構。

- `PerformanceMeasurementHistory`：保存一次實際儀器性能確校事件。
- `PerformanceAnalysisLink`：建立性能確校事件與正式分析紀錄的多對多關聯。
- `AnalysisRecord`：正式保存 D／W／G `category`，供分類查詢與管理。
- `AnalysisWorkState`：保留表單工作狀態與 PFM 原始解析資料。

同一次性能確校可供不同檢測類別的正式分析紀錄共用，不因 D／W／G 類別分別建立 Event。

PFM Event 不保存 `category` 或 `analysis_id`；類別由關聯的 `AnalysisRecord.category` 取得。

### 2.8.2 PFM Event 識別原則

目前以以下欄位判斷同一次性能確校事件：

- `instrument_id`
- `monitor_item`
- `performance_type`
- `analysis_datetime`

其中 `analysis_datetime` 必須取自 PDF 原始性能確校量測時間，不得使用正式儲存時間代替。

同一天不同時間的性能確校應建立不同 Event。

如果識別欄位相同，但實測值、方法或管制資料不一致，系統應拒絕當作相同事件，避免錯誤共用。

### 2.8.3 分析關聯與刪除規則

`PerformanceAnalysisLink` 使用：

- `performance_id`：對應 PFM Event。
- `analysis_id`：對應正式分析紀錄。
- `prm_sequence_no`：對應分析工作狀態內的性能確校序號；保留既有程式命名。

刪除正式分析紀錄時：

1. 刪除該分析紀錄對應的 Link。
2. 若 Event 仍被其他正式分析紀錄引用，必須保留。
3. 只有最後一筆 Link 消失後，才可清除該無其他引用的 Event。
4. 保留正式分析紀錄刪除稽核資料。

未來獨立於正式分析紀錄的設備維護性能確校，需另行設計其保留及生命週期規則。

### 2.8.4 實際驗證資料

測試檔案：`TOC1151013.pdf`

- 儀器：`A0087-02`
- 管制項目：`TOC`
- 性能類型：`CAL_HIGH_SIGNAL`
- PDF 分析時間：`2026-10-13 17:12:00`
- 實測值：`210635`
- 參考值：`204718`
- 管制下限：`190221`
- 管制上限：`219214`
- 判定：`PASS`

實際 Flask 正式儲存結果：

- D 類：`AnalysisRecord` ID 3
- W 類：`AnalysisRecord` ID 4
- PFM Event：1 筆
- PFM Link：2 筆
- 歷程顯示類別：`D、W`

刪除驗證：

- 刪除 D 類後：Event 仍為 1 筆，歷程類別改為 W。
- 刪除最後的 W 類後：歷程查詢為 0 筆。
- SQLAlchemy 刪除服務測試：PASS。

### 2.8.5 查詢與趨勢功能

`performance_history_query_service.py`：

- 類別篩選直接使用 `AnalysisRecord.category`。
- 不再依賴解析 `AnalysisWorkState.form_data_json` 取得類別。
- 同一 Event 即使有多筆分析關聯，查詢仍僅回傳一筆。
- 可依儀器、測項、判定結果及 PDF 分析日期範圍篩選。
- 類別顯示合併所有實際關聯類別，例如 `D、W`。

`performance_trend_service.py`：

- 使用 `analysis_datetime` 排序。
- 同一實際量測只顯示一個趨勢點。
- 保留當次實測值、參考值、管制上下限。
- 單筆量測及無資料查詢均已通過服務測試。

### 2.8.6 已完成測試

| 測試項目 | 結果 |
|---|---|
| PFM Event / Link SQLite 模型重建 | PASS |
| PDF 分析時間解析與錯誤格式檢查 | PASS |
| 相同 Event 比對及衝突檢查 | PASS |
| D／W 正式分析儲存 | PASS |
| D／W 共用 1 Event、2 Links | PASS |
| 重複同步避免新增 Event | PASS |
| PFM 獨立歷程查詢 | PASS |
| D／W／G 類別篩選回歸 | PASS |
| 日期區間及 PASS／FAIL 篩選 | PASS |
| 趨勢資料服務測試 | PASS |
| 刪除部分分析時保留共用 Event | PASS |
| 刪除最後一筆分析後歷程歸零 | PASS（網頁） |
| 測試交易 ROLLBACK | PASS |

### 2.8.7 本次修改檔案

- `app.py`
- `models.py`
- `services/analysis_record_service.py`
- `services/performance_history_service.py`
- `services/performance_history_query_service.py`
- `services/performance_trend_service.py`

### 2.8.8 待辦與注意事項

- PFM V2.1 尚待正式 Git Commit。
- 需確認完整資料庫清除結果及刪除稽核紀錄。
- 實際 Flask 趨勢圖 UI 的 V2.1 回歸仍可補測。
- 未來不同儀器、不同方法與多次同日量測仍需擴充實測案例。
- 同一儀器、項目、類型及時間出現不同量測內容時，現行設計採衝突拒絕，未來需評估時間精度與事件識別條件。
- 生產環境 Firebird 遷移與多人並行一致性尚未驗證。
- 程式部分識別名稱仍沿用 `prm_*`，後續整理時應避免一次全面改名影響既有流程。
- SQLite 測試資料可重新建立，但不得將開發環境的刪除重建操作直接套用至正式資料庫。


## 3. 其他暫停／未完成工作（不可遺漏）

| 項目 | 進度／注意事項 |
|---|---|
| ICP 檢驗紀錄 | 已有 ICP5800 原始量測／候選量測、分析模組等工作，**暫停等待回到原流程**；不得標示完成。恢復時先核對原開發對話與最新檔案。 |
| ICP 多波長整合 | 原始量測／候選量測及正式結果多波長選擇整合仍待追蹤驗證。 |
| QA/QC 表格調整 | `templates/components/analysis/qaqc_check_section.html` 存在尚未提交的 UI 修改；另有較長樣品編號欄寬與 MS/MSD 顯示需求。 |
| D／W 類別過濾 | `analysis/analysis_batch_splitter.py` 已修正 DUP/MS/MSD 類別漏入；但通用 `MS-1`／`DUP-1` 等不含正式樣品編碼的跨方法回歸仍需驗證。 |
| TOC 波長提示 | TOC 使用 Area Counts，分析頁共用的「無有效波長」警告不適合 TOC；使用者同意**暫時不處理**。 |
| W434 TOC PDF 解析異常（待 DEBUG） | 2026-10-16 發現原始 PDF 中出現 `1CCV1`，疑似使 CCV1 無法正確辨識，導致 D 類分析紀錄前段的 ICV、BK1、QC1 等資料被錯誤納入。尚未確認根因。後續須檢查 `parsers/oi_toc_parser.py`、樣品角色分類與資料切分流程；不可直接將問題歸因於 QC1 品管結果。 |
| Performance CSV 發布操作簡化 | 目前發布機制存在繁瑣的人工備份及啟用寫入開關流程。日後要改善成管理者選 CSV → 自動驗證差異 → 確認 → 自動備份與一致發布；**在自動備份／安全流程完成並測試前，不可直接移除保護**。 |
| 分析工作狀態持久化與隔離 | `analysis/analysis_state.py` 使用全域 `_analysis_states = {}`，僅存在 Flask 程序 RAM；重啟消失且不同使用者／Worker 可能互相覆蓋。屬正式多人使用前必要改善，現階段避免貿然波及所有分析流程。 |
| LIMS／Firebird 整合 | 既有資料庫與正式紀錄流程持續整合；不能因 PRM 專案而假設各模組已全部完成。 |

## 4. 關鍵程式檔案

| 檔案 | 用途 |
|---|---|
| `app.py` | Basic Info、分析路由、PDF 匯入、工作狀態、正式儲存、Performance 發布路由。 |
| `analysis/performance_classifier.py` | 依 PERFORMANCE／PFM 精確分流 PRM。 |
| `analysis/analysis_state.py` | 目前僅 RAM 的分析工作狀態。 |
| `analysis/analysis_batch_splitter.py` | 依測項／樣品類別切分及過濾批次。 |
| `parsers/oi_toc_parser.py` | TOC PDF 解析、原始 Area、分析日期及 replicate。 |
| `services/performance_query_service.py` | 依 ACTIVE 發布版本唯一查詢管制標準。 |
| `services/performance_import_service.py` | Performance CSV 解析與匯入準備。 |
| `services/performance_release_service.py` | Performance 正式發布與一致性檢查。 |
| `models.py` | SQLAlchemy 資料模型，包含 `AnalysisRecord`、`PerformanceMeasurementHistory`、`InstrumentPerformanceControl`、`PerformanceImportHistory` 等。 |
| `templates/components/analysis/performance_section.html` | PRM 分析結果表格。 |
| `templates/methods/w43401.html` | TOC 分析頁，含 PRM 元件。 |
| `templates/components/analysis/qaqc_check_section.html` | QA/QC 表格，存在未完成 UI 修改。 |
| `services/performance_history_service.py` | PRM 正式歷程儲存與同步；同一分析紀錄重新儲存時更新所屬歷程。 |
| `services/performance_history_query_service.py` | 獨立性能確校歷程查詢，依儀器、測項、日期及判定結果篩選。 |
| `services/performance_trend_service.py` | 查詢最近 30 筆 PRM 歷程，供趨勢圖 API 使用。 |
| `services/analysis_record_service.py` | 分析紀錄正式儲存服務，整合 PRM 歷程同步。 |
| `templates/components/analysis/performance_trend_modal.html` | 共用 PRM 趨勢圖 Modal，包含 Chart.js 圖表及開啟、關閉事件。 |
| `templates/performance_history_query.html` | 獨立「性能確校查詢」頁面，包含歷程查詢與趨勢圖按鈕。 |
| `templates/base.html` | Phyon 共用版型及左側選單，已加入「性能確校查詢」。 |
| `tools/initialize_prm_v2.py` | PRM V2 初始化前置檢查工具；不屬於一般正式發布流程。 |
| `tools/backup_prm_v1.py` | PRM V1 資料備份工具；供版本轉換及開發資料保護使用。 |

## 5. Git 版本與未提交工作

### 5.1 PRM V2 已確認的 Git Commit

- 分支：`main`
- Commit：`dc57790`
- 訊息：`Implement PRM V2 controls, history, query and delete integrity`
- 已提交 15 個程式檔案，包含 PRM V2 核心服務、資料模型、TOC 整合、歷程查詢、趨勢圖及刪除完整性修正。

### 5.2 Commit 後的工作

2026-10-16，在 `dc57790` 之後又完成：

1. `templates/base.html`：新增左側「性能確校查詢」選單。
2. `templates/performance_history_query.html`：新增查詢結果的趨勢圖按鈕，並引用共用 Modal。
3. `templates/performance_history_query.html`：移除 D／G／W 檢測類別查詢條件。
4. `templates/components/analysis/performance_trend_modal.html`：隱藏 `CAL_HIGH_SIGNAL` 等內部性能類型代碼。
5. `docs/PHYON_DEVELOPMENT_STATUS.md`：更新開發進度與交接紀錄。

上述修改已由使用者回報網頁測試成功，但尚未確認建立新的 Git Commit。

### 5.3 未追蹤檔案與資料保護

先前的 Git 狀態包含：

- `instance/`：SQLite 資料庫及備份。
- `backups/`：性能管制資料與發布備份。
- 測試 PDF 與 PRM V2 CSV。
- Firebird／LIMS 測試程式。
- `tools/`：PRM V1 備份與 V2 初始化工具。
- `docs/`：開發文件。

這些檔案是否納入版本控制，應逐項檢查。

**禁止直接執行 `git add .`。**

尤其不得在未審查前提交 SQLite 資料庫、備份、測試 PDF、連線設定或可能包含帳密的檔案。

### 5.4 下次續接檢查

進入下一個開發階段前，先執行：

```powershell
git status --short
git log -1 --oneline
```

## 6. 換聊天室交接步驟

1. 提供本文件最新內容，並說明「繼續 Phyon，依照 `PHYON_DEVELOPMENT_STATUS.md` 接續」。
2. 提供最新 `git status --short` 與 `git log -1 --oneline`；必要時提供目前正在修改的檔案片段。
3. 先確認**現在主線、已驗證項目、尚未提交修改與暫停工作**；勿直接重寫或回滾。
4. 只挑一個最小修改步驟，測試 PASS 後再更新本文件相應進度。
5. 遇到文件與實際 Code 不一致時，**以已檢查的現有 Code／測試結果為準**，更新文件並說明差異。

## 7. 下次續接的第一件事

### 7.1 目前優先主線：W434 TOC PDF 解析異常

2026-10-16，使用者重新檢查 `TOC1151013.pdf`，發現原始資料中的樣品識別碼出現 `1CCV1`。

目前觀察到的問題：

- `CCV1` 疑似因前方多出 `1` 而無法被正確辨識。
- D 類分析紀錄前段出現 ICV、BK1、QC1 等不應納入該區段的資料。
- 尚未確認錯誤發生於 PDF 文字解析、樣品角色分類或分析批次切分。
- 不可直接把 QC1 的品管判定當成問題根源。

**下一階段採取唯讀診斷，不立即修改 Parser。**

依序確認：

1. `TOC1151013.pdf` 的原始 Sample ID 與解析結果。
2. `parsers/oi_toc_parser.py` 如何辨識 `1CCV1`。
3. `analysis/performance_classifier.py` 與其他樣品分類邏輯是否受到影響。
4. ICV、BK1、QC1、CCV1 與正式樣品的資料區間如何切分。
5. 找到根因後，僅修改必要的解析或分類規則，並以 W／D 類別進行回歸測試。

特別注意：不可未經確認就全面移除 Sample ID 的數字前綴，避免誤改合法樣品編號。

### 7.2 PRM V2 目前狀態

PRM V2 核心功能已完成實測，包括：

- 跨 D／G／W 類別共用儀器性能管制標準。
- 正式分析儲存與性能歷程同步。
- 分析紀錄刪除時同步清除 PRM。
- 左側獨立「性能確校查詢」。
- 查詢結果趨勢圖與共用 Modal。
- 隱藏內部性能類型代碼。

已確認 Git Commit：

`dc57790`

**注意：** 左側選單、查詢介面精簡及本開發文件的後續修改，仍須確認新的 Commit。

### 7.3 不得遺漏的後續工作

- ICP5800、多波長整合與原有分析流程。
- R318、R300 等分析方法的既有開發工作。
- QA/QC 表格及其他尚未完成的介面需求。
- PRM 手動輸入、停用標準與重複配對測試。
- Performance CSV 發布流程簡化。
- 分析工作狀態持久化及多人隔離。
- SQLite／Firebird 外鍵關聯及既有孤兒資料檢查。
- LIMS／Firebird 正式環境整合。

上述工作不得因 PRM V2 階段完成而標示為全部完成。

### 7.4 跨聊天室續接原則

1. 先閱讀本文件最新版本。
2. 執行 `git status --short` 與 `git log -1 --oneline`。
3. 確認已完成項目、未提交變更及目前待處理 Bug。
4. 每次只進行一個小範圍修改，提供明確 Code 定位。
5. 測試 PASS 後再進行下一步，避免同時更動多個分析模組。


## W430 建置完成與驗收（2026-10-25）

方法：NIEA W430.52C 水中硫酸鹽檢測方法－濁度法。

已完成：
- 檢量線、PFM、樣品 TXT 可分檔或合併匯入。
- 單一線性檢量線、相關係數、QDL 與樣品及 QA/QC 計算。
- A 液樣品不扣 BKA；B 液樣品扣除對應 B 空白的回歸含量，再換算濃度及稀釋倍數。
- BKB 單獨扣除 1.5 mg 後執行空白判定，不用於樣品濃度扣除。
- UV 最大吸光值及石英槽比對判定、PFM 儲存與趨勢查詢。
- 樣品刪除、排序、稀釋倍數調整、重新計算與暫存恢復。
- 正式儲存後進入待審核並移出暫存清單，底層 Draft 與原始資料保留。
- 正式紀錄、五組快照、Draft 與 PFM 關聯共用交易。
- PDF 儲存前即可匯出，每批次一頁，備註只保留分析判讀。
- LIMS Excel 沿用共用模組及既有範本，輸出品管與一般樣品兩張工作表。
- LIMS 樣品編號移除稀釋標記，MDL／QDL 依各列稀釋倍數判讀。
- 移除工作頁儲存後右側的分析紀錄查詢入口。

驗收狀態：
- 居家開發環境：匯入、計算、PFM、暫存恢復、正式儲存、PDF 與 Excel 匯出已通過操作確認。
- W430 退回修正及審核者代修：整合測試通過，實際帳號操作待驗收。
- UV PFM 管制範圍目前為暫定測試版本，待實際數據精算後更新。
- LIMS 實際匯入及 Server 部署尚待確認。
- 不以開發電腦 SQLite 覆蓋 Server 資料庫。

