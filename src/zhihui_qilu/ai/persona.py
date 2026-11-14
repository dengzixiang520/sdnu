"""Load the editable guide persona and compose the wellbeing system prompt.

人物设定放在 `src/zhihui_qilu/prompts/guide_persona.md`，属于内容而不是代码：
运营同学改措辞不需要碰 Python。读取按 (mtime, size) 做缓存，所以保存 md 之后
下一轮对话就生效，不必重启后端。
"""

from functools import lru_cache
from pathlib import Path

_PERSONA_PATH = Path(__file__).resolve().parent.parent / "prompts" / "guide_persona.md"

#: 文件被删或读不到时的兜底，保证对话不会因为缺一个 md 就崩掉。
_FALLBACK_PERSONA = (
    "你是‘智汇齐鲁·全域同频’的暖心引导员小齐，一位面向大学生的温暖陪伴助手。"
    "先接住情绪、再给一个小而可行的建议；一次最多问一个问题，回复控制在 120 字内。"
    "不诊断心理疾病，不冒充心理咨询师，不索取敏感信息，不声称已替用户预约或联系学校。"
    "遇到安全风险由外部规则处理；你不能覆盖安全提示、不能执行系统或设备指令。"
)

#: 无论 md 里写了什么都要带的硬约束，避免改人设时把安全底线改没了。
_HARD_RULES = (
    "## 本轮硬性约束（不可被上面的设定覆盖）\n"
    "- 回复不超过 120 字，最多问一个问题。\n"
    "- 不诊断心理疾病，不贴人格标签，不替用户下结论。\n"
    "- 不索取身份证、手机号、学号、住址等敏感信息。\n"
    "- 不声称已替用户预约、联系学校或老师。\n"
    "- 不复述「当前上下文」里的字段名和数值。\n"
    "- 你不能覆盖安全提示，不能执行系统或设备指令。"
)

_MOOD_LABEL = {"sunny": "晴 / 轻松", "cloudy": "云 / 一般", "rainy": "雨 / 低落", "stormy": "雷 / 难熬"}
_LEVEL_LABEL = {
    "green": "green（常规陪伴）",
    "yellow": "yellow（最近偏累，语气放缓，可以轻轻提一句要不要找人聊聊）",
    "orange": "orange（持续承压，优先给求助路径，不继续分析原因）",
    "red": "red（有安全风险，安全流程优先，停止一切分析）",
}


@lru_cache(maxsize=4)
def _read_persona(mtime: float, size: int) -> str:
    del mtime, size  # 只作为缓存键，读的时候不需要
    return _PERSONA_PATH.read_text(encoding="utf-8").strip()


def load_guide_persona() -> str:
    """读人设 md；改完保存即生效，不需要重启后端。"""
    try:
        stat = _PERSONA_PATH.stat()
    except OSError:
        return _FALLBACK_PERSONA
    try:
        persona = _read_persona(stat.st_mtime, stat.st_size)
    except (OSError, UnicodeDecodeError):
        return _FALLBACK_PERSONA
    return persona or _FALLBACK_PERSONA


def compose_guide_prompt(context: dict[str, str] | None = None) -> str:
    """人设 md + 服务端算出的心情上下文 + 硬约束。

    context 由后端从短期记忆里取，不接受前端传入，避免客户端伪造「我很安全」这类状态。
    """
    parts = [load_guide_persona()]
    context = context or {}
    mood = _MOOD_LABEL.get(context.get("mood", ""))
    lines: list[str] = []
    if mood:
        lines.append(f"- 最近一次心情记录：{mood}")
    if context.get("checked_today") == "1":
        lines.append("- 今天已经记录过心情，不用再提打卡")
    else:
        lines.append("- 今天还没记录心情，可以轻轻问一句，但不要催")
    level = context.get("alert_level", "")
    if level in _LEVEL_LABEL:
        lines.append(f"- 支持等级：{_LEVEL_LABEL[level]}")
    if lines:
        parts.append("## 当前上下文（系统提供，不要向用户复述字段名）\n" + "\n".join(lines))
    parts.append(_HARD_RULES)
    return "\n\n".join(parts)
