"""W427 880 nm preview. Reuse UV text decoding; never calculate or store results."""
import re
from parsers.uv_txt_parser import parse_uv_text, MAX_FILE_BYTES, MAX_TOTAL_BYTES, MAX_ROWS


LABELS={"STANDARD":"檢量線","PFM":"PFM","CELL_CHECK":"石英槽比對","INSTRUMENT_BLANK":"儀器 BLANK",
        "SAMPLE":"樣品","BK":"空白","ICV":"ICV","CCV":"CCV","QC":"QC","DUP":"重複","MS":"添加","MSD":"添加重複","UNKNOWN":"待辨識"}


def build_w427_preview(files, category):
    if not files or len(files)>20:raise ValueError("請選擇 1～20 個 TXT 檔案。")
    if sum(len(b) for _,b in files)>MAX_TOTAL_BYTES:raise ValueError("檔案合計不可超過 20 MB。")
    rows=[];sources=[]
    for filename,payload in files:
        if not filename.lower().endswith(".txt"):raise ValueError("僅支援 TXT 檔案。")
        parsed,encoding=parse_uv_text(payload,filename)
        rows.extend(parsed);sources.append({"name":filename,"encoding":encoding,"count":len(parsed)})
    if len(rows)>MAX_ROWS:raise ValueError("資料列合計超過上限。")
    if any(abs(r["wavelength"]-880)>0.00001 for r in rows):raise ValueError("W427 預期 880 nm，請確認是否選錯檔案。")
    rows.sort(key=lambda r:(r["measured_at"],r["source_file"],r["source_line"]))
    groups={};current={};parents={};closing={};warnings=[];seen=set()
    for i,row in enumerate(rows,1):
        name=row["sample_id"].upper();day=row["measured_at"][:10]
        row.update(row_id=i,role="UNKNOWN",batch="",dilution=1.0,base_id="",parent_id="",issues=[])
        signature=tuple(row[k] for k in ("sample_id","measured_at","instrument_conc_text","absorbance_text"))
        if signature in seen:row["issues"].append("疑似重複量測，已保留。")
        seen.add(signature)
        if name=="PFM":row["role"]="PFM"
        elif name=="石英槽比對":row["role"]="CELL_CHECK"
        elif name=="BLANK":row["role"]="INSTRUMENT_BLANK"
        elif re.fullmatch(r"STD\d+",name) or row["type"].upper()=="STANDARD":row["role"]="STANDARD"
        else:
            sample=re.fullmatch(r"([A-Z]\d{11})(?:\*(\d+(?:\.\d+)?))?",name)
            check=re.fullmatch(r"(BK|ICV|CCV|QC|DUP|MSD|MS)(?:[_-](\d+))?(?:\*(\d+(?:\.\d+)?))?",name)
            if sample:row.update(role="SAMPLE",base_id=sample.group(1),dilution=float(sample.group(2) or 1))
            elif check:row.update(role=check.group(1),batch=check.group(2) or "",dilution=float(check.group(3) or 1))
            else:row["issues"].append("名稱待確認；不列為一般樣品。")
        if row["dilution"]<=0 or not __import__('math').isfinite(row["dilution"]):raise ValueError("稀釋倍數必須為有效正數。")
        row["role_label"]=LABELS[row["role"]]
        if row["role"] in {"STANDARD","PFM","CELL_CHECK","INSTRUMENT_BLANK","UNKNOWN"}:continue
        number=current.get(day,"1")
        if row["batch"] and row["batch"]!=number:
            number=row["batch"];parents.pop(day,None)
        current[day]=number;key=(day,int(number));row["batch"]=number
        if key not in groups:
            prior=closing.get(day)
            groups[key]={"date":day,"number":number,"rows":[],"opening":prior,"category":""}
        group=groups[key];group["rows"].append(row)
        if row["role"]=="SAMPLE":parents[day]=row
        elif row["role"] in {"DUP","MS","MSD"}:
            parent=parents.get(day)
            if parent is None:row["issues"].append("同批次尚無原樣品。")
            else:
                row["parent_id"]=parent["sample_id"];row["parent_row_id"]=parent["row_id"]
                if "*" not in name:row["dilution"]=parent["dilution"]
        if row["role"]=="CCV":closing[day]=row
    selected=[];excluded=[]
    for key,group in sorted(groups.items()):
        categories={r["base_id"][0] for r in group["rows"] if r["role"]=="SAMPLE"}
        if len(categories)!=1:
            warnings.append("Batch {} 類別混合或沒有一般樣品，未自動採用。".format(group["number"]))
            excluded.append(group);continue
        group["category"]=next(iter(categories))
        if group["category"]==category:selected.append(group)
        else:excluded.append(group)
    for row in rows:
        warnings.extend(row["sample_id"]+"："+x for x in row["issues"])
    standards=[r for r in rows if r["role"]=="STANDARD"]
    if not standards:warnings.append("尚未匯入檢量線；可重新選取檢量線與樣品檔一起匯入。")
    if len({r["sample_id"].upper() for r in standards})!=len(standards):warnings.append("有重複標準點，未自動選取檢量線。")
    if not selected:warnings.append("沒有符合目前基本資料類別的樣品批次。")
    return {"rows":rows,"sources":sources,"standards":standards,"performance_rows":[r for r in rows if r["role"] in {"PFM","CELL_CHECK"}],
            "batches":selected,"excluded_batches":excluded,"warnings":warnings,
            "sample_count":sum(r["role"]=="SAMPLE" for b in selected for r in b["rows"])}
