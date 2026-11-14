from pathlib import Path

import asyncio

from docx import Document

from zhihui_qilu.ai.provider import OfflineProvider
from zhihui_qilu.document_drafting import _normalize, compose_draft, fallback_draft
from zhihui_qilu.document_models import LatexCompileResult, LatexError
from zhihui_qilu.document_phrases import phrase_payload
from zhihui_qilu.document_service import AdministrativeDocxEngine, LatexCompiler, LatexRepairClient, SelfCorrectingLatexEngine, TemplatePreParser
from zhihui_qilu.document_templates import TEMPLATE_CATALOG


def test_template_parser_and_docx_engine(tmp_path: Path) -> None:
    parser = TemplatePreParser()
    elements = parser.extract_elements("发文字号：鲁师字〔2026〕1号\n标题：关于开展测试的通知\n正文：请各单位按时完成。\n落款：教务处\n日期：2026年7月30日")
    output = AdministrativeDocxEngine().render(elements, tmp_path / "notice.docx")
    assert output.exists()
    text = "\n".join(paragraph.text for paragraph in Document(output).paragraphs)
    assert "关于开展测试的通知" in text and "教务处" in text


class RepairOnceCompiler(LatexCompiler):
    def __init__(self) -> None:
        self.calls = 0

    def compile(self, tex_path: Path, working_directory: Path) -> LatexCompileResult:
        self.calls += 1
        if self.calls == 1:
            return LatexCompileResult(success=False, error=LatexError(message="Missing $ inserted", line_number=3))
        pdf = working_directory / "paper.pdf"
        pdf.write_bytes(b"%PDF-test")
        return LatexCompileResult(success=True, pdf_path=pdf)


class SyntaxRepairer(LatexRepairClient):
    def repair_syntax(self, tex_source: str, error: LatexError) -> str:
        return tex_source.replace("\\badcommand", "\\relax")


class AlwaysFailCompiler(LatexCompiler):
    def compile(self, tex_path: Path, working_directory: Path) -> LatexCompileResult:
        return LatexCompileResult(success=False, error=LatexError(message="Unclosed environment"))


def test_latex_self_correction_and_docx_fallback(tmp_path: Path) -> None:
    corrected = SelfCorrectingLatexEngine(RepairOnceCompiler(), SyntaxRepairer()).build("\\documentclass{article}\\begin{document}hello \\badcommand\\end{document}", tmp_path / "ok", "paper")
    assert corrected.success and corrected.attempts == 2 and corrected.pdf_path.exists()
    fallback = SelfCorrectingLatexEngine(AlwaysFailCompiler(), SyntaxRepairer(), max_attempts=2).build("\\documentclass{article}\\begin{document}hello\\end{document}", tmp_path / "fallback", "paper")
    assert not fallback.success and fallback.fallback_docx_path.exists() and len(fallback.errors) == 2


def test_fallback_draft_round_trips_through_parser() -> None:
    """一句话成稿的兜底骨架必须能被权威解析器完整吃下，否则导出 DOCX 会丢字段。"""
    draft = fallback_draft("下周三组织消防演练，各班班长参加", "notice")
    elements = TemplatePreParser().extract_elements(draft)
    assert elements.title.startswith("山东师范大学关于")
    # 标题里不能出现逗号：只取第一个分句
    assert "，" not in elements.title and "下周三组织消防演练" in elements.title
    assert elements.recipient.endswith("：")
    assert "一、" in elements.body and "（一）" in elements.body
    assert elements.signature and "二○二六年" in elements.issue_date


def test_compose_draft_falls_back_when_provider_offline() -> None:
    draft, source = asyncio.run(compose_draft(OfflineProvider(), "组织消防演练", "notice"))
    assert source == "local" and "标题：" in draft


def test_normalize_indents_attachment_continuation() -> None:
    """模型常把 2.、3. 顶格输出；必须补缩进，否则第二条附件会被静默丢掉。"""
    raw = "标题：关于开展测试的通知\n正文：详见附件。\n附件：1．路线图\n2．人员名单\n"
    normalized = _normalize(raw)
    assert "　　　2．人员名单" in normalized
    assert TemplatePreParser().extract_elements(normalized).attachments == ["1．路线图", "2．人员名单"]


def test_parser_accepts_unindented_attachment_continuation() -> None:
    """手打和模型输出都会顶格，解析器不能只认缩进。"""
    text = "标题：关于开展测试的通知\n正文：详见附件。\n附件：1.报名表\n2.汇总表"
    assert TemplatePreParser().extract_elements(text).attachments == ["1.报名表", "2.汇总表"]


def test_phrase_book_genres_align_with_template_catalog() -> None:
    payload = phrase_payload()
    template_ids = {item["id"] for item in TEMPLATE_CATALOG}
    assert len(payload["groups"]) == 5
    assert sum(len(group["items"]) for group in payload["groups"]) >= 25
    # 文种指引点「用这个文种」时会按 template_id 切模板，对不上就是死链
    assert {row["template_id"] for row in payload["genres"]} <= template_ids
    assert len(payload["contrasts"]) == 4
    assert [rule["workdays"] for rule in payload["deadlines"]] == [1, 2, 5]
