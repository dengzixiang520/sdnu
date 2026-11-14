"""定向命题七 Skill：钓鱼邮件、可疑链接与仿冒页面识别。

只做三件事：文本、HTML 源码、单条链接。截图 OCR 不做——识别图片里的字
是另一件事，做一半反而让人以为看懂了整张图。

刻意不接大模型：钓鱼识别是安全判断，结论必须能指回具体规则，
而且要能离线跑、结果可复现。
"""

from zhihui_qilu.core.models import AgentRequest, AgentResponse
from zhihui_qilu.phishing_service import (
    PhishingInputError,
    analyze_html,
    analyze_text,
    analyze_url,
)
from zhihui_qilu.skills.base import BaseSkill


class PhishingSkill(BaseSkill):
    """Expose explainable phishing checks for text, HTML source, and links."""

    skill_id = "phishing"
    display_name = "钓鱼邮件与可疑链接识别"

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Dispatch the three bounded checks from typed request payloads."""
        action = str(request.payload.get("action", "")).strip()
        text = request.text or ""

        if action == "check_text":
            return self._run(analyze_text, str(request.payload.get("text") or text), "文本分析完成")
        if action == "check_html":
            return self._run(analyze_html, str(request.payload.get("html") or text), "页面源码分析完成")
        if action == "check_url":
            return self._run(analyze_url, str(request.payload.get("url") or text), "链接分析完成")

        # 不指定类型时按内容猜：带尖括号且有标签名当 HTML，能看出域名当链接，其余当文本。
        if action in {"", "check"}:
            guess = _guess_input_type(str(request.payload.get("content") or text))
            if guess == "html":
                return self._run(analyze_html, str(request.payload.get("content") or text), "页面源码分析完成")
            if guess == "url":
                return self._run(analyze_url, str(request.payload.get("content") or text), "链接分析完成")
            return self._run(analyze_text, str(request.payload.get("content") or text), "文本分析完成")

        return AgentResponse(
            success=False,
            message="不支持的钓鱼识别操作",
            data={"supported_actions": ["check_text", "check_html", "check_url", "check"]},
        )

    @staticmethod
    def _run(analyzer, content: str, message: str) -> AgentResponse:
        try:
            report = analyzer(content)
        except PhishingInputError as exc:
            return AgentResponse(success=False, message=str(exc))
        return AgentResponse(success=True, message=f"{message}：{report.risk_label}", data=report.as_dict())


def _guess_input_type(content: str) -> str:
    """粗略判断粘贴进来的是什么，省得用户先选一次类型。"""
    body = (content or "").strip()
    if not body:
        return "text"
    lowered = body.lower()
    if "<" in body and ">" in body and any(tag in lowered for tag in ("<html", "<form", "<div", "<body", "<a ")):
        return "html"
    if " " not in body and "\n" not in body and ("://" in body or body.startswith("www.")):
        return "url"
    return "text"
