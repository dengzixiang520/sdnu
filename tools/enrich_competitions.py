# -*- coding: utf-8 -*-
"""把补充资料合并进 data/competitions.json（并同步 demo_baseline）。

用法：python tools/enrich_competitions.py
"""

import io
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from comp_data_a import DATA_A  # noqa: E402
from comp_data_b import DATA_B  # noqa: E402

DATA = {**DATA_A, **DATA_B}

TARGETS = [Path("data/competitions.json"), Path("data/demo_baseline/competitions.json")]


def bing(query: str) -> str:
    """把检索词转成可直接点开的搜索链接，保证没有固定官网的条目也有可用入口。"""
    return "https://www.bing.com/search?q=" + urllib.parse.quote(query)


def derive_level(awards: dict) -> str:
    """按获奖记录里最高的奖项前缀推断学校认定的竞赛类别（A 类最高）。"""
    for prefix, label in (("A", "A类"), ("B", "B类"), ("C", "C类"), ("D", "D类")):
        if any(str(key).startswith(prefix) for key in awards or {}):
            return label
    return "其他类"


def build_documents(name: str, website: str) -> list[dict[str, str]]:
    docs: list[dict[str, str]] = []
    if website:
        docs.append({"title": "官方网站 / 报名入口", "url": website, "kind": "official"})
    else:
        docs.append({
            "title": "官方入口检索（官网域名未固定，建议从学校通知进入）",
            "url": bing(f"{name} 官网 报名"),
            "kind": "search",
        })
    docs.append({"title": "历年真题 / 赛题检索", "url": bing(f"{name} 真题 赛题"), "kind": "search"})
    docs.append({"title": "竞赛规程与评分标准", "url": bing(f"{name} 竞赛规程 评分标准"), "kind": "search"})
    docs.append({"title": "备赛经验与培训资料", "url": bing(f"{name} 备赛 经验 培训"), "kind": "search"})
    return docs


def enrich(entry: dict) -> dict:
    extra = DATA.get(entry["id"])
    if not extra:
        return entry
    awards = entry.get("awards") or {}
    merged = dict(entry)
    merged.update({
        "intro": extra["intro"],
        "organizer": extra["organizer"],
        "website": extra["website"],
        "registration": extra["registration"],
        "schedule": extra["schedule"],
        "fee": extra["fee"],
        "tracks": extra["tracks"],
        "skills": extra["skills"],
        "tips": extra["tips"],
        "level": derive_level(awards),
        "documents": build_documents(entry["name"], extra["website"]),
    })
    return merged


def main() -> None:
    for target in TARGETS:
        if not target.exists():
            print(f"skip {target} (not found)")
            continue
        entries = json.loads(target.read_text(encoding="utf-8"))
        before_missing = sum(1 for e in entries if not e.get("organizer"))
        updated = [enrich(e) for e in entries]
        missing = [e["id"] for e in updated if e["id"] not in DATA]
        target.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        after_missing = sum(1 for e in updated if not e.get("organizer"))
        print(f"{target}: {len(updated)} 条，organizer 缺失 {before_missing} -> {after_missing}，未覆盖 {missing}")


if __name__ == "__main__":
    main()
