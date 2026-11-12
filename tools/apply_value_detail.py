"""把含金量评分、详细简介、适合人群合并进竞赛库。

value 结构：
    score        0-100 综合含金量
    rating       由 score 换算的五档标签
    schoolTier   学校认定类别（A/B/C/D/其他）
    summary      一句话说明为什么值这个分
    uses         这个奖项能用在什么地方
    nationalAwards / provincialAwards / schoolLevelAwards / totalAwards
    rarityNote   用统计表实测获奖数算出的稀缺度说明
"""

import json
from pathlib import Path

from value_data_a import PART_A
from value_data_b import PART_B
from value_data_c import PART_C
from value_data_extra import INTRO_EXTRA

ROOT = Path(__file__).resolve().parent.parent
DATA_FILES = [ROOT / "data/competitions.json", ROOT / "data/demo_baseline/competitions.json"]

CONTENT = {**PART_A, **PART_B, **PART_C}

NATIONAL = {"A1", "A2", "A3", "B1", "B2", "B3", "E1"}
PROVINCE = {"C1", "C2", "C3"}
SCHOOL = {"D1", "D2", "D3", "校级", "不入级"}


def rating_of(score: int) -> str:
    if score >= 88:
        return "极高"
    if score >= 74:
        return "高"
    if score >= 60:
        return "中高"
    if score >= 45:
        return "中"
    return "一般"


def split_awards(awards: dict[str, int]) -> tuple[int, int, int]:
    national = sum(v for k, v in awards.items() if k in NATIONAL)
    province = sum(v for k, v in awards.items() if k in PROVINCE)
    school = sum(v for k, v in awards.items() if k in SCHOOL)
    return national, province, school


def rarity_note(awards: dict[str, int]) -> str:
    national, province, school = split_awards(awards)
    total = national + province + school
    if national >= 10:
        return f"近两届全校国家级认定获奖 {national} 项，是校内产出最集中的赛事之一"
    if national >= 3:
        return f"近两届全校国家级认定获奖 {national} 项、省级 {province} 项，属校内重点突破方向"
    if national >= 1:
        return f"近两届全校国家级认定获奖 {national} 项、省级 {province} 项，能拿到国奖的属少数"
    if province >= 3:
        return f"近两届全校省级认定获奖 {province} 项，国家级尚未突破，属上升期赛事"
    if total >= 1:
        return f"近两届全校认定获奖 {total} 项，参与人数较少，属小众赛道"
    return "近两届暂无校内获奖记录"


def main() -> None:
    cat = json.loads(DATA_FILES[0].read_text(encoding="utf-8"))

    missing = [c["id"] for c in cat if c["id"] not in CONTENT]
    if missing:
        raise SystemExit(f"以下条目缺少含金量内容：{missing}")
    extra = [k for k in CONTENT if k not in {c["id"] for c in cat}]
    if extra:
        raise SystemExit(f"以下内容没有对应条目：{extra}")

    for c in cat:
        payload = CONTENT[c["id"]]
        national, province, school = split_awards(c["awards"])
        c["intro"] = INTRO_EXTRA.get(c["id"], payload["intro"])
        c["audience"] = payload["audience"]
        c["value"] = {
            "score": payload["score"],
            "rating": rating_of(payload["score"]),
            "schoolTier": c["level"],
            "summary": payload["valueSummary"],
            "uses": payload["uses"],
            "nationalAwards": national,
            "provincialAwards": province,
            "schoolLevelAwards": school,
            "totalAwards": national + province + school,
            "rarityNote": rarity_note(c["awards"]),
        }

    body = json.dumps(cat, ensure_ascii=False, indent=2) + "\n"
    for path in DATA_FILES:
        path.write_text(body, encoding="utf-8")

    from collections import Counter

    ratings = Counter(c["value"]["rating"] for c in cat)
    print(f"已更新 {len(cat)} 条")
    print("含金量分布：", dict(ratings))
    print("\n含金量前 12：")
    for c in sorted(cat, key=lambda x: -x["value"]["score"])[:12]:
        print(f"  {c['value']['score']:3d} {c['value']['rating']:2s} [{c['level']}] {c['name']}")
    print("\n含金量后 8：")
    for c in sorted(cat, key=lambda x: x["value"]["score"])[:8]:
        print(f"  {c['value']['score']:3d} {c['value']['rating']:2s} [{c['level']}] {c['name']}")
    print(f"\n已写入：{[str(p.relative_to(ROOT)) for p in DATA_FILES]}")


main()
