# W427 LIMS Excel 匯出（2026-10-26）

## 操作與範本
- 使用者已確認 PDF 版面微調成功；本次完成 W427 LIMS Excel。
- PDF 右側新增「匯出 LIMS」，儲存前後均可使用；正式紀錄查詢亦可匯出。
- 範本沿用 resources/lims/lims匯入表格.xlsx，共用 LimsExportData、w434 mapper 與 lims_excel_exporter 不修改。
- 工作表／欄位維持「Lims-品管數據」及「Lims-分析數據」，第 5 列起；表頭日期為基本資料分析起始日期、方法為年度控制 EM_NO。
- 使用同一下載處理顯示頁內錯誤，不跳轉訊息頁；匯出不自動暫存、提交或修改 PFM 歷程。

## 數值與配對
- 一批一列品管、僅一般 SAMPLE 進分析表；DUP／MS／MSD／BK／ICV／CCV／QC 不混入一般樣品。
- 樣品編號以原始解析 base_id 輸出，移除 *稀釋標記。已刪除列不輸出。
- 樣品最終濃度已含體積、前處理、D 與物種換算；QAQC_CONC_FACTOR 在匯出 adapter 固定 1，正磷酸鹽 3.07 不重複套用。
- 年度 MDL 為報告單位，再依該列 D 調整；QDL 使用已算出的該列值。沿用共用 ND<MDL／<QDL／六位數結果與備註格式。
- QC／MS 回收率、RPD、CCV 相對誤差使用已計算的 mg P/L 基準百分比；最高吸光度取檢量線標準點，不拿石英槽或 PFM 取代。
- G Batch2 的結束 CCV2 明確帶入，不誤拿開始沿用的 CCV1。
- BK 依實際最終濃度與 MDL×D×倍率比較，不因有 BK 就固定填 <2MDL。
- 缺少 MDL、QC、MS、RPD、結束 CCV、BK，或同一樣品有多個採用結果，均拒絕匯出；缺值不填零。
- 同批多組原樣超出既有 LIMS 單列品管模型時拒絕，不默默取第一組或新增聚合規則。
- 批次流水號沿用基本分析日期＋檢測代碼＋原批號，G Batch2 保持 2。多個測定日期若導致流水號重複，提示分開工作後匯出，不靜默覆蓋。

## 快照與驗證
- 未送審輸出目前表格編輯／批次備註，經原 QA/QC 放行檢查；不寫資料庫。
- 正式匯出共用五組 JSON 快照讀取器，不讀新 CSV 或 Session；原分析員姓名／代號從 AnalysisRecord 取得，審核者代匯出不改成審核者。
- 共用 PDF 快照讀取器僅抽出 load_w427_record_snapshot，PDF 行為維持，既有對齊微調 renderer 不納入本更新包。
- 測試 TP／磷酸鹽磷／正磷酸鹽、D／ND／QDL、G CCV2、BK、原樣編號／排除、重複樣品／批次／QAQC拒絕、兩張實際 xlsx 工作表與模板表頭／格式保留。
- Flask 匯出／正式快照／原分析員／資料庫不變、PDF 回歸、JS 下載與錯誤訊息、Python 3.8、精確來源安裝器。
- 使用者 Windows Excel／LIMS 實際匯入驗收待套用。本次不修改 CSV、資料庫或環境變數。
