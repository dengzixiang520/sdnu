"""Verify the merged competition catalogue."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
cat = json.loads((ROOT / "data/competitions.json").read_text(encoding="utf-8"))
base = json.loads((ROOT / "data/demo_baseline/competitions.json").read_text(encoding="utf-8"))
pdf = json.loads((ROOT / "tools/_pdf_competitions.json").read_text(encoding="utf-8"))

REQUIRED = [
    "id", "name", "level", "category", "difficulty", "teamSize", "organizer",
    "intro", "highlights", "prep", "skills", "registration", "schedule", "fee",
    "tracks", "documents", "tips", "awards", "note", "year", "website",
    "schoolParticipants",
]

print("=== 结构校验 ===")
print("条目数:", len(cat), "| demo_baseline 一致:", cat == base)
print("PDF 原始行数:", sum(e["rows"] for e in pdf))

problems = []
for c in cat:
    missing = [k for k in REQUIRED if k not in c]
    if missing:
        problems.append(f"{c['id']} 缺字段 {missing}")
    if not c.get("awards"):
        problems.append(f"{c['id']} awards 为空")
    for d in c.get("documents", []):
        if not str(d.get("url", "")).startswith("http"):
            problems.append(f"{c['id']} 链接异常 {d}")
    if "bing.com" in json.dumps(c, ensure_ascii=False):
        problems.append(f"{c['id']} 含搜索链接")
ids = [c["id"] for c in cat]
if len(ids) != len(set(ids)):
    problems.append("id 重复")
names = [c["name"] for c in cat]
if len(names) != len(set(names)):
    problems.append("name 重复")
print("问题:", problems or "无")

print("\n=== 新增的 8 条 ===")
for c in cat:
    if c["id"] >= "sdnu-071":
        docs = len(c["documents"])
        print(f"{c['id']} [{c['level']}] {c['category']:8s} 难度{c['difficulty']:2s} "
              f"链接{docs} 获奖{json.dumps(c['awards'], ensure_ascii=False)}  {c['name']}")
        print(f"          intro {len(c['intro'])} 字 / highlights {len(c['highlights'])} 条 / "
              f"skills {len(c['skills'])} 项 / tracks {len(c['tracks'])} 个 / prep {len(c['prep'])} 字")

print("\n=== 获奖记录汇总 ===")
total = sum(sum(c["awards"].values()) for c in cat)
print("全部条目获奖记录数:", total)
no_pdf = [c["id"] + " " + c["name"] for c in cat if c.get("note") != "校内获奖数为学校学分认定统计实测值"]
print("未从统计表刷新的条目:", len(no_pdf))
for x in no_pdf:
    print("   ", x)

print("\n=== 等级分布 ===")
from collections import Counter
print("level:", dict(Counter(c["level"] for c in cat)))
print("category:", dict(Counter(c["category"] for c in cat)))
print("award keys:", sorted({k for c in cat for k in c["awards"]}))
