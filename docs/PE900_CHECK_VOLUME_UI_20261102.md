# PE900 查核列體積及檢量線顯示

- W434/W341/R318/R300 數據頁，ICBK/ICV/CCBK/CCV 最終定量體積改採 FINAL_VOLUME_DEFAULT，25/50 方法即顯示取樣25 mL、最終50 mL；不再把最終體積誤設為取樣體積。
- 共用 recalculate_sample_rows 的 direct_instrument_roles 規則保持：四種儀器查核列濃度不套體積、額外D或前處理倍率；ICV/CCV QA/QC 使用 measured_concentration。避免因顯示體積50/25而意外多乘2。
- 一般樣品、BK/QC/DUP/MS/MSD 繼續依既有方法設定及體積倍率計算。其他方法體積規則不變。
- UI_SIGNAL_DECIMALS 未設定時，這四種方法以顯示用副本預設4位，檢量線0顯示0.0000、0.025顯示0.0250；明確 CSV 設定優先，不改方法快照或原始數值。
- 此檔案名稱含 UTF8 的方法設定實際為 CP950、Tab 分隔，本次僅核對而未修改或要求重新匯入。
- 僅修改 app.py 並附本文件，analysis_workflow.py 作為精確版本依賴驗證，沒有修改共用計算。
- 已正式儲存快照不自動改寫；為確認初始化請重新匯入測試 PDF。舊暫存若仍帶25 mL，不視為新匯入失敗，不刪除正式資料測試。
- 無 DB 初始化、migration、環境、CSV 或 PE900 parser 變更；可接續前一個 parser 補丁。

## 驗收
1. 重新匯入 As/Se：ICBK/ICV/CCBK/CCV 最終定量50 mL。
2. ICV/CCV 測定及樣品濃度仍為原儀器回歸濃度，相對誤差不因體積顯示而改變。
3. 一般樣品25/50按2倍換算；R300固定前處理倍率及其他檢項不受本次變更影響。
4. 檢量線所有測定值依設定顯示；空白設定預設4位，重新計算/暫存/F5後確認。
