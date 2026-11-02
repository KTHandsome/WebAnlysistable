# Phyon Server 關閉、同步與啟動 SOP

琨鼎環境科技股份有限公司檢驗室（FQ042）
文件日期：2026-10-28
適用位置：E:\PhyonWeb；Windows PowerShell；Waitress，TCP 80

## 1. 用途與責任

供網站維護人員更新及啟停 Phyon。一般使用者不必每天同步程式或重啟服務。更新前先通知使用者完成暫存，確認目前沒有匯入、儲存或匯出作業。

本次已同步版本：7a84407。未來更新以維護人員公告版本為準，不要把此版本當成永久更新目標。

## 2. 環境設定紀錄

| 項目 | 設定／說明 |
|---|---|
| 專案 | E:\PhyonWeb |
| Python | E:\PhyonWeb\.venv\Scripts\python.exe |
| 網站入口 | run_server.py；本機檔案，不納入本次 Git 更新 |
| 網站執行器 | Waitress，0.0.0.0，TCP 80 |
| Phyon 資料庫 | PHYON_DB_TYPE=firebird |
| 已確認資料庫路徑 | E:/PhyonDatabase/PHYON.FDB |
| LIMS 登入 DSN | LIMSDB-FQ |
| ICP 委測查詢 DSN | 由 PHYON_LIMS_DSN 指定；程式未指定時預設 PHYON_LIMS |
| 目前可見 ODBC DSN | LIMSDB-FQ；未見 PHYON_LIMS |
| 本次待驗證設定 | PHYON_LIMS_DSN=LIMSDB-FQ；須完成 ICP 實際查詢驗證後，才能列為正式啟動設定 |

重要：Phyon 資料庫、LIMS 登入及 ICP 查詢是不同連線。可登入不代表 ICP 查詢正常。不要因為 ICP 查詢失敗就直接重啟資料庫。

PowerShell 的 $env: 設定只屬於該視窗及其子程序；關閉視窗後，新開視窗必須重新指定。不能假設上次設定仍存在。

## 3. 關閉網站服務

1. 通知使用者暫停操作並完成暫存。
2. 在原本執行 run_server.py 的視窗按 Ctrl+C，等待回到 PowerShell 提示字元。
3. 確認 80 埠已停止監聽：

```powershell
Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

沒有輸出，代表未偵測到 TCP 80 監聽者。若有輸出，不要直接關閉任意 python.exe，先確認擁有程序：

```powershell
$phyonListeners = Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue
$phyonListeners.OwningProcess | Sort-Object -Unique | ForEach-Object {
    Get-CimInstance Win32_Process -Filter "ProcessId = $_" |
        Select-Object ProcessId, Name, ExecutablePath, CommandLine
}
```

若命令回報權限問題，不能據此判定服務已停止。請由具權限人員確認。若監聽者不是本網站，停止更新並交由維護人員處理。原視窗已遺失時，只有確認完整程式路徑及命令列確實屬於本網站後，才由維護人員終止該 PID。

## 4. 同步程式

在 PowerShell 執行，每次只貼指令，不要把 PASS、warning 或提示字元當成指令貼入。

```powershell
Set-Location E:\PhyonWeb
git status --short
git log -1 --oneline
```

- 只有未追蹤的 backups/、run_server.py：可繼續；保留它們。
- 出現已追蹤程式的 M、D、A，或不認識的變更：停止同步並交由維護人員確認。
- 不使用 git add .、git clean、git reset --hard 或 git restore 來強行排除問題。

確認服務已停止後：

```powershell
git pull --ff-only origin main
git log -1 --oneline
git status -sb
```

核對版本與維護人員公告一致。若有衝突、被本機檔案阻擋或無法 fast-forward，不要改用強制更新；保留完整訊息。

Git 同步不會同步已匯入資料庫的 CSV 設定。若發版包含方法、報表、年度管制或性能設定更新，依發版清單另外匯入及發布。

本次 7a84407 不需建表或 migration。未來若發版要求資料庫異動，必須先完成 Firebird 備份與備份檢查，再按該版專用程序操作，不能自行執行 create_all 或匯入其他電腦的資料庫。

## 5. 啟動前檢查

```powershell
Set-Location E:\PhyonWeb
Test-Path .\.venv\Scripts\python.exe
Test-Path .\run_server.py
.\.venv\Scripts\python.exe -c "import pyodbc; print(pyodbc.dataSources())"
```

前兩項應為 True。ODBC 清單必須包含預定使用的 DSN；清單只代表可見設定，不代表連線或查詢成功。

確認 80 埠沒有其他程序監聽後，再啟動，避免重複啟動兩份網站。

## 6. 啟動網站

以下為目前 LIMSDB-FQ 連線驗證用啟動指令；ICP 委測查詢測試成功後，才固定採用。

```powershell
Set-Location E:\PhyonWeb
$env:PHYON_DB_TYPE = "firebird"
$env:PHYON_LIMS_DSN = "LIMSDB-FQ"
.\.venv\Scripts\python.exe -u .\run_server.py
```

啟動後保留該視窗，不能按 X 關閉。需要查程序或版本時，另開第二個 PowerShell。

若服務回到提示字元或視窗關閉，不能假設網站仍在執行，請重新檢查 TCP 80。若發生錯誤，保留 Traceback，先排除原因，不連續重複啟動。

### 正式固定設定方式

由維護人員在完成 ICP 查詢驗證後，將確認的資料庫及 DSN 設定納入 server 專用啟動檔，或未來的 Windows 服務設定；需另行測試及部署。本 SOP 本身不會修改 run_server.py、環境變數或建立 Windows 服務。

交接前必須以「關閉原視窗 → 開新視窗 → 使用交付的啟動方式 → 登入與 ICP 查詢成功」完成一次驗收，才能確認不依賴前次視窗的暫時設定。

## 7. 啟動後驗收

在第二個 PowerShell 確認監聽：

```powershell
Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

