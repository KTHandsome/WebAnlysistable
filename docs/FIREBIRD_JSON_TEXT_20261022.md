# Firebird 大型 JSON BLOB 讀取相容修正 — 2026-10-22

## 問題證據

Server Firebird 5.0 匯入 ICP PDF 後，INSERT 與 COMMIT 成功；重導至 GET /analysis/icp/import 時，json.loads(record.state_json) 收到 BlobReader 而非 str，造成 TypeError。約 140 萬字元的工作 JSON 已存在，不需刪除或重新匯入。

## 修改

- models.py 新增 JsonText(TypeDecorator)，底層仍為 Text。
- 僅套用 12 個 *_json 欄位：AnalysisWorkState 五欄、AnalysisWorkDraft 五欄、IcpImportWorkState.state_json、PerformanceImportHistory.control_versions_json。
- SQLAlchemy 取回結果時，遇到 reader 便在連線仍開啟時 read 並 close；文字直接保留，位元資料以 UTF-8 解碼；異常不吞掉。
- JSON 仍由原有服務解析；WHERE／CAS 使用已讀出的完整文字，避免重新使用已耗盡或已斷線的 BlobReader。
- notes／message 等其他 Text 欄位、既有字串／JSON 值與寫入規則不更改。
- 不初始化、不 Migration、不異動資料表、不改 Firebird 帳密／環境、不刪除工作或正式紀錄。

## 驗證及限制

- 隔離 SQLite DBAPI TEXT converter 模擬 BlobReader，經實際 ORM 結果處理器讀取 140 萬中文字元 JSON；驗證 json.loads、重新載入、連線關閉後存取、條件更新、Commit／Rollback 與串流釋放。
- 一般 SQLite 字串、None、UTF-8 bytes／bytearray／memoryview、讀取失敗釋放、12 欄範圍與 Python 3.8 語法已驗證。
- 尚未在本地連線 Server Firebird 執行；需使用者以原已暫存工作進行實際驗收。
- 修正須同步至開發電腦並 Commit／Push，讓 Server 後續版本保持一致。

## Server verification and required driver setting

- Server: Firebird 5.0; firebird-driver 1.10.11;
  sqlalchemy-firebird 2.1; SQLAlchemy 2.0.36.
- JSON result conversion alone was insufficient: the cursor could close
  a streamed BlobReader before SQLAlchemy processed its value.
- In database.py, the Firebird branch sets
  driver_config.stream_blob_threshold.value to sys.maxsize before connections
  are opened, so BLOB values are materialized by the driver.
- The existing ICP work was read successfully without reimport:
  1,403,406 JSON characters, parsed as a dictionary.
- After restarting the Server, the ICP import page opened without errors.
- models.py and database.py fixes were also applied to the development computer.
- No database schema or stored data was changed by these fixes.
- Full Server ICP save, review and export acceptance remains pending.
