# W430 LIMS Excel 匯出 — 2026-10-25

- 重用 exports/w434_lims_mapper、lims_export_model、lims_excel_exporter 與 resources/lims/lims匯入表格.xlsx，不修改共用匯出器與範本。
- 增加 W430 轉接層，依日期／批次建立 included_batches，轉接既有 QA/QC 欄位；每批品管一列、一般樣品一列。
- 只輸出 SAMPLE；SAMPLE_BLANK、BKA、BKB、DUP、MS、MSD 不作一般樣品送入 LIMS。
- 使用原解析資料 base_id 還原樣品編號，排除 *倍數 標記；同樣品／檢測代碼多個結果時阻擋，不自動挑選。
- 樣品結果採已完成 A/B 空白扣除與稀釋的 mg/L；不再次套用換算係數。MDL 乘該列 D，QDL 使用該列已調整門檻，沿用共用 ND／QDL 字串格式。
- 空白欄依 BKA/BKB 實際濃度中較高者判斷，不因空白列存在就直接填 <2MDL；缺少空白時阻擋匯出。
- 品管最高吸光度沿用共用的最高檢量點訊號；RPD、QC、MS、CCV、r 與批次備註沿用已計算結果。百分比小數一位維持既有 Excel 匯出器規則。
- 儲存前與 PDF 同樣輸出目前輸入，不新增或修改工作；已送審由正式快照匯出，分析員表頭保留原分析員。
- 移除 W430 工作頁儲存後右側「分析紀錄查詢」入口，保留 PDF／Excel 實際 button；全站原分析紀錄查詢功能不變。
- 共用正式快照讀取函式供 PDF、Excel 使用；不讀現行 CSV、不初始化資料庫、不 Migration。

## 本次驗證

- 使用原始 TXT、實際共用 mapper／model／Excel writer 與原 LIMS 範本，核對 1 列品管及 8 列一般樣品、原始樣品編號、71.751710 mg/L、批次鍵與分析員表頭；來源範本位元組未變更。
- MDL／QDL 依 D=4 驗證 3.992／20；濃度不重複轉換。BKB 超限回傳實際值、不假填 <2MDL；重複樣品結果阻擋。
- 兩批產出兩列品管、16 列一般樣品與各自批次鍵。
- 實際 HTTP 未儲存匯出，D 修改後結果 47.169716 mg/L；資料庫未新增 Draft、快照、正式紀錄或 PFM。CSRF 錯誤拒絕。
- 正式快照與正式 Excel 路由下載通過，後續設定變動不影響舊紀錄，保留原分析員；快照損壞時拒絕。
- Python 3.8、Jinja、JavaScript 與安裝器檢查／套用／重複執行通過。待使用者 Windows 實際匯出及 LIMS 匯入確認。
