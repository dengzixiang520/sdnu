"""一句话成稿：把口语化需求扩写成符合校规的公文草稿。

只做「起草」，不做签发：输出始终是可以继续编辑的带标签草稿
（发文字号／标题／主送机关／正文／落款／日期／附件），交给
TemplatePreParser 解析、AdministrativeDocxEngine 渲染。

模型不可用时用 document_templates 的骨架兜底，保证演示现场断网也能出稿。
"""

import re

from zhihui_qilu.ai.provider import ChatMessage, LanguageModelProvider, ProviderUnavailableError
from zhihui_qilu.document_templates import get_template

# 标签必须与 document_service.TemplatePreParser._LABELS 及前端 DRAFT_LABEL 对齐
LABELS = ("发文字号", "标题", "主送机关", "正文", "落款", "日期", "附件")

# 注意：这段提示词里不能出现「面试」「复试」「训练导师」等字样。
# OfflineProvider.complete 会按这些词把请求劫持成面试题，起草会拿到一段完全无关的文本。
_SYSTEM_PROMPT = """你是山东师范大学校长办公室的公文起草助手。用户给你一句话需求，你起草一份符合《山东师范大学行政文件格式细则》的公文草稿。

严格按下面的标签格式输出，每个标签独占一行，不要输出任何解释、不要使用 Markdown、不要写「以下是」之类的开场白：

发文字号：山东师大校字〔2026〕×号
标题：山东师范大学关于……的通知
主送机关：校内各单位：
正文：
为……，经学校研究，现将有关事项通知如下。
一、……
（一）……
1．……
二、……
三、工作要求
……
特此通知。
落款：山东师范大学
日期：二○二六年××月××日
附件：1.……

硬性要求：
- 正文 300～600 字。一级标题用「一、」，二级用「（一）」，三级用「1．」，不得混用其他编号
- 一级标题「一、」句尾不加标点，单独占一行
- 成文日期必须写成汉字，如「二○二六年十一月十三日」，不得用阿拉伯数字
- 不确定的具体信息（时间、地点、人名、电话、金额）一律用 ×× 占位，绝不编造
- 主送机关以全角冒号结尾
- 结束语由文种决定：通知用「特此通知。」，请示用「妥否，请批示。」，报告用「特此报告。」
- 正文里不要重复写「发文字号」「标题」这些标签名
"""

# 各文种的过渡语与结束语，兜底骨架按文种取，避免所有文种长一个样。
_LEAD_IN = {
    "notice": "通知",
    "announcement": "公告",
    "report": "报告",
    "request": "请示",
    "letter": "函告",
    "decision": "决定",
    "communique": "通报",
    "minutes": "纪要",
}

_FENCE = re.compile(r"^\s*```[a-zA-Z]*\s*$", re.MULTILINE)
_LEADING_NOISE = re.compile(r"^\s*(以下是|如下是|这是|好的)[^\n]*\n+")
_ATTACH_HEAD = re.compile(r"^附件\s*[：:]\s*")
_ATTACH_ITEM = re.compile(r"^\s*[（(]?\d+[）).、．]")


def _fix_attachment_indent(text: str) -> str:
    """附件续行必须与首个附件名对齐（细则要求），模型经常顶格输出。

    这里补上「　　　」缩进，让 TemplatePreParser 与前端 parseLabeledDraft
    都能识别出第二条以后的附件；否则导出 DOCX 会静默丢掉 2.、3.。
    """
    lines = text.splitlines()
    result: list[str] = []
    in_attach = False
    for line in lines:
        if _ATTACH_HEAD.match(line):
            in_attach = True
            result.append(line)
            continue
        if in_attach:
            if not line.strip():
                in_attach = False
                result.append(line)
                continue
            if _ATTACH_ITEM.match(line):
                result.append(line if line[:1].isspace() else f"　　　{line.strip()}")
                continue
            in_attach = False
        result.append(line)
    return "\n".join(result)


