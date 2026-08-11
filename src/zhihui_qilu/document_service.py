"""Task 6 formatting engine: template extraction, DOCX rendering, and bounded LaTeX repair."""

import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from zhihui_qilu.document_models import (
    LatexBuildResult,
    LatexCompileResult,
    LatexError,
    OfficialDocumentElements,
    TemplateSpecification,
)


class TemplatePreParser:
    """Extract standard elements and placeholders from text or a Word template before rendering."""

    _LABELS = {
        "reference_number": ("发文字号", "文号"),
        "title": ("标题",),
        "body": ("正文",),
        "signature": ("落款", "署名"),
        "issue_date": ("日期", "成文日期"),
    }

    def extract_elements(self, source_text: str) -> OfficialDocumentElements:
        """Extract labeled formal-document fields, applying a safe title/body fallback when unlabeled."""
        values: dict[str, str | None] = {key: self._find_labeled_value(source_text, labels) for key, labels in self._LABELS.items()}
        lines = [line.strip() for line in source_text.splitlines() if line.strip()]
        title = values["title"] or (lines[0] if lines else "未命名文件")
        body = values["body"] or "\n".join(line for line in lines if line != title)
        if not body:
            body = "正文内容待补充。"
        return OfficialDocumentElements(reference_number=values["reference_number"], title=title, body=body, signature=values["signature"], issue_date=values["issue_date"])

    def inspect_docx_template(self, template_path: Path) -> TemplateSpecification:
        """Read a DOCX template's visible text and discover supported {{placeholder}} markers."""
        document = Document(template_path)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        elements = self.extract_elements(text)
        placeholders = sorted(set(re.findall(r"\{\{\s*([a-z_]+)\s*\}\}", text)))
        return TemplateSpecification(template_name=template_path.name, reference_number=elements.reference_number, title_hint=elements.title, body_hint=elements.body, signature_hint=elements.signature, placeholder_names=placeholders)

    @staticmethod
    def _find_labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
        for label in labels:
            match = re.search(rf"(?:^|\n)\s*{re.escape(label)}\s*[：:]\s*(.+)", text)
            if match:
                return match.group(1).strip()
        return None


