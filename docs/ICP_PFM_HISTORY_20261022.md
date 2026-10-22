# ICP PFM 歷程與趨勢圖 — 2026-10-22

## 本次整合
- 計算並儲存 PFM 時，工作 JSON 與 PerformanceMeasurementHistory 在同一 SQLAlchemy Session、同一交易儲存，失敗一起 rollback。
- 新增 icp_pfm_history_service.py，沿用共用事件內容比對，不修改單測項正式紀錄服務。
- 日期取基本資料分析起始日；既有 DateTime 欄位用當日零時表達「只有日期」，message 明確註記未提供實際測定時間，不冒充儀器 PDF 時間。
- history_event_id 保存在工作 PFM 區段；不建立假的 AnalysisRecord 或 PerformanceAnalysisLink。
- 在計算按鈕右側加入查看趨勢圖，共用 performance_trend_modal.html 與既有 /analysis/performance-trend。
- 管制來源仍為正式 ACTIVE 設定，W311 Se/Pb、M104 Pb/Cu；不讀開發 CSV 作判定。

## 重複與更正
- 依既有唯一鍵：儀器、監控項目、性能類型、分析日期。同日完全相同的事件重用，不因不同金屬／波長或重按儲存新增點。
- 比值與界限依既有 Numeric(20,8) 欄位精度正規化後比對，避免非整除比值重存時誤判衝突。判定仍用原始 Decimal 計算，不改成四捨五入後比較。
- 同一工作獨占且尚未連結正式紀錄的事件可更正，維持同一事件 ID。
- 不覆寫其他工作共用、正式紀錄已連結、非本工作建立或內容已被更動的事件；同日不同內容提示衝突並 rollback。
- 儲存前檢查工作版本及基本資料，工作 CAS 成功後才寫歷程；唯一鍵競爭失敗也回復整筆交易。

## 查詢與舊工作
- 儀器／監控項目／日期查詢可以看到尚未連結正式分析紀錄的事件。
- 既有類別篩選仍來自正式 AnalysisRecord 的關聯；ICP 工作橫跨多個批次類別且未建立正式紀錄時，請先不填類別。未改寫既有類別查詢規則。
- 舊工作不自動掃描回填。套用後重新按一次計算並儲存 PFM，即同步該筆工作。
- 不新增資料表、不初始化或 Migration、不自動覆寫既有正式資料。

## 驗證與待驗收
- 使用實際模型的 SQLite 記憶體資料庫，通過首次儲存、非整除比值重存、獨占更正、共用保護、正式連結保護、同日衝突、W311／M104 分流及尚未正式送審的歷程查詢。
- 通過事件新增後失敗、事件更正後失敗、commit 失敗時工作與歷程共同 rollback。
- Python 3.8、Jinja、共用趨勢圖 JavaScript 語法檢查通過；按鈕順序、資料屬性及共用視窗渲染檢查通過。
- 實際瀏覽器歷程查詢／趨勢圖及 Server Firebird 尚待驗收；本次未操作正式資料庫。
