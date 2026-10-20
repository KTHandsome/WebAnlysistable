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

