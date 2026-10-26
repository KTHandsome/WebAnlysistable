# W427 正式分析紀錄（2026-10-25）

## 進度
- 使用者已確認 W427 暫存成功。
- 本次接入儲存／送審／查詢／退回恢復；PDF 與 LIMS Excel 匯出留待後續，避免誤用舊匯出器。

## 行為
- 基本資料與儀器性能查核右側加入「儲存分析紀錄」。直接包含目前樣品倍數、排序、刪除及批次備註，不必先按更新／暫存。
- 儲存成功正式紀錄為 UNDER_REVIEW，工作為 SUBMITTED，自本人暫存清單移除；重載／返回已送工作時暫存、儲存、樣品編輯與 PFM 儲存停用。
- 延續既有正式 Analysis Identity：測項＋方法＋儀器＋分析日期區間。其他未關聯工作若遇相同正式 Identity 即拒絕，不覆寫既有紀錄。
- 區塊 3 開放批次備註，跟隨更新／暫存／正式儲存保存；以日期＋批次／原樣識別，避免跨日期備註互相覆蓋。
- 沿用共用 QA/QC 放行規則：超限／無法判定需批次備註；缺少原樣配對、重複角色或前後查核不完整不得靜默送審。r 判定維持 UI 的 r > 0.995。
- PFM 必須完成兩項 PASS／FAIL 判定；沿用單項流程可保留 FAIL 提交審核，不自動宣告合格。
- 正式查詢保留檢量線、樣品、QA/QC、審核歷程；W427 顯示 mg P/L 與最終報告單位說明。
- 退回恢復同一 work_id，修正後更新原正式紀錄，不另增紀錄；保留審核者代修權限與原分析員，沿用共用授權及稽核。

## 交易與計算
- 共用同一 SQLAlchemy Session，service 無 commit／rollback／close；route 成功一次 commit，任何失敗 rollback。
- AnalysisRecord、樣品／檢量線／QAQC、AnalysisWorkState 五組 JSON、AnalysisWorkDraft 提交狀態與 PFM 歷程／關聯同一交易。
- 共用正式服務以 db=／strict_work_identity=True 寫入，PFM 由 W427 既有事件識別去重後關聯兩筆；原 AA 同步器接收空 PFM 列，不重複記錄。
- 正式快照還原成 W427 五組工作 bundle，Repository 驗證完全一致才更新 SUBMITTED。
- mg P/L 回歸與 QA/QC 基準保留；正磷酸鹽 3.07 只在樣品最終濃度套用一次。
- 不建立資料表、不調整 CSV 或環境變數。

## 驗證
- 實際共用正式服務與 SQLite：直接送審／暫存後送審、待審核狀態、清單移除、唯讀、五組快照一致、PFM 去重關聯、重複送出拒絕。
- 失敗發生在正式寫入後／Draft 提交後時全部 rollback；外層 commit 前亦可 rollback。
- QA/QC 備註／驗證、3.07 單次換算、原分析員及具審核權限者退回恢復／再送審。
- Python 3.8／JS 語法、安裝器 check-only／apply／重複套用／來源不符保護。
- 使用者 Windows／正式 Firebird 排版與實際操作驗收待套用後進行。
