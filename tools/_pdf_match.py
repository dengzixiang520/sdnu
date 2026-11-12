"""Match PDF competition names against the existing canonical catalogue.

产出 tools/_pdf_match.json：{"matched": {目录条目: [PDF原始写法...]}, "unmatched": [...]}
自动匹配只做初筛，人工修正写在 tools/apply_pdf_competitions.py 的 OVERRIDE 里。
"""

import difflib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NOISE = [
    r"^第[一二三四五六七八九十百\d]+届", r"^第\d+届",
    r"^\d{4}年", r"^\d{4}（第\d+届）", r"^\d{4}\(第\d+届\)",
    r"^20\d\d", r"^\d{4}",
    r"[（(][^）)]*赛道[）)]", r"[（(][^）)]*赛区[）)]", r"[（(][^）)]*组[）)]",
    r"[（(][^）)]*杯[）)]", r"[（(][^）)]*赛[）)]",
    r"全国总决赛", r"山东赛区", r"省赛区", r"东赛区",
    r"一等奖", r"二等奖", r"三等奖", r"特等奖", r"金奖", r"银奖", r"铜奖",
    r"国家级", r"省级", r"校级",
    r"[\s·•\.\-—_、，,：:；;“”\"'‘’（）()\[\]【】/]+",
]

ALIASES = {
    "蓝桥杯": "蓝桥杯全国软件和信息技术专业人才大赛",
    "大唐杯": "“大唐杯”全国大学生新一代信息通信技术大赛",
    "睿抗": "睿抗机器人开发者大赛（RAICOM）",
    "RAICOM": "睿抗机器人开发者大赛（RAICOM）",
    "数学建模": "全国大学生数学建模大赛",
    "挑战杯": "“挑战杯”全国大学生课外学术科技作品竞赛",
    "互联网+": "中国国际大学生创新创业大赛",
    "ICPC": "ACM-ICPC国际大学生程序设计竞赛",
    "ACM-ICPC": "ACM-ICPC国际大学生程序设计竞赛",
    "天梯赛": "团体程序设计天梯赛",
    "建行杯": "山东省大学生创新大赛（“建行杯”）",
    "创客大赛": "山东省大学生创客大赛（含“浪曦杯”）",
    "光电": "山东省大学生光电设计科技创新大赛",
    "地理创新": "山东省大学生地理创新大赛",
    "智能车": "全国大学生智能汽车竞赛",
    "智能汽车": "全国大学生智能汽车竞赛",
    "电子设计": "全国大学生电子设计竞赛",
    "华为": "第十届华为ICT大赛",
    "商业精英": "全国高校商业精英挑战赛",
    "新文科": "大学生新文科实践创新大赛",
    "好创意": "中国好创意暨全国数字艺术设计大赛",
    "未来设计师": "未来设计师·全国高校数字艺术设计大赛",
    "米兰设计周": "米兰设计周·中国高校设计学科师生优秀作品展",
    "东方创意之星": "第六届东方创意之星",
    "东方设计奖": "东方设计奖·全国高校创新设计大赛",
    "华韵奖": "华韵奖·全国高校数字创新设计大赛",
    "中装杯": "第十一届“中装杯”全国大学生环境设计大赛",
    "包装创意": "中国包装创意设计大赛",
    "华灿奖": "“两岸新锐设计竞赛·华灿奖”",
    "香港新锐": "第七届香港新锐当代设计奖",
    "数字媒体": "全国大学生数字媒体科技作品及创意竞赛",
    "统计建模": "全国大学生统计建模大赛",
    "能源经济": "全国大学生能源经济学术创意大赛",
    "生命科学": "全国大学生生命科学竞赛",
    "GIS": "全国大学生GIS技能大赛",
    "人力资源": "第十届中国大学生人力资源创新实践大赛",
    "等离子体": "全国高校等离子体大赛",
    "计算机能力": "全国高校计算机能力挑战赛",
    "算法挑战": "大学生算法挑战赛",
    "百度之星": "百度之星程序设计大赛",
    "机器人与算法": "2025年全国大学生机器人与算法大赛",
    "机器人及人工智能": "中国机器人及人工智能大赛",
    "算法精英": "全球校园人工智能算法精英大赛",
    "节能排": "全国大学生节能减排社会实践与科技竞赛",
    "信息安全": "全国大学生信息安全与对抗技术竞赛",
    "英语竞赛": "全国大学生英语竞赛",
    "英语能力": "全国大学生英语竞赛",
    "BETT": "第四届“BETT”杯全国大学生英语词汇大赛",
    "赫尔岑": "2025第五届“相约上合”赫尔岑杯俄语演讲大赛",
    "田家炳": "田家炳杯全国示范院校师范生师范技能竞赛",
    "诗教中国": "中华经典诵写讲大赛“诗教中国”诗词讲解大赛",
    "千村行动": "“千村行动”暑期社会实践专项调查“村庄的故事”主题作品征集",
    "心理": "山东省大学生心理学应用技能大赛",
    "创新创业大赛": "山东师范大学大学生创新创业大赛（含“翰林杯”）",
    "翰林杯": "山东师范大学大学生创新创业大赛（含“翰林杯”）",
    "程序设计竞赛": "山东省大学生程序设计竞赛",
    "物理竞赛": "山东省大学生物理竞赛",
    "物理实验": "全国大学生物理实验竞赛",
    "数学竞赛": "全国大学生数学竞赛",
    "环保创意": "山东省大学生环保创意大赛",
    "乡村环境": "山东省大学生乡村环境与能源应用创新设计大赛",
    "数字工程师": "山东省数字工程师创新创意大赛暨国际数字工程师邀请赛",
    "创新发明": "山东省大学生创新发明大赛",
    "金砖": "一带一路暨金砖国家技能发展与技术创新大赛",
    "揭榜挂帅": "挑战杯中国青年科技创新“揭榜挂帅”擂台赛",
    "电子商务": "全国大学生电子商务“创新、创意及创业”挑战赛",
    "高电压": "全国大学生高电压与等离子体科技创新竞赛",
    "计算机系统能力": "全国大学生计算机系统能力大赛",
    "计算机设计": "中国大学生计算机设计大赛",
    "MathorCup": "MathorCup数学应用挑战赛",
    "DigitalCup": "“DigitalCup”全国大学生数学建模大赛",
    "ShuWei": "ShuWei Cup IMCM",
    "马栏山": "第二届马栏山青年大学生视频文创节",
    "PREMIO": "2025 PREMIO ROCA国际艺术大赛",
    "东方美学": "2025“东方美学”艺术设计作品征集",
}


