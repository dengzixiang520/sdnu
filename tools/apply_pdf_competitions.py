"""把 2024–2025 学年《山东师范大学本科生创新创业学分认定统计表（大学生竞赛）》
的真实数据合并进竞赛库：

1. 235 种 PDF 写法归并到已有竞赛条目，用 PDF 实测的校内获奖等级刷新 awards；
2. 补录 8 个此前不在库里的竞赛（sdnu-071 ~ sdnu-078）；
3. 同步写入 data/ 与 data/demo_baseline/ 两份文件。

映射规则：PDF 原始写法 -> 目录条目名。值为 NEW 表示新增，None 表示跳过（非竞赛条目）。
未在 OVERRIDE 中出现的写法沿用 tools/_pdf_match.json 的自动匹配结果。
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILES = [ROOT / "data/competitions.json", ROOT / "data/demo_baseline/competitions.json"]

SOURCE_NOTE = "校内获奖数为学校学分认定统计实测值"
TOTAL_RECORDS = 608

# ---------------------------------------------------------------------------
# 自动匹配里判错的写法，逐条人工指定
# ---------------------------------------------------------------------------
OVERRIDE: dict[str, str | None] = {
    # —— 新增：PDF 里有、库里没有 ——
    "“招行杯”第十八届全国大学生节能减排社会实践与科技竞赛": "NEW",
    "第十七届全国大学生节能减排社会实践与科技竞赛": "NEW",
    "全国大学生节能减排社会实践与科技竞赛": "NEW",
    "全国大学生市场调查与分析大赛": "NEW",
    "2025外研社“理解当代中国”全国大学生外语能力大赛多语种组决赛": "NEW",
    "“苍穹杯”全国大学生空间信息技术大赛": "NEW",
    "中国大学生程序设计竞赛": "NEW",
    "山东省大学生数学与数学建模竞赛": "NEW",
    "2025年“厚粲杯”全国大学生心理与认知智能测评挑战赛": "NEW",
    "2025年全国大学生心理与行为在线实验精英赛": "NEW",
    # —— 纠正：自动匹配指错了条目 ——
    "中国国际大学生创新创业大赛": "中国国际大学生创新创业大赛",
    "全国大学生高电压与等离子体科技创新竞赛": "全国大学生高电压与等离子体科技创新竞赛",
    "挑战杯中国青年科技创新“揭榜挂帅”擂台赛": "挑战杯中国青年科技创新“揭榜挂帅”擂台赛",
    # —— 跳过：山东省大学生科技节是系列赛事的平台名，不是具体竞赛 ——
    "山东省大学生科技节": None,
    # —— 跳过：Excel 合并单元格导致两个赛事名粘在一行，无法确定归属 ——
    "全国大学生数学建模大赛中国高校计算机大赛-团体程序设计天梯赛（普及赛）": None,
    # —— 纠正：DigitalCup 在库里是独立条目，不应并进「全国大学生数学建模大赛」——
    "“DigitalCup”全国大学生数学建模大赛": '"DigitalCup"全国大学生数学建模大赛',
}

GRADE_RE = re.compile(r"^[a-eA-E]\d$")
GRADE_ORDER = ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3", "D1", "D2", "D3", "E1"]


def grade_rank(key: str) -> tuple[int, str]:
    """按 A1 > A2 > ... > D3 > 校级 > 不入级 排序。"""
    if key in GRADE_ORDER:
        return (GRADE_ORDER.index(key), key)
    return (len(GRADE_ORDER) + (1 if key == "不入级" else 0), key)


def normalize_grade(grade: str) -> str:
    """认定等级统一大写：统计表里混有 c1 这类小写写法。"""
    text = grade.strip()
    return text.upper() if GRADE_RE.match(text) else text

# ---------------------------------------------------------------------------
# 新增条目：PDF 里的级别/类型/获奖等级来自统计表，其余字段按往年规律整理
# ---------------------------------------------------------------------------
NEW_ENTRIES = [
    {
        "id": "sdnu-071",
        "name": "全国大学生节能减排社会实践与科技竞赛",
        "level": "B类",
        "category": "地理与环境",
        "difficulty": "高",
        "teamSize": "3~7",
        "organizer": "全国大学生节能减排社会实践与科技竞赛委员会（教育部高等学校能源动力类专业教学指导委员会指导，历年由不同高校承办）",
        "intro": "围绕「节能减排、绿色能源」主题的全国性学科竞赛，作品分科技类（实物制作、软件设计）与社会实践类两条主线，需提交完整技术报告与实物或方案，决赛为现场布展加答辩。因主题直接对应「双碳」战略，被称作能源动力类学科竞赛的一面旗帜。",
        "highlights": [
            "主题聚焦「双碳」，作品必须算得清节能量与减排量，光有创意拿不到奖",
            "科技类与社会实践类并行，做调研、写报告的队伍同样能参赛",
            "决赛现场布展加答辩，评委多为能源动力、环境领域的教授与企业专家",
            "学校认定为 B 类，国家级奖项在保研与评优中权重较高",
        ],
        "prep": "大二组队定选题（宿舍、食堂、实验室的能耗痛点最容易落地），先用一个月做能耗实测拿到基线数据，再设计装置或方案；报告按「背景—方案—实测—效益」四段写，节能率必须有实测支撑。",
        "skills": [
            "能耗实测与数据采集",
            "热工或流体基础计算",
            "单片机与传感器搭建",
            "技术报告与工程图纸规范",
            "现场布展与答辩",
        ],
        "registration": "每年 11 月—次年 3 月校内选拔，4—5 月提交作品，8 月全国决赛",
        "schedule": "校赛 3—4 月；网评与省赛 5—6 月；全国决赛 8 月",
        "fee": "报名免费；作品制作与差旅一般由学校或学院承担",
        "tracks": [
            "科技类（实物制作）",
            "科技类（软件设计与调研报告）",
            "社会实践类",
            "港澳台及国际赛道",
        ],
        "documents": [
            {"title": "竞赛官方网站", "url": "https://www.jienengjianpai.org/", "kind": "official"},
            {"title": "同济大学承办通知", "url": "https://caup.tongji.edu.cn/d7/fa/c33419a382970/page.htm", "kind": "notice"},
            {"title": "北京石油化工学院组织通知", "url": "https://www.bipt.edu.cn/publish/jwc/tzgg/77aa508d72aa419c8f00af8174ce10bd.htm", "kind": "notice"},
        ],
        "tips": "节能量一定要有实测基线，评委最常追问「跟什么比、省了多少、怎么算出来的」，答不上来直接扣分。",
    },
    {
        "id": "sdnu-072",
        "name": "全国大学生市场调查与分析大赛",
        "level": "B类",
        "category": "经管类",
        "difficulty": "中",
        "teamSize": "3~5",
        "organizer": "中国商业统计学会（教育部高等学校统计学类专业教学指导委员会共同主办）",
        "intro": "国内规模最大的统计调查类学科竞赛，赛程为「个人知识赛网考 → 校赛 → 省赛 → 全国总决赛」，需完成真实抽样调查、数据分析与报告撰写。评审重点在方法的规范性，而不是结论有多惊人。",
        "highlights": [
            "唯一要求先通过个人知识赛（统计学基础网考）才能组队进实践的赛制",
            "选题落地空间大：校园消费、地方产业、社会热点都能做，但抽样方案必须站得住",
            "评审重方法规范性：问卷设计、抽样误差、显著性检验缺一不可",
            "学校认定为 B 类，省级以上奖项对经管、统计、社会学方向升学帮助明显",
        ],
        "prep": "先刷知识赛题库（统计学加市场调查方法），组队后按「问卷与抽样 / 数据分析 / 报告撰写」三人分工；用 SPSS 或 Python 完成描述统计、交叉分析与回归，报告控制在 30 页内。",
        "skills": [
            "问卷设计与预调研",
            "抽样方案与误差控制",
            "SPSS 或 Python 统计分析",
            "图表制作与报告排版",
            "现场答辩",
        ],
        "registration": "每年 9—11 月知识赛报名与网考，12 月—次年 3 月校赛，4—5 月省赛，5—6 月全国总决赛",
        "schedule": "知识赛 10—11 月；校赛 3 月；省赛 4—5 月；全国总决赛 5—6 月",
        "fee": "知识赛报名费约 30 元/人（多数学校统一承担）；后续赛段免费",
        "tracks": ["本科组", "专科组", "研究生组", "在华留学生组"],
        "documents": [
            {"title": "大赛通知（中国商业统计学会）", "url": "http://www.china-cssc.org/show-304-2179-1.html", "kind": "notice"},
            {"title": "中国商业统计学会官网", "url": "http://www.china-cssc.org/", "kind": "official"},
            {"title": "赛氪竞赛平台", "url": "https://www.saikr.com/", "kind": "platform"},
        ],
        "tips": "抽样部分要写清「总体是什么、抽样框怎么来、样本量怎么定的」，这三个问题答不上来直接扣分。",
    },
    {
        "id": "sdnu-073",
        "name": "“外研社·国才杯”“理解当代中国”全国大学生外语能力大赛",
        "level": "B类",
        "category": "语言与文化",
        "difficulty": "中高",
        "teamSize": "1",
        "organizer": "外语教学与研究出版社（外研社）主办，教育部高等学校外国语言文学类专业教学指导委员会指导",
        "intro": "多语种并行的大型外语赛事，含英语、日语、俄语、德语、法语、西班牙语、阿拉伯语、韩语等组别，赛项覆盖演讲、写作、阅读、笔译、口译与国际传播综合能力。2022 年起以「理解当代中国」为主题，强调用外语讲好中国故事。",
        "highlights": [
            "赛项最多、语种最全的外语类赛事，同一个人可以报多个赛项",
            "校赛到省赛再到全国决赛三级推进，校赛门槛低，晋级主要看省赛排名",
            "演讲与口译赛项临场权重高，写作与阅读更看长期积累",
            "学校认定为 B 类，国家级奖项在外语类保研与出国申请中认可度高",
        ],
        "prep": "按赛项提前 2—3 个月准备：演讲写 3 篇不同主题稿并录视频回看；写作每周 2 篇议论文限时训练；口译每天 20 分钟视译加笔记符号体系。多语种组要同步积累时政术语的对应译法。",
        "skills": [
            "即兴演讲与语音语调",
            "议论文结构与限时写作",
            "视译与交替传译笔记",
            "时政与中国文化外译",
            "跨文化表达",
        ],
        "registration": "每年 5—9 月校赛报名（各校自定），9—10 月校赛，11 月省赛，12 月全国决赛",
        "schedule": "校赛 9—10 月；省赛 11 月；全国决赛 12 月",
        "fee": "校赛多由学校组织免费；省赛与国赛报名费约 100—200 元/赛项",
        "tracks": [
            "英语组",
            "日语组",
            "俄语组",
            "德语组",
            "法语组",
            "西班牙语组",
            "阿拉伯语组",
            "韩语组",
        ],
        "documents": [
            {"title": "大赛官方网站", "url": "https://ucc.fltrp.com/", "kind": "official"},
            {"title": "北京物资学院校赛通知", "url": "http://news.bwu.edu.cn/info/1021/89201.htm", "kind": "notice"},
            {"title": "烟台大学校赛通知", "url": "https://xkjs.ytu.edu.cn/info/1046/1682.htm", "kind": "notice"},
        ],
        "tips": "演讲别背稿感太重，评委更看有没有自己的观点；口译宁少不错，卡住就用概括句过渡，硬翻反而扣分更多。",
    },
    {
        "id": "sdnu-074",
        "name": "“苍穹杯”全国大学生空间信息技术大赛",
        "level": "C类",
        "category": "地理与环境",
        "difficulty": "中",
        "teamSize": "1~4",
        "organizer": "苍穹数码技术股份有限公司主办，中国测绘学会指导",
        "intro": "面向全国高校 GIS、遥感、测绘相关专业学生的行业赛事，要求基于国产 GIS 平台 KQGIS 完成空间数据处理、专题制图或应用系统开发，分软件应用与开发、空间分析、遥感应用等方向。题目多取自真实地理场景。",
        "highlights": [
            "全程使用国产 GIS 平台 KQGIS，赛前需要装环境并摸清它与 ArcGIS 的差异",
            "题目来自真实场景：国土空间规划、灾害评估、城市体检等",
            "提交物是「成果数据 + 地图 + 技术报告」，制图规范占分不低",
            "学校认定为 C 类，适合地理、遥感、规划方向积累作品集",
        ],
        "prep": "先用 KQGIS 跟官方教程走一遍完整流程（数据入库、空间分析、专题图输出）；组队后两人做数据处理、一人做制图与报告；提前准备一套配色与图例规范模板，出图效率会高很多。",
        "skills": [
            "KQGIS 与 ArcGIS 空间分析",
            "遥感影像解译",
            "专题制图与版式设计",
            "空间数据建库",
            "技术报告撰写",
        ],
        "registration": "每年 3—5 月报名并开放赛题，6—9 月提交作品，10—11 月评审与答辩",
        "schedule": "报名与培训 4—5 月；作品提交 9 月；评审答辩 10—11 月",
        "fee": "免费，软件授权由主办方提供",
        "tracks": ["软件应用与开发", "空间分析与制图", "遥感应用", "命题赛道"],
        "documents": [
            {"title": "大赛启动通知（苍穹数码）", "url": "https://www.kqgeo.com/About/Info.aspx?nid=-1&pid=41&id=3531", "kind": "notice"},
            {"title": "中国测绘学会", "url": "https://www.csgpc.org/", "kind": "official"},
            {"title": "吉林大学 GIS 系列竞赛组织通知", "url": "http://gest.jlu.edu.cn/info/1037/10775.htm", "kind": "notice"},
        ],
        "tips": "制图务必按地图制图规范来，缺图例、缺比例尺、缺投影说明是最常见的失分点。",
    },
    {
        "id": "sdnu-075",
        "name": "中国大学生程序设计竞赛（CCPC）",
        "level": "B类",
        "category": "计算机与软件",
        "difficulty": "高",
        "teamSize": "3",
        "organizer": "中国大学生程序设计竞赛组委会（教育部高等学校计算机类专业教学指导委员会指导）",
        "intro": "与 ICPC 同规格的国内顶级算法竞赛，三人一队、一台电脑、5 小时，按过题数与罚时排名。赛程含网络预选赛、分站赛与全国总决赛，是国内高校算法竞赛的主战场之一。",
        "highlights": [
            "规则与 ICPC 一致但赛程独立，两条线可以同时打",
            "分站赛按学校名额报名，名额取决于前一年成绩，需要提前争",
            "题目难度梯度明显，多数队伍的现实目标是稳过 3—5 题拿牌",
            "学校认定为 B 类，区域赛奖牌在算法岗简历筛选中权重极高",
        ],
        "prep": "大一按专题刷 300 题（洛谷、Codeforces），大二固定三人队每周一场 5 小时模拟赛，按「读题、主写、对拍」分工；赛后必须复盘每道未过题的卡点并补题。",
        "skills": [
            "C++ 与 STL 标准库",
            "图论与动态规划",
            "数论与计算几何",
            "三人分工与对拍调试",
            "英文题面速读",
        ],
        "registration": "每年 4—6 月网络预选赛，9—12 月各分站赛，次年 3—4 月全国总决赛",
        "schedule": "网络赛 5—6 月；分站赛 9—12 月；全国总决赛次年 3—4 月",
        "fee": "网络赛免费；分站赛报名费约 500—800 元/队，一般由学校承担",
        "tracks": ["网络预选赛", "分站赛（各省与区域）", "女生专场", "全国总决赛"],
        "documents": [
            {"title": "CCPC 官方网站", "url": "https://ccpc.io/", "kind": "official"},
            {"title": "赛事日程与公告", "url": "https://ccpc.io/event", "kind": "notice"},
            {"title": "赛氪竞赛平台", "url": "https://www.saikr.com/", "kind": "platform"},
        ],
        "tips": "罚时按分钟累计，先清简单题再啃难题；提交前一定对拍，一次 WA 就是 20 分钟起步。",
    },
    {
        "id": "sdnu-076",
        "name": "山东省大学生数学与数学建模竞赛",
        "level": "C类",
        "category": "数学与建模",
        "difficulty": "中",
        "teamSize": "1~3",
        "organizer": "山东省科学技术协会、山东省数学会（山东省大学生科技节系列赛事之一）",
        "intro": "山东省大学生科技节下设的省级数学赛事，含数学竞赛（个人笔试，同时作为全国大学生数学竞赛山东赛区）与数学建模竞赛（团队三天一题）两部分，是省内数学类学科竞赛的主要入口。",
        "highlights": [
            "数学竞赛部分同时是全国大学生数学竞赛的山东赛区，一次参赛两个成绩",
            "建模部分赛题偏应用，常结合山东本地产业与黄河流域生态保护",
            "省级奖项是国赛前的低成本练兵，周期短、投入小",
            "学校认定为 C 类，适合作为全国大学生数学建模竞赛的预演",
        ],
        "prep": "数学竞赛按数学分析、高等代数专题刷真题；建模部分提前组队，练熟一篇完整论文的「摘要—假设—模型—求解—检验—评价」结构，把 LaTeX 或 Word 模板排版练成肌肉记忆。",
        "skills": [
            "数学分析与高等代数",
            "MATLAB 或 Python 数值计算",
            "微分方程与优化建模",
            "科技论文写作与排版",
            "三人协作与时间管理",
        ],
        "registration": "数学竞赛每年 9—10 月报名、11 月考试；建模竞赛每年 4—6 月报名",
        "schedule": "数学竞赛 11 月；建模竞赛 5—6 月",
        "fee": "数学竞赛报名费约 100 元/人；建模竞赛约 100—200 元/队",
        "tracks": ["数学竞赛（数学专业组）", "数学竞赛（非数学专业组）", "数学建模竞赛"],
        "documents": [
            {"title": "山东省赛通知（大学生数学竞赛网）", "url": "https://www.cmathc.org.cn/sqtz/487.html", "kind": "notice"},
            {"title": "大学生数学竞赛网", "url": "https://www.cmathc.org.cn/", "kind": "official"},
            {"title": "赛氪报名平台", "url": "https://www.saikr.com/", "kind": "platform"},
        ],
        "tips": "建模论文的摘要是唯一必读部分，必须写清「用了什么模型、得到什么结论、精度多少」，摘要写砸后面全白搭。",
    },
    {
        "id": "sdnu-077",
        "name": "“厚粲杯”全国大学生心理与认知智能测评挑战赛",
        "level": "D类",
        "category": "教育与心理",
        "difficulty": "中",
        "teamSize": "1~3",
        "organizer": "中国心理学会心理测量专业委员会等相关专业委员会（以当年通知为准）",
        "intro": "以张厚粲先生命名的心理与认知测评类赛事，要求围绕认知能力、人格、心理健康等主题设计测评工具或完成实证测评研究，提交量表或实验设计与数据分析报告。",
        "highlights": [
            "核心是测评工具的科学性，信度、效度、常模三件事必须交代清楚",
            "可用现有量表做本土化修订，也可自编题目做预试与项目分析",
            "需要经典测验理论或项目反应理论基础，只做描述统计拿不到高分",
            "学校认定为 D 类，适合心理学、教育学方向练手并积累作品",
        ],
        "prep": "先修心理测量学，掌握 Cronbach's α、探索性与验证性因素分析；组队后按「文献—题目编写—预试—信效度检验—报告」推进，数据分析用 SPSS 加 AMOS，或 R 的 lavaan 包。",
        "skills": [
            "心理测量理论与量表编制",
            "SPSS 与 AMOS",
            "因素分析与信效度检验",
            "实验设计与伦理审查",
            "学术报告写作",
        ],
        "registration": "每年 3—6 月报名，7—9 月提交作品，10 月评审",
        "schedule": "报名 4—6 月；作品提交 9 月；评审 10 月",
        "fee": "一般免费",
        "tracks": ["测评工具开发", "实证测评研究", "认知智能应用"],
        "documents": [
            {"title": "中国心理学会", "url": "https://www.cpsbeijing.org/", "kind": "official"},
        ],
        "tips": "样本量不足是最常见的硬伤，预试至少 200 人、正式施测 500 人以上，结论才站得住。",
    },
    {
        "id": "sdnu-078",
        "name": "全国大学生心理与行为在线实验精英赛",
        "level": "D类",
        "category": "教育与心理",
        "difficulty": "中",
        "teamSize": "1~3",
        "organizer": "中国心理学会相关专业委员会与高校心理学实验教学平台（以当年通知为准）",
        "intro": "依托在线实验平台举办的心理学实验设计与实施赛事，参赛队在平台上完成实验程序搭建、被试招募、数据采集并撰写实验报告，重点考察实验设计的严谨性与在线实验的可复现性。",
        "highlights": [
            "全程在线完成：实验程序、被试招募、数据采集、报告撰写一条链",
            "评审看实验设计的内部效度，控制条件、随机化、盲法是否到位",
            "在线实验必须处理注意力检验与数据剔除规则，且要写进报告",
            "学校认定为 D 类，是心理学实验课内容的实战延伸",
        ],
        "prep": "先学 jsPsych 或 PsychoPy 搭一个完整实验（含指导语、练习、正式试次、问卷），提前设计注意力检验题与剔除标准；数据分析用 R 或 Python 做预处理加混合效应模型。",
        "skills": [
            "jsPsych 或 PsychoPy 实验编程",
            "实验设计与变量控制",
            "在线被试招募与数据清洗",
            "R 或 Python 统计分析",
            "实验报告写作",
        ],
        "registration": "每年 4—6 月报名，7—10 月实验实施与作品提交",
        "schedule": "报名 5—6 月；实验实施 7—9 月；评审 10 月",
        "fee": "一般免费",
        "tracks": ["实验设计赛道", "认知行为赛道", "社会心理赛道"],
        "documents": [
            {"title": "中国心理学会", "url": "https://www.cpsbeijing.org/", "kind": "official"},
        ],
        "tips": "数据剔除标准要事先写死并说明依据，事后挑数据是评审最忌讳的做法。",
    },
]

# 新增条目在统计表里的真实获奖等级
NEW_AWARDS = {
    "sdnu-071": {"不入级": 2, "C3": 1},
    "sdnu-072": {"校级": 1},
    "sdnu-073": {"B3": 1},
    "sdnu-074": {"C3": 1},
    "sdnu-075": {"B2": 1},
    "sdnu-076": {"C2": 1},
    "sdnu-077": {"校级": 2},
    "sdnu-078": {"校级": 2},
}

# 新增条目对应的 PDF 原始写法
NEW_RAW = {
    "sdnu-071": [
        "“招行杯”第十八届全国大学生节能减排社会实践与科技竞赛",
        "第十七届全国大学生节能减排社会实践与科技竞赛",
        "全国大学生节能减排社会实践与科技竞赛",
    ],
    "sdnu-072": ["全国大学生市场调查与分析大赛"],
    "sdnu-073": ["2025外研社“理解当代中国”全国大学生外语能力大赛多语种组决赛"],
    "sdnu-074": ["“苍穹杯”全国大学生空间信息技术大赛"],
    "sdnu-075": ["中国大学生程序设计竞赛"],
    "sdnu-076": ["山东省大学生数学与数学建模竞赛"],
    "sdnu-077": ["2025年“厚粲杯”全国大学生心理与认知智能测评挑战赛"],
    "sdnu-078": ["2025年全国大学生心理与行为在线实验精英赛"],
}


def norm_key(text: str) -> str:
    """归一化：统一弯/直引号，去掉间隔号与空白，用于跨文件名称比对。"""
    out = text
    for a, b in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"), ("•", "·"), ("·", "")):
        out = out.replace(a, b)
    return re.sub(r"\s+", "", out)


def main() -> None:
    pdf = json.loads((ROOT / "tools/_pdf_competitions.json").read_text(encoding="utf-8"))
    by_raw = {e["name"]: e for e in pdf}
    match = json.loads((ROOT / "tools/_pdf_match.json").read_text(encoding="utf-8"))

    cat = json.loads(DATA_FILES[0].read_text(encoding="utf-8"))
    cat_by_key = {norm_key(c["name"]): c for c in cat}

    # 1) 建立 raw -> 目录条目名 的最终映射
    raw_to_canon: dict[str, str] = {}
    for canon, raws in match["matched"].items():
        for raw in raws:
            raw_to_canon[raw] = canon
    for raw, target in OVERRIDE.items():
        if target is None:
            raw_to_canon.pop(raw, None)
        elif target == "NEW":
            raw_to_canon.pop(raw, None)
        else:
            raw_to_canon[raw] = target

    # 2) 按目录条目聚合统计表里的获奖等级
    awards: dict[str, Counter] = defaultdict(Counter)
    colleges: dict[str, set[str]] = defaultdict(set)
    for raw, canon in raw_to_canon.items():
        entry = by_raw.get(raw)
        if not entry:
            continue
        key = norm_key(canon)
        target = cat_by_key.get(key)
        if not target:
            raise SystemExit(f"映射目标不在目录里：{canon}（来自 {raw}）")
        for grade, count in entry["grades"].items():
            awards[target["name"]][normalize_grade(grade) or "校级"] += count
        colleges[target["name"]].update(entry["colleges"].keys())

    # 3) 刷新已有条目的 awards
    updated = 0
    for c in cat:
        new = awards.get(c["name"])
        if not new:
            continue
        c["awards"] = dict(sorted(new.items(), key=lambda kv: grade_rank(kv[0])))
        c["note"] = SOURCE_NOTE
        updated += 1

    # 4) 补录新增条目
    existing_ids = {c["id"] for c in cat}
    existing_names = {c["name"] for c in cat}
    added = 0
    for entry in NEW_ENTRIES:
        if entry["name"] in existing_names:
            continue
        payload = dict(entry)
        payload["awards"] = NEW_AWARDS[payload["id"]]
        payload["note"] = SOURCE_NOTE
        payload["year"] = "2024-2025"
        payload["schoolParticipants"] = "常见参加人数"
        payload["website"] = next(
            (d["url"] for d in payload["documents"] if d["kind"] == "official"), ""
        )
        if payload["id"] not in existing_ids:
            cat.append(payload)
            added += 1

    cat.sort(key=lambda c: c["id"])

    body = json.dumps(cat, ensure_ascii=False, indent=2) + "\n"
    for path in DATA_FILES:
        path.write_text(body, encoding="utf-8")

    total_awards = sum(sum(c["awards"].values()) for c in cat)
    print(f"刷新 awards 的条目：{updated}")
    print(f"新增竞赛：{added}（当前共 {len(cat)} 条）")
    print(f"归并后的校内获奖记录总数：{total_awards}（统计表原始 {TOTAL_RECORDS} 条，跳过非竞赛/歧义行）")
    print(f"已写入：{[str(p.relative_to(ROOT)) for p in DATA_FILES]}")


main()
