from pathlib import Path

from docx import Document

from zhihui_qilu.document_models import LatexCompileResult, LatexError
from zhihui_qilu.document_service import AdministrativeDocxEngine, LatexCompiler, LatexRepairClient, SelfCorrectingLatexEngine, TemplatePreParser


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
