"""Convert the saved E215 inputs to a formal record without a calibration curve."""
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

TABLE_51, TABLE_97 = json.loads(Path(__file__).with_name("e215_mpn.json").read_text(encoding="utf-8"))


def number(text, maximum):
    if not re.fullmatch(r"[0-9]+", text) or not 0 <= int(text) <= maximum:
        raise ValueError("陽性孔數未填或超過定量盤範圍。")
    return int(text)


def result(raw, factor):
    symbol = raw[0] if raw[0] in "<>" else ""
    adjusted = Decimal(raw[len(symbol):]) * int(factor)
    if adjusted < 100:
        report = str(adjusted.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    else:
        places = adjusted.adjusted() - 1
        rounded = adjusted.quantize(Decimal(1).scaleb(places), rounding=ROUND_HALF_UP)
        exponent = rounded.adjusted()
        report = format(rounded.scaleb(-exponent), ".1f") + "E+" + str(exponent)
    return symbol + format(adjusted.normalize(), "f"), symbol + report


def formal_state(state, exam_no):
    data = state["data"]
    names = {r["sid"]: r["number"] for r in state["lookup"]["rows"]}
    dual = exam_no in ("W-E21502", "D-E21502", "G-E21502")
    batches, samples = [], []
    for index, batch in enumerate(data["batches"]):
        if not all(v.strip() for v in batch["fields"]):
            raise ValueError("請填完整批次資料。")
        ids = [None] + data["samples"][index*10:index*10+10]
        detail = []
        for sid, row in zip(ids, batch["rows"]):
            name = names[sid] if sid is not None else "實驗室空白"
            tray = row["tray"]
            if not tray or (sid is not None and not row["time"]):
                raise ValueError(name + "：請填定量盤與採樣時間（空白不需採樣時間）。")
            lines, selected, factors = [], [], set()
            for line in row["lines"]:
                if not any(line["counts"]) and not line["selected"] and not line["factor"]:
                    continue
                factor = line["factor"]
                if not factor or factor in factors:
                    raise ValueError(name + "：請選擇倍數，且不得重複。")
                factors.add(factor)
                outputs = []
                for k, analyte in enumerate(("Coliform", "E. coli") if dual else ("Coliform",)):
                    try:
                        count = number(line["counts"][2*k], 51 if tray == "51" else 49)
                        small = number(line["counts"][2*k+1], 48) if tray == "97" else None
                    except ValueError as exc:
                        raise ValueError(name + "：" + str(exc)) from exc
                    raw = TABLE_51[count] if tray == "51" else TABLE_97[count][small]
                    adjusted, report = result(raw, factor)
                    outputs.append(dict(analyte=analyte, adjusted=adjusted, report=report))
                entry = dict(line, outputs=outputs)
                lines.append(entry)
                if line["selected"]:
                    selected.append(entry)
            if len(selected) != 1:
                raise ValueError(name + "：請選取一個報告倍數。")
            report_line = selected[0]
            detail.append(dict(row, sample_id=name, lines=lines))
            target = report_line["outputs"][-1]["report"]
            samples.append(dict(sample_id=name, role="BLANK" if sid is None else "SAMPLE",
                dilution_factor=int(report_line["factor"]), remark=target + " MPN/100 mL"))
        batches.append(dict(fields=batch["fields"], rows=detail))
    return dict(state, e215_batches=batches, sample_qaqc_rows=samples)
