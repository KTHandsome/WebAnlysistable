# Phyon 開發進度與跨聊天室交接紀錄

> 文件版本：V1.1｜更新日期：2026-10-16
> 目的：保留已驗證功能、目前開發主線、暫停工作、關鍵設計決策及接續位置。  
> 注意：本文件依目前對話整理；未實際執行的測試、尚未確認的 Commit 與正式儲存功能，不得標示為完成。

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