瀏覽器按 Ctrl+F5，依序確認：

1. 首頁及分析基本資料可開啟。
2. LIMS 帳密可登入。
3. 開啟既有 ICP 工作，進入 LIMS 委測配對，確認沒有「查詢失敗」。查詢成功但查無委測項目，與連線失敗是不同狀態。
4. 本次 W430 發版：使用測試／暫存工作，更新樣品及 QA/QC，確認 A/B 與 BKB；匯出 PDF，空白列顯示 -，QA/QC 小數一位，DUP 顯示 <= 15.0 %。

既有正式紀錄不會自動重新計算；需要更正時依退回修正程序辦理，不刪除正式資料來測試。

## 8. 常見故障與處理

| 現象 | 優先確認 | 處理 |
|---|---|---|
| 首頁無法開啟 | TCP 80 是否監聽、run_server.py 是否仍執行 | 保留錯誤；不要重複啟動 |
| 登入正常、ICP 查詢失敗 | PHYON_LIMS_DSN 與可見 ODBC DSN、查詢 Traceback | 不直接重啟 Firebird；核對啟動設定 |
| 重啟後 ICP 又失敗 | 新視窗是否漏設 PHYON_LIMS_DSN | 使用包含確認設定的正式啟動方式 |
| 顯示 sqlite3 或找不到 SQLite 表 | 是否啟動前漏設 PHYON_DB_TYPE | 停止錯誤網站程序；指定 firebird 後重新啟動，不在 SQLite 補建正式表 |
| Address already in use | TCP 80 擁有程序 | 確認是否已有本網站；不要隨機終止程序 |
| no such table／table unknown | 正確 DB、發版建表需求 | 交由維護人員，不自行補表 |
| PDF 數據仍舊 | 是否讀取既有正式快照、是否已重新計算暫存 | 按工作狀態處理，不直接修改 DB |
| git pull 失敗 | 本機修改、網路、遠端版本 | 保留訊息，不強制覆蓋 |

若要查看環境，必須在啟動前的同一視窗執行：

```powershell
$env:PHYON_DB_TYPE
$env:PHYON_LIMS_DSN
```

另一個新視窗的環境不一定與既有網站程序相同。不要將完整連線字串或密碼貼入問題回報。

## 9. 問題回報資料

提供發生時間、操作步驟、畫面錯誤、git log -1 --oneline、是否可登入、ICP 是否查詢失敗、80 埠擁有 PID，以及 server 最新 Traceback 的末段。可遮蔽帳號、密碼與連線資訊。

## 10. 交接紀錄

- 維護人員：____________
- 更新時間／版本：____________
- 啟動方式／啟動檔：____________
- 確認使用的 ICP DSN：____________
- 新視窗重新啟動驗證：通過／未通過
- 首頁／登入／ICP 查詢／本次功能測試：____________
- 異常與處理紀錄：____________