def normalize(text: str) -> str:
    out = text
    for pat in NOISE:
        out = re.sub(pat, "", out)
    return out.strip()


def main() -> None:
    pdf = json.loads((ROOT / "tools/_pdf_competitions.json").read_text(encoding="utf-8"))
    cat = json.loads((ROOT / "data/competitions.json").read_text(encoding="utf-8"))
    canon = [(c["name"], normalize(c["name"])) for c in cat]
    canon_aliases = dict(ALIASES)

    matched: dict[str, list[str]] = {}
    unmatched: list[dict] = []

    for entry in pdf:
        raw = entry["name"]
        norm = normalize(raw)
        hits: list[str] = []
        for alias, target in canon_aliases.items():
            if alias.lower() in raw.lower():
                hits.append(target)
        for name, cn in canon:
            if cn and (cn in norm or norm in cn) and len(norm) >= 4:
                hits.append(name)
        if not hits:
            best = difflib.get_close_matches(norm, [cn for _, cn in canon], n=1, cutoff=0.62)
            if best:
                hits.append(next(n for n, cn in canon if cn == best[0]))

        if hits:
            matched.setdefault(hits[0], []).append(raw)
        else:
            unmatched.append(entry)

    print(f"PDF 名称 {len(pdf)} 个 → 命中 {len(pdf) - len(unmatched)}，未命中 {len(unmatched)}")
    for u in unmatched:
        print(f"  [{u['rows']:2d}] {'/'.join(u['levels'])} {'/'.join(u['types'])}  {u['name']}")

    out = ROOT / "tools/_pdf_match.json"
    out.write_text(
        json.dumps({"matched": matched, "unmatched": [u["name"] for u in unmatched]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"-> {out}")


main()
