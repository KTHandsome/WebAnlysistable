# ICP 基本資料類別匯入篩選（2026-11-03）

- 新上傳 ICP5800 PDF 時，依 basic_info_form.category 及共用正式樣品編號辨識規則選取完整批次。W 僅帶入 W 批次、G 僅帶入 G 批次；同批混類、無法確認類別／批次、查核批次編號不明或沒有符合批次時，顯示提示且不建立新工作。
- 在建立工作之前完成篩選，原始量測、候選量測、批次設定、LIMS 配對及後續計算皆讀取相同 parsed_data.rows。
- 檢量線及性能列共用保留；共用 CCBK n／CCV n 依 build_batch_memberships 保留相鄰批次所需起始／結束查核，BK/QC/DUP/MS/MSD 跟隨批次。不以樣品字首逐列刪除 QA/QC。
- 保留原 sequence、批次編號及數值，不重新編號。每列附 import_category_batch_ids，build_batches 僅列出保留批次，避免共用結束查核復活已排除批次。
- 完整解析列保存在 parsed_data.source_rows，介面及計算仍僅使用 rows；原始來源為解析資料，並非另存原始 PDF 檔案。
- 舊暫存／正式快照不自動修改。請從基本資料選類別後重新上傳測試 PDF，舊工作仍按原流程處理。
- 修改 app.py、services/icp_batch_category_service.py、新增 analysis/icp_category_scope.py；parser及共用樣品類別辨識、候選分組不修改，安裝時驗證版本依賴。
- 無 DB 初始化、migration、CSV 或環境變更。

## 驗收
1. W/G 分別新匯入同份混合 PDF：原始量測與候選均僅有該類正式樣品。
2. 只保留第2批時，第1批不出現在批次設定；CCBK1/CCV1及CCBK2/CCV2仍完整。
3. 批次內 DUP/MS/MSD、BK/QC 及檢量線保留，類別切換後需新匯入，不挪用舊選擇。
4. 暫存、F5及後續數據頁確認範圍一致；一般舊工作與其他方法不變。
