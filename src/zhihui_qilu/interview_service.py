"""沉浸式复试现场：考官名册、提问编排与语音指标评分。

三个职责分得很清：

1. **考官名册**（``EXAMINERS``）—— 三位导师各自的音色、语气指令、座位和职责。
   音色是 Breeze Blue 上真实存在的 voice_id，不是占位符。
2. **提问编排**（``PLANS`` + ``InterviewDirector``）—— 按复试时长给出固定的提问节奏
   （自我介绍 → 专业基础 → 项目追问 → 英语 → 读研规划 → 压力追问 → 收尾），
   每一步都有兜底题目。大模型可用时只负责"把这一问说得更自然"，
   不可用时整场照样能跑完，不会在答辩现场卡住。
3. **语音指标评分**（``build_report``）—— 语速、停顿、填充词、音量、开口延迟
   全部由前端实测后上传，这里只做确定性的换算与打分，不臆造数据。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from zhihui_qilu.ai.provider import ChatMessage, LanguageModelProvider, ProviderUnavailableError

# --------------------------------------------------------------------------- 名册

EXAMINERS: tuple[dict[str, Any], ...] = (
    {
        "id": "host",
        "name": "陈立群",
        "title": "复试组长 · 教授",
        "role": "开场主持与综合判断",
        "duty": "动机、规划、整体印象",
        "voice_id": "voc_wuwu3ckdfe4q",
        "voice_name": "云端播报员",
        "voice_style": "沉稳、略偏低的男声，语速稍慢，语气平和而有权威感，像高校研究生复试现场的主考官",
        "speed": 0.94,
        "color": "#3f6f9e",
        "seat": -1,
    },
    {
        "id": "major",
        "name": "周敏行",
        "title": "专业面试官 · 副教授",
        "role": "专业深度追问",
        "duty": "基础概念、项目细节、方法边界",
        "voice_id": "voc_reys5un5t4ed",
        "voice_name": "深思先生",
        "voice_style": "偏低、温和清楚的成年男声，语速平稳，问句收尾干脆，像在认真核对细节的副教授",
        "speed": 1.0,
        "color": "#4a7c59",
        "seat": 0,
    },
    {
        "id": "english",
        "name": "苏静宜",
        "title": "综合素质考官 · 副教授",
        "role": "英语与抗压测试",
        "duty": "英语表达、临场反应、情绪稳定",
        "voice_id": "voc_b86bfwct4cjn",
        "voice_name": "香农小姐",
        "voice_style": "清冷疏离、清晰克制的年轻女声，语气平静不带情绪，像严格但公正的考官",
        "speed": 1.0,
        "color": "#8a5a7a",
        "seat": 1,
    },
)

EXAMINER_INDEX: dict[str, dict[str, Any]] = {item["id"]: item for item in EXAMINERS}


# --------------------------------------------------------------------------- 编排


@dataclass(frozen=True, slots=True)
class Stage:
    """复试节奏里的一步。``fallback`` 保证没有大模型时也能问出像样的问题。"""

    examiner: str
    intent: str
    fallback: str
    language: str = "zh"
    hard: bool = False


_PLAN_COMMON: tuple[Stage, ...] = (
    Stage("host", "开场与自我介绍", "先请你用一到两分钟做个自我介绍，重点讲清楚你的专业背景，以及为什么想读这个方向。"),
    Stage("major", "专业基础概念", "挑一个你最有把握的专业核心概念，讲清楚它的定义，再说明它在什么情况下会失效。"),
    Stage("major", "项目或科研经历", "讲一个你真正动手做过的项目。你负责哪一部分，怎么验证你的方案确实有效？"),
    Stage("english", "英语表达", "Please introduce your research interest in English, and explain why it matters to you.", "en"),
    Stage("host", "读研动机与规划", "如果今年顺利入学，你打算怎么安排前两年的学习和研究？"),
    Stage("major", "质疑与证据", "假设我现在质疑你的实验结论站不住脚，你会怎么回应？请给出具体的验证路径。", "zh", True),
    Stage("english", "英语追问与抗压", "What would you do if your first research approach failed completely?", "en", True),
    Stage("host", "收尾", "最后，你有什么想问我们的吗？可以问一个你最关心的问题。"),
)

_PLAN_SHORT: tuple[Stage, ...] = (
    _PLAN_COMMON[0],
    _PLAN_COMMON[1],
    _PLAN_COMMON[2],
    _PLAN_COMMON[4],
    _PLAN_COMMON[7],
)

_PLAN_LONG: tuple[Stage, ...] = (
    _PLAN_COMMON[0],
    _PLAN_COMMON[1],
    Stage("major", "专业课基础", "说一门你学得最好的专业课，它最核心的一条结论是什么，为什么成立。"),
    _PLAN_COMMON[2],
    Stage("major", "方法与工具", "你常用的工具或框架里，有一个你最不放心的地方是什么？你怎么规避它的风险？"),
    _PLAN_COMMON[3],
    _PLAN_COMMON[4],
    Stage("host", "学术诚信与协作", "如果合作者的数据和你的复现结果对不上，你会怎么处理？"),
    _PLAN_COMMON[5],
    _PLAN_COMMON[6],
    Stage("english", "英语规划", "Where do you see yourself in five years, and how does this program fit that plan?", "en"),
    _PLAN_COMMON[7],
)

PLANS: dict[int, tuple[Stage, ...]] = {5: _PLAN_SHORT, 15: _PLAN_COMMON, 30: _PLAN_LONG}

GREETINGS: dict[str, str] = {
    "host": "同学你好，请坐。这里是山东师范大学人工智能专业硕士研究生复试现场，我是本次复试的组长陈立群。今天大概用{n}分钟，我们三位老师会和你聊几个问题，你按自己的思路回答就好，不用紧张。",
    "major": "我是周敏行，负责今天的专业部分。我会问得细一些，你尽量讲清楚你自己的想法。",
    "english": "我是苏静宜，接下来会有一部分问题用英语提问，你可以用英语回答。",
}


def plan_for(minutes: int) -> tuple[Stage, ...]:
    """按时长取最近的提问计划，避免出现空计划。"""
    if minutes in PLANS:
        return PLANS[minutes]
    if minutes <= 8:
        return _PLAN_SHORT
    if minutes <= 20:
        return _PLAN_COMMON
    return _PLAN_LONG


def examiner_public(item: dict[str, Any]) -> dict[str, Any]:
    """只暴露前端需要的字段，voice_id 也给出（前端仅用于展示音色名）。"""
    return {
        "id": item["id"],
        "name": item["name"],
        "title": item["title"],
        "role": item["role"],
        "duty": item["duty"],
        "voice_name": item["voice_name"],
        "color": item["color"],
        "seat": item["seat"],
    }


def speech_profile(examiner_id: str, text: str, language: str) -> dict[str, Any]:
    """给 ``SpeechRequest`` 用的合成参数。"""
    item = EXAMINER_INDEX.get(examiner_id, EXAMINERS[0])
    return {
        "voice_id": item["voice_id"],
        "instructions": item["voice_style"],
        "speed": float(item["speed"]),
        "language": language,
    }


# --------------------------------------------------------------------------- 导演


class TurnRequest(BaseModel):
    """请求下一问。"""

    major: str = Field(default="人工智能", max_length=40)
    minutes: int = Field(default=15, ge=5, le=30)
    strictness: str = Field(default="常规", max_length=12)
    step: int = Field(default=0, ge=0, le=40)
    history: list[dict[str, str]] = Field(default_factory=list)


class TurnResponse(BaseModel):
    """一位考官的一次提问。"""

    step: int
    total: int
    examiner: str
    examiner_name: str
    examiner_title: str
    intent: str
    language: str
    hard: bool
    question: str
    closing: bool = False
    generated_by: str = "plan"


_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


class InterviewDirector:
    """把"固定节奏 + 自然措辞"拼起来。大模型只润色措辞，不改变节奏。"""

    def __init__(self, provider: LanguageModelProvider) -> None:
        self._provider = provider

    def plan(self, minutes: int) -> tuple[Stage, ...]:
        return plan_for(minutes)

    async def next_turn(self, request: TurnRequest) -> TurnResponse:
        stages = self.plan(request.minutes)
        step = min(request.step, len(stages) - 1)
        stage = stages[step]
        examiner = EXAMINER_INDEX[stage.examiner]
        question = stage.fallback
        generated = "plan"

        if self._provider.available:
            polished = await self._polish(request, stage, examiner)
            if polished:
                question, generated = polished, "model"

        return TurnResponse(
            step=step,
            total=len(stages),
            examiner=stage.examiner,
            examiner_name=examiner["name"],
            examiner_title=examiner["title"],
            intent=stage.intent,
            language=stage.language,
            hard=stage.hard,
            question=question,
            closing=step == len(stages) - 1,
            generated_by=generated,
        )

    async def _polish(self, request: TurnRequest, stage: Stage, examiner: dict[str, Any]) -> str | None:
        """让考官把兜底题目说得更自然；任何异常都回落到兜底题目。

        这里刻意把"已经问过什么"写进提示词：大模型很容易在考生答不上来的时候
        反复问同一个方向（实测出现过连续两题都在问读研规划），必须显式禁止。
        """
        recent = request.history[-8:]
        transcript = "\n".join(
            f"{'考生' if item.get('role') == 'user' else item.get('speaker', '考官')}：{item.get('content', '')[:300]}"
            for item in recent
        ) or "（还没有对话，这是第一步）"
        asked = [item.get("content", "") for item in request.history if item.get("role") == "assistant"]
        asked_text = "\n".join(f"- {text[:120]}" for text in asked[-8:]) or "（无）"
        strict = {
            "鼓励": "语气温和，先肯定再提问。",
            "常规": "语气中性，按研究生复试的常规深度提问。",
            "严格追问": "语气克制偏冷，问题要直指证据和边界。",
        }.get(request.strictness, "语气中性。")
        closing = stage is self.plan(request.minutes)[-1]
        system = (
            f"你在扮演研究生复试现场的考官{examiner['name']}（{examiner['title']}），"
            f"负责「{examiner['role']}」，考察点是「{examiner['duty']}」。"
            f"目标专业：{request.major}。{strict}"
            "只输出一个 JSON 对象，形如 {\"question\": \"...\"}，不要任何解释、不要 Markdown。"
        )
        rules = [
            f"本步唯一考察点是「{stage.intent}」，问题必须服务这个考察点。",
            f"参考问法是：「{stage.fallback}」，可以改写但不能换成别的考察点。",
            "绝对不要重复或改写下面已经问过的问题，也不要继续追问同一方向：",
            asked_text,
            "考生没答上来的题可以换个角度重问，但必须换考察角度，不能只是换措辞。",
        ]
        if closing:
            rules.append("这是本场最后一问，必须收束整场，例如请考生提问、或请考生用一句话总结今天的表现。不要再开新话题。")
        rules.append("必须用英文提问。" if stage.language == "en" else "用中文提问。")
        rules.append("中文不超过 90 字，英文不超过 45 词，只问一个问题。")
        user = "\n".join(rules) + f"\n\n已有对话：\n{transcript}"
        try:
            raw = await self._provider.complete(
                [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)],
                temperature=0.8,
            )
        except ProviderUnavailableError:
            return None
        match = _JSON_BLOCK.search(raw)
        if match:
            try:
                data = json.loads(match.group(0))
                text = str(data.get("question", "")).strip()
                if 4 <= len(text) <= 400:
                    return text
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        cleaned = raw.strip().strip('"“”')
        if 4 <= len(cleaned) <= 400 and "\n" not in cleaned:
            return cleaned
        return None


# --------------------------------------------------------------------------- 报告


class AnswerMetric(BaseModel):
    """前端实测的一题语音指标。缺项按 0 处理，不做猜测。"""

    index: int = 0
    examiner: str = "host"
    question: str = ""
    transcript: str = ""
    duration_ms: int = Field(default=0, ge=0, le=3_600_000)
    speech_ms: int = Field(default=0, ge=0, le=3_600_000)
    latency_ms: int = Field(default=0, ge=0, le=600_000)
    pause_count: int = Field(default=0, ge=0, le=10_000)
    longest_pause_ms: int = Field(default=0, ge=0, le=600_000)
    avg_volume: float = Field(default=0.0, ge=0.0, le=1.0)
    volume_stability: float = Field(default=0.0, ge=0.0, le=1.0)
    filler_count: int = Field(default=0, ge=0, le=10_000)
    chars: int = Field(default=0, ge=0, le=100_000)
    syllables: int = Field(default=0, ge=0, le=100_000)
    hard: bool = False


class ReportRequest(BaseModel):
    """整场复试的原始数据。"""

    major: str = Field(default="人工智能", max_length=40)
    minutes: int = Field(default=15, ge=5, le=30)
    strictness: str = Field(default="常规", max_length=12)
    answers: list[AnswerMetric] = Field(default_factory=list)


class Dimension(BaseModel):
    key: str
    label: str
    score: int
    evidence: str
    advice: str


class SpeechSummary(BaseModel):
    total_seconds: int
    speech_seconds: int
    speech_ratio: int
    chars_per_min: int
    pause_count: int
    longest_pause_ms: int
    latency_ms: int
    filler_total: int
    filler_rate: int
    avg_volume: int
    volume_stability: int
    answered: int
    # 语速的来源：transcript = 有语音转写文本；estimate = 按音量包络音节峰估算；none = 都没测到
    pace_source: str = "none"


class AnswerReview(BaseModel):
    index: int
    examiner_name: str
    question: str
    transcript: str
    seconds: int
    chars_per_min: int
    pause_count: int
    longest_pause_ms: int
    latency_ms: int
    filler_count: int
    verdict: str


class InterviewReport(BaseModel):
    overall: int
    grade: str
    headline: str
    dimensions: list[Dimension]
    speech: SpeechSummary
    answers: list[AnswerReview]
    highlights: list[str]
    fixes: list[str]


_FILLERS = ("嗯", "呃", "那个", "就是", "然后", "这个", "反正", "其实吧")


def _pace_score(cpm: int) -> int:
    """中文面试的舒适语速区间是 190–270 字/分，偏离越多扣分越狠。

    偏慢比偏快更常见（紧张时会逐字往外挤），所以下坡比上坡缓一点，
    但下限都压在 45 分，避免一项把总分拖死。
    """
    if cpm <= 0:
        return 25
    if 190 <= cpm <= 270:
        return 96
    if cpm < 190:
        return max(45, round(96 - (190 - cpm) * 0.7))
    return max(40, round(96 - (cpm - 270) * 0.5))


def _pause_score(pause_per_min: float, longest_ms: int) -> int:
    """每分钟 5–14 次短停顿是正常思考；超过 2.5 秒的长停顿会被读成卡壳。"""
    if pause_per_min <= 0:
        base = 62
    elif pause_per_min <= 4:
        base = 78
    elif pause_per_min <= 14:
        base = 96
    elif pause_per_min <= 22:
        base = 82
    else:
        base = 66
    if longest_ms > 6000:
        base -= 26
    elif longest_ms > 3500:
        base -= 14
    elif longest_ms > 2500:
        base -= 6
    return max(30, base)


def _fluency_score(filler_rate: int) -> int:
    """填充词按"每百字几个"计，0 个接近满分。"""
    return max(28, 96 - filler_rate * 11)


def _presence_score(avg_volume: int, stability: int) -> int:
    """音量太小显得没底气，忽大忽小显得不稳。

    注意：前端开了 autoGainControl，这里的 avg_volume 是"经自动增益后的相对音量"，
    不再等于真实声压。所以阈值放得比纯物理测量更宽，主要看稳定性。
    """
    if avg_volume <= 0:
        return 55
    if avg_volume < 6:
        base = 68
    elif avg_volume < 14:
        base = 84
    elif avg_volume <= 60:
        base = 96
    else:
        base = 88
    return max(40, round(base * 0.62 + stability * 0.38))


def _composure_score(latency_ms: int, longest_ms: int, hard: bool) -> int:
    """开口延迟 0.6–3 秒是从容思考；压力题上允许更长的组织时间。"""
    if latency_ms <= 0:
        base = 70
    elif latency_ms < 600:
        base = 80
    elif latency_ms <= 3000:
        base = 96
    elif latency_ms <= 6000:
        base = 84
    else:
        base = 68
    if hard and longest_ms > 4000:
        base -= 10
    return max(30, base)


def _content_score(answer: AnswerMetric) -> int:
    """内容分只用可复核的信号：说了多少、有没有结构词、有没有专业词。"""
    text = answer.transcript.strip()
    if not text:
        return 20
    length = min(38, len(text) // 8)
    structure = len(re.findall(r"首先|其次|然后|最后|因为|所以|因此|第一|第二|一方面|另一方面", text))
    technical = len(re.findall(r"模型|算法|数据|实验|方法|指标|框架|验证|收敛|特征|样本|评测|baseline", text, re.IGNORECASE))
    english = len(re.findall(r"[A-Za-z]{4,}", text))
    score = 34 + length + min(20, structure * 5) + min(20, technical * 4) + min(8, english)
    return max(25, min(97, score))


def build_report(request: ReportRequest) -> InterviewReport:
    """把实测指标换算成五维评分；每一项都附可追溯的证据句。"""
    answers = request.answers
    answered = [item for item in answers if item.transcript.strip()]
    total_ms = sum(item.duration_ms for item in answers)
    speech_ms = sum(item.speech_ms for item in answers)
    chars = sum(item.chars for item in answers)
    syllables = sum(item.syllables for item in answers)
    pause_total = sum(item.pause_count for item in answers)
    filler_total = sum(item.filler_count for item in answers)
    longest = max((item.longest_pause_ms for item in answers), default=0)
    latency = round(sum(item.latency_ms for item in answers) / len(answers)) if answers else 0
    avg_volume = round(100 * (sum(item.avg_volume for item in answers) / len(answers))) if answers else 0
    stability = round(100 * (sum(item.volume_stability for item in answers) / len(answers))) if answers else 0
    # 语速优先用转写文本；没有文本时退回音量包络的音节峰估算，并在报告里标明来源。
    # 估算路径必须做合理性检查：纯音调、风扇噪声、键盘声都会让峰数虚高，
    # 实测过一段 4 秒的合成音被算成 686 字/分，所以样本太少或数值离谱时直接判为"没测到"。
    if chars > 0:
        pace_units, pace_source = chars, "transcript"
    elif syllables >= 20 and speech_ms >= 3000:
        pace_units, pace_source = syllables, "estimate"
    else:
        pace_units, pace_source = 0, "none"
    cpm = round(pace_units / (speech_ms / 60_000)) if speech_ms > 0 else 0
    if pace_source == "estimate":
        cpm = max(60, min(480, cpm))
    pause_per_min = pause_total / (total_ms / 60_000) if total_ms > 0 else 0.0
    filler_rate = round(100 * filler_total / chars) if chars > 0 else 0

    pace = _pace_score(cpm)
    pause = _pause_score(pause_per_min, longest)
    fluency = _fluency_score(filler_rate)
    presence = _presence_score(avg_volume, stability)
    composure = _composure_score(latency, longest, any(item.hard for item in answers))
    has_text = chars > 0
    content = round(sum(_content_score(item) for item in answers) / len(answers)) if has_text and answers else 60

    dimensions = [
        Dimension(
            key="pace",
            label="语速节奏",
            score=pace,
            evidence=(
                f"实测 {cpm} 字/分，有效说话 {round(speech_ms / 1000)} 秒、共 {chars} 字。"
                if pace_source == "transcript"
                else f"未获得语音转写文本，按音量包络的音节峰估算约 {cpm} 字/分（有效说话 {round(speech_ms / 1000)} 秒）。"
                if pace_source == "estimate"
                else f"本题没有测到有效人声，仅记录到 {round(speech_ms / 1000)} 秒发声。"
            ),
            advice="中文面试的舒适区间是 190–270 字/分。偏快就把每句话的句末停顿拉长半拍，偏慢就用短句推进。"
            if not 190 <= cpm <= 270
            else "语速落在舒适区间，保持这个节奏，重点句子前留半拍停顿会更稳。",
        ),
        Dimension(
            key="pause",
            label="停顿控制",
            score=pause,
            evidence=f"共 {pause_total} 次超过 0.8 秒的停顿，平均每分钟 {pause_per_min:.1f} 次，最长 {round(longest / 1000, 1)} 秒。",
            advice="长停顿超过 2.5 秒会被听成卡壳。想不起下一句时，用「这一点我想分两层说」顶住，再展开。"
            if longest > 2500
            else "停顿分布正常，说明你在边想边说。可以再主动用停顿强调结论。",
        ),
        Dimension(
            key="fluency",
            label="表达干净度",
            score=fluency,
            evidence=f"识别到 {filler_total} 处口头填充词，每百字 {filler_rate} 处。",
            advice="把「嗯、那个、就是」换成一次深呼吸或半秒静默，听感会立刻变专业。"
            if filler_rate >= 2
            else "几乎没有口头填充词，表达干净。",
        ),
        Dimension(
            key="presence",
            label="音量与气场",
            score=presence,
            evidence=f"平均音量 {avg_volume}/100，音量稳定性 {stability}/100。",
            advice="音量偏小或波动大时，先做一次腹式吸气再开口，句尾不要泄气。"
            if avg_volume < 18 or stability < 55
            else "音量充足且稳定，镜头前的气场是够的。",
        ),
        Dimension(
            key="composure",
            label="临场应变",
            score=composure,
            evidence=f"平均开口延迟 {round(latency / 1000, 1)} 秒。",
            advice="被追问时先复述问题再回答，用「我理解您问的是…」争取两秒组织时间。"
            if latency > 3000
            else "开口反应自然，没有明显的空白期。",
        ),
        Dimension(
            key="content",
            label="内容密度",
            score=content,
            evidence=(
                f"{len(answered)} 题有有效回答，平均每题 {round(chars / max(1, len(answered)))} 字。"
                if has_text
                else "未获得语音转写文本，内容密度无法评估，本项不计入总分。"
            ),
            advice="每题用「结论—依据—边界」三段式，避免只讲过程不讲判断。"
            if content < 70
            else "内容结构清楚，继续保持证据先行的习惯。",
        ),
    ]

    weights = {"pace": 0.14, "pause": 0.14, "fluency": 0.16, "presence": 0.14, "composure": 0.16, "content": 0.26}
    # 没有转写文本时把内容项剔除后重新归一化，避免"没测到"被当成"答得差"
    effective = {key: value for key, value in weights.items() if key != "content" or has_text}
    total_weight = sum(effective.values())
    overall = round(sum(item.score * effective[item.key] for item in dimensions if item.key in effective) / total_weight)
    overall = max(0, min(100, overall))
    if not has_text:
        # 没有转写文本时内容分是缺席而不是满分，总分要相应压住，
        # 否则会给出一个"语音很漂亮但根本没评估内容"的虚高分。
        overall = min(overall, 84)
    grade = "A" if overall >= 85 else "B+" if overall >= 78 else "B" if overall >= 70 else "C+" if overall >= 62 else "C"
    if not has_text:
        headline = "语音表现已经测到了，但这场没有拿到转写文本，内容分未参与评估。建议先确认浏览器语音识别可用，再练一次。"
    else:
        headline = {
            "A": "这场可以直接上真实复试现场。",
            "B+": "整体稳，把最弱的一项补上就能进第一梯队。",
            "B": "基础表达过关，需要针对追问再练一轮。",
            "C+": "有明显短板，先解决语速与停顿，再练内容。",
            "C": "建议先做一轮逐题复述练习，把回答结构固定下来。",
        }[grade]

    reviews: list[AnswerReview] = []
    for item in answers:
        examiner = EXAMINER_INDEX.get(item.examiner, EXAMINERS[0])
        units = item.chars or item.syllables
        item_cpm = round(units / (item.speech_ms / 60_000)) if item.speech_ms > 0 and units else 0
        score = round(
            (
                _pace_score(item_cpm)
                + _pause_score(item.pause_count / max(0.01, item.duration_ms / 60_000), item.longest_pause_ms)
                + _fluency_score(round(100 * item.filler_count / item.chars) if item.chars else 0)
                + _content_score(item)
            )
            / 4
        )
        verdict = "好" if score >= 82 else "稳" if score >= 70 else "需加强"
        reviews.append(
            AnswerReview(
                index=item.index,
                examiner_name=examiner["name"],
                question=item.question,
                transcript=item.transcript,
                seconds=round(item.duration_ms / 1000),
                chars_per_min=item_cpm,
                pause_count=item.pause_count,
                longest_pause_ms=item.longest_pause_ms,
                latency_ms=item.latency_ms,
                filler_count=item.filler_count,
                verdict=verdict,
            )
        )

    ordered = sorted(dimensions, key=lambda item: item.score)
    highlights = [f"{item.label} {item.score} 分：{item.evidence}" for item in ordered[-2:][::-1]]
    fixes = [f"{item.label}（{item.score} 分）：{item.advice}" for item in ordered[:2]]

    return InterviewReport(
        overall=overall,
        grade=grade,
        headline=headline,
        dimensions=dimensions,
        speech=SpeechSummary(
            total_seconds=round(total_ms / 1000),
            speech_seconds=round(speech_ms / 1000),
            speech_ratio=round(100 * speech_ms / total_ms) if total_ms else 0,
            chars_per_min=cpm,
            pause_count=pause_total,
            longest_pause_ms=longest,
            latency_ms=latency,
            filler_total=filler_total,
            filler_rate=filler_rate,
            avg_volume=avg_volume,
            volume_stability=stability,
            answered=len(answered),
            pace_source=pace_source,
        ),
        answers=reviews,
        highlights=highlights,
        fixes=fixes,
    )