class AdministrativeDocxEngine:
    """Render a standardized administrative DOCX using python-docx or an approved template."""

    def render(self, elements: OfficialDocumentElements, output_path: Path, template_path: Path | None = None) -> Path:
        """Create a DOCX with replacements for known placeholders and conservative government-style defaults."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        document = Document(template_path) if template_path else Document()
        if template_path:
            self._replace_placeholders(document, elements)
        else:
            self._configure_default_layout(document)
            self._add_standard_content(document, elements)
        document.save(output_path)
        return output_path

    def _configure_default_layout(self, document: Document) -> None:
        section = document.sections[0]
        section.top_margin = Cm(3.7)
        section.bottom_margin = Cm(3.5)
        section.left_margin = Cm(2.8)
        section.right_margin = Cm(2.6)
        normal = document.styles["Normal"]
        normal.font.name = "仿宋_GB2312"
        normal._element.rPr.rFonts.set(qn("w:eastAsia"), "仿宋_GB2312")
        normal.font.size = Pt(16)

    def _add_standard_content(self, document: Document, elements: OfficialDocumentElements) -> None:
        if elements.reference_number:
            reference = document.add_paragraph(elements.reference_number)
            reference.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title = document.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title.add_run(elements.title)
        title_run.bold = True
        title_run.font.name = "方正小标宋简体"
        title_run._element.rPr.rFonts.set(qn("w:eastAsia"), "方正小标宋简体")
        title_run.font.size = Pt(22)
        for paragraph_text in elements.body.splitlines():
            if paragraph_text.strip():
                paragraph = document.add_paragraph(paragraph_text.strip())
                paragraph.paragraph_format.first_line_indent = Cm(0.74)
                paragraph.paragraph_format.line_spacing = 1.5
        if elements.signature or elements.issue_date:
            signature = document.add_paragraph()
            signature.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            signature.add_run("\n".join(part for part in (elements.signature, elements.issue_date) if part))

    @staticmethod
    def _replace_placeholders(document: Document, elements: OfficialDocumentElements) -> None:
        replacements = {"reference_number": elements.reference_number or "", "title": elements.title, "body": elements.body, "signature": elements.signature or "", "issue_date": elements.issue_date or ""}
        for paragraph in document.paragraphs:
            for key, value in replacements.items():
                marker = "{{" + key + "}}"
                if marker in paragraph.text:
                    for run in paragraph.runs:
                        if marker in run.text:
                            run.text = run.text.replace(marker, value)


class LatexCompiler(ABC):
    """Port isolating pdflatex process invocation from the correction workflow."""

    @abstractmethod
    def compile(self, tex_path: Path, working_directory: Path) -> LatexCompileResult:
        """Compile one source version and return a structured, non-throwing result."""


class PdflatexCompiler(LatexCompiler):
    """Local pdflatex adapter; it invokes no shell and retains logs only in the job directory."""

    def __init__(self, executable: str = "pdflatex") -> None:
        self._executable = executable

    def compile(self, tex_path: Path, working_directory: Path) -> LatexCompileResult:
        """Run pdflatex with noninteractive flags and extract the first actionable error."""
        if shutil.which(self._executable) is None:
            error = LatexError(message="pdflatex executable was not found")
            return LatexCompileResult(success=False, error=error, log=error.message)
        process = subprocess.run([self._executable, "-interaction=nonstopmode", "-halt-on-error", tex_path.name], cwd=working_directory, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        log_path = working_directory / f"{tex_path.stem}.log"
        log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else process.stdout + process.stderr
        pdf_path = working_directory / f"{tex_path.stem}.pdf"
        if process.returncode == 0 and pdf_path.exists():
            return LatexCompileResult(success=True, pdf_path=pdf_path, log=log)
        return LatexCompileResult(success=False, log=log, error=self._parse_error(log))

    @staticmethod
    def _parse_error(log: str) -> LatexError:
        error_match = re.search(r"^!\s*(.+)$", log, flags=re.MULTILINE)
        line_match = re.search(r"^l\.(\d+)\s*(.*)$", log, flags=re.MULTILINE)
        return LatexError(message=error_match.group(1).strip() if error_match else "pdflatex compilation failed", line_number=int(line_match.group(1)) if line_match else None, context=line_match.group(2).strip() if line_match else None)


class LatexRepairClient(ABC):
    """Port for a reviewed LLM syntax repair service; content semantics must remain untouched."""

    @abstractmethod
    def repair_syntax(self, tex_source: str, error: LatexError) -> str:
        """Return only a minimal syntax repair; callers validate that source body remains under policy."""


class SelfCorrectingLatexEngine:
    """Bounded pdflatex → structured error → syntax repair loop with DOCX fallback."""

    def __init__(self, compiler: LatexCompiler, repair_client: LatexRepairClient, docx_engine: AdministrativeDocxEngine | None = None, max_attempts: int = 3) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._compiler = compiler
        self._repair_client = repair_client
        self._docx_engine = docx_engine or AdministrativeDocxEngine()
        self._max_attempts = max_attempts

    def build(self, tex_source: str, output_directory: Path, stem: str = "academic_document") -> LatexBuildResult:
        """Compile at most N times, persisting each repaired source and falling back to a DOCX delivery."""
        output_directory.mkdir(parents=True, exist_ok=True)
        tex_path = output_directory / f"{stem}.tex"
        source = tex_source
        errors: list[LatexError] = []
        for attempt in range(1, self._max_attempts + 1):
            tex_path.write_text(source, encoding="utf-8")
            result = self._compiler.compile(tex_path, output_directory)
            if result.success:
                return LatexBuildResult(success=True, attempts=attempt, tex_path=tex_path, pdf_path=result.pdf_path, errors=errors)
            error = result.error or LatexError(message="Unknown LaTex compilation failure")
            errors.append(error)
            if attempt < self._max_attempts:
                repaired = self._repair_client.repair_syntax(source, error)
                self._reject_semantic_rewrite(source, repaired)
                source = repaired
        fallback_path = output_directory / f"{stem}_fallback.docx"
        body = self._tex_to_plain_text(source)
        self._docx_engine.render(OfficialDocumentElements(title="学术文档编译兜底版本", body=body), fallback_path)
        return LatexBuildResult(success=False, attempts=self._max_attempts, tex_path=tex_path, fallback_docx_path=fallback_path, errors=errors)

    @staticmethod
    def _reject_semantic_rewrite(original: str, repaired: str) -> None:
        """Guard against repair clients changing prose outside LaTeX command syntax."""
        strip_commands = lambda value: re.sub(r"\\[a-zA-Z]+(?:\[[^]]*\])?(?:\{[^{}]*\})?", "", value)
        if re.sub(r"\s+", "", strip_commands(original)) != re.sub(r"\s+", "", strip_commands(repaired)):
            raise ValueError("LaTeX repair attempted to alter document prose; semantic rewrite is forbidden")

    @staticmethod
    def _tex_to_plain_text(source: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"\\[a-zA-Z]+(?:\[[^]]*\])?(?:\{([^{}]*)\})?", r"\1", source)).strip() or "LaTeX 源文件无法转换为正文。"
