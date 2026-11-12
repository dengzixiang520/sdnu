"""Extract every competition row from the SDNU innovation-credit PDF.

产出 tools/_pdf_competitions.json：235 种竞赛写法的级别/类型/奖项/认定等级/学院/日期聚合。
被 tools/_pdf_match.py 和 tools/apply_pdf_competitions.py 作为上游输入。
"""

import json
import re
from collections import Counter, OrderedDict
from pathlib import Path

import pdfplumber

PDF = Path(r"D:\install\qq\chat\2.山东师范大学本科生创新创业学分认定统计表（大学生竞赛） (2).pdf")

HEADER_FIRST = "竞赛名称"
LEVELS = {"国家级", "省级", "校级", "市级", "国家级A类", "省级A类", "校级A类"}
TYPES = {"A类竞赛", "B类竞赛", "C类竞赛", "D类竞赛", "E类竞赛", "非竞赛类"}

rows: list[dict] = []
with pdfplumber.open(PDF) as pdf_doc:
    for pno, page in enumerate(pdf_doc.pages, 1):
        for table in page.extract_tables():
            for raw in table:
                if not raw or not raw[0]:
                    continue
                if raw[0].strip().startswith(HEADER_FIRST):
                    continue
                cells = [(c or "").strip() for c in raw]
                if len(cells) < 7:
                    continue
                name = re.sub(r"\s+", "", cells[0])
                level = re.sub(r"\s+", "", cells[1])
                ctype = re.sub(r"\s+", "", cells[2])
                if level not in LEVELS or ctype not in TYPES:
                    continue
                rows.append({
                    "page": pno,
                    "name": name,
                    "level": level,
                    "type": ctype,
                    "award": re.sub(r"\s+", "", cells[3]),
                    "grade": re.sub(r"\s+", "", cells[4]),
                    "college": re.sub(r"\s+", "", cells[5]),
                    "date": re.sub(r"\s+", "", cells[6]),
                })

agg: "OrderedDict[str, dict]" = OrderedDict()
for r in rows:
    key = r["name"]
    if key not in agg:
        agg[key] = {
            "name": key,
            "levels": Counter(),
            "types": Counter(),
            "awards": Counter(),
            "grades": Counter(),
            "colleges": Counter(),
            "dates": Counter(),
            "rows": 0,
        }
    a = agg[key]
    a["levels"][r["level"]] += 1
    a["types"][r["type"]] += 1
    a["awards"][r["award"]] += 1
    a["grades"][r["grade"]] += 1
    a["colleges"][r["college"]] += 1
    a["dates"][r["date"]] += 1
    a["rows"] += 1

payload = []
for name, a in sorted(agg.items(), key=lambda kv: -kv[1]["rows"]):
    payload.append({
        "name": name,
        "rows": a["rows"],
        "levels": dict(a["levels"].most_common()),
        "types": dict(a["types"].most_common()),
        "awards": dict(a["awards"].most_common()),
        "grades": dict(a["grades"].most_common()),
        "colleges": dict(a["colleges"].most_common(3)),
        "dates": dict(a["dates"].most_common(3)),
    })

out = Path(__file__).resolve().parent / "_pdf_competitions.json"
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"rows={len(rows)} distinct={len(payload)} -> {out}")