def _normalize(text: str) -> str:
    """把模型输出收拾成 TemplatePreParser 认得的带标签草稿。"""
    cleaned = _FENCE.sub("", text).strip()
    cleaned = _LEADING_NOISE.sub("", cleaned)
    # 标签后的半角冒号统一成全角，否则前端 DRAFT_LABEL 之外的镜像实现容易漏
    for label in LABELS:
        cleaned = re.sub(rf"^\s*{label}\s*:\s*", f"{label}：", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(rf"^\s*{label}\s*：\s*", f"{label}：", cleaned, flags=re.MULTILINE)
    # 模型有时会加「正文：」以外的层级标题符号前缀，去掉行首多余的 markdown 标记
    cleaned = re.sub(r"^\s*#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)
    return _fix_attachment_indent(cleaned.strip())


def _looks_usable(text: str) -> bool:
    """至少要有标题和正文两段，否则宁可走兜底也不要把半截文本交给用户。"""
    return "标题：" in text and "正文：" in text and len(text) >= 80


def _subject(brief: str) -> str:
    """从一句话需求里抽标题用的主题词。

    公文标题里不放逗号：只取第一个分句，其余信息留在正文首段，避免出现
    「关于下周三组织消防演练，各班班长参加的通知」这种带逗号的标题。
    """
    cleaned = brief.strip().strip("。；;，,、！!？?")
    first = re.split(r"[，,。；;、]", cleaned, maxsplit=1)[0]
    subject = re.sub(r"\s+", "", first)
    return subject[:40] or "××工作"


def fallback_draft(brief: str, doc_type: str = "notice") -> str:
    """模型不可用时的确定性骨架：结构完整、占位清晰，用户只需填空。"""
    template = get_template(doc_type) or get_template("notice") or {}
    name = str(template.get("name") or "通知")
    recipient = str(template.get("recipient") or "校内各单位：")
    closing = str(template.get("closing") or "特此通知。")
    lead = _LEAD_IN.get(doc_type, "通知")
    subject = _subject(brief)
    lines = [
        "发文字号：山东师大校字〔2026〕×号",
        f"标题：山东师范大学关于{subject}的{name}",
        f"主送机关：{recipient}",
        "正文：",
        f"现就{brief.strip().rstrip('。；;')}有关事项{lead}如下。",
        "一、总体要求",
        "（一）各单位要充分认识做好此项工作的重要意义，把责任落实到岗到人。",
        "（二）坚持问题导向，结合本单位实际细化措施，不搞层层加码。",
        "二、具体安排",
        "（一）时间：××年××月××日（星期×）×时×分。",
        "（二）地点：××校区××楼××会议室。",
        "（三）参加人员：×××、×××，以及各单位分管负责同志。",
        "三、工作要求",
        "（一）各单位要高度重视，主要负责同志亲自抓，明确专人负责。",
        "（二）请各单位于××月××日前将有关材料报××处（室），电子版发送至××@sdnu.edu.cn。",
        "（三）联系人：×××，联系电话：0531-××××××××。",
        closing,
        "落款：山东师范大学",
        "日期：二○二六年××月××日",
    ]
    return "\n".join(lines)


async def compose_draft(
    provider: LanguageModelProvider,
    brief: str,
    doc_type: str = "notice",
) -> tuple[str, str]:
    """返回 (草稿正文, 来源)。来源取 'deepseek' 或 'local'，前端据此提示用户。"""
    brief = brief.strip()
    if not brief:
        raise ValueError("请先写一句需求，例如「下周三组织消防演练，各班班长参加」")
    if not provider.available:
        return fallback_draft(brief, doc_type), "local"

    template = get_template(doc_type) or {}
    name = str(template.get("name") or "通知")
    scenario = str(template.get("scenario") or "")
    user_prompt = (
        f"文种：{name}\n"
        f"适用场景：{scenario}\n"
        f"需求：{brief}\n\n"
        f"请直接输出带标签的完整草稿。"
    )
    messages = [
        ChatMessage(role="system", content=_SYSTEM_PROMPT),
        ChatMessage(role="user", content=user_prompt),
    ]
    try:
        raw = await provider.complete(messages, temperature=0.4)
    except ProviderUnavailableError:
        return fallback_draft(brief, doc_type), "local"

    draft = _normalize(raw)
    if not _looks_usable(draft):
        return fallback_draft(brief, doc_type), "local"
    return draft, "deepseek"
