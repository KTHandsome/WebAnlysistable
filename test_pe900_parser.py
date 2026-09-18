import parsers.pe900_parser as pe900_parser
from parsers.pe900_parser import parse_pe900_pdf


print("實際載入 Parser：")
print(pe900_parser.__file__)
print()

pdf_path = r"D:\PhyonWeb\test_data\PE900_Test.pdf"

results = parse_pe900_pdf(pdf_path)

print("解析筆數：", len(results))
print()

for row in results:
    print(
        row["sequence_no"],
        repr(row["sample_id"]),
        row["signal"]
    )