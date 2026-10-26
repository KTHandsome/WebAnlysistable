# TOC PDF 配置（2026-10-26）

- 僅 METHOD_CODE=W532 啟用新配置：左側 PFM、右側檢量線；兩表上框線對齊，方程式及 r 在檢量線上方。
- PFM 直接讀取傳入 analysis_state.prm_results：signal、signal_field、sample_id、analysis_datetime、status 及 control 參考值／上下限。不重新查詢目前 CSV 或重新判定。
- 無 PFM 資料明示「未載入 PFM 查核資料」，不製造合格結果。
- 保留所有標準點、原格式位數、TIC／TIC-SPK、滿版樣品／QAQC、簽核及原批次分頁。
- As／Se／Hg 保留既有繪製路徑，後續獨立驗收。
- 不修改計算、資料庫、儲存或匯出路由。若舊工作未存 prm_results，需由使用者確認原始資料來源。
- 本地以代表性六點檢量線、PFM、TIC 與樣品資料產生並渲染檢查；Windows 真實工作驗收待套用。
