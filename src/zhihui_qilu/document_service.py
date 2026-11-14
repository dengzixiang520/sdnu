"""Task 6 formatting engine: template extraction, DOCX rendering, and bounded LaTeX repair.

DOCX 渲染严格按《山东师范大学行政文件格式细则》（山东师大校办字〔2007〕9 号）落地：
版头红线、2 号小标宋标题、3 号仿宋正文、层次序数字体切换、汉字成文时间、
主题词 / 抄送 / 印发机关三栏版记、4 号页码。
"""

import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from zhihui_qilu.document_models import (
    LatexBuildResult,
    LatexCompileResult,
    LatexError,
    OfficialDocumentElements,
    TemplateSpecification,
)
from zhihui_qilu.document_templates import get_banner, get_template

# 细则第二十二条：标题 2 号小标宋，正文 3 号仿宋
TITLE_FONT = "方正小标宋简体"
BODY_FONT = "仿宋_GB2312"
HEITI_FONT = "黑体"
KAITI_FONT = "楷体_GB2312"
TITLE_SIZE = Pt(22)   # 2 号
BODY_SIZE = Pt(16)    # 3 号
SMALL_SIZE = Pt(14)   # 4 号（页码）
RED = RGBColor(0xC0, 0x00, 0x00)

_CN_DIGITS = "○一二三四五六七八九"
_CN_TENS = {10: "十", 20: "二十", 30: "三十"}


def _set_run_font(run, name: str, size: Pt, bold: bool = False, color: RGBColor | None = None) -> None:
    """同时设置西文与中文字体，避免 Word 里中文回落到默认宋体。"""
    run.font.name = name
    run.font.size = size
    run.bold = bold
    if color is not None:
        run.font.color.rgb = color
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), name)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)


def _add_border(paragraph, edge: str, color: str = "000000", size: str = "6") -> None:
    """给段落加单线边框，用来画红头横线与版记分隔线。"""
    ppr = paragraph._p.get_or_add_pPr()
    borders = ppr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        ppr.append(borders)
    line = OxmlElement(f"w:{edge}")
    line.set(qn("w:val"), "single")
    line.set(qn("w:sz"), size)
    line.set(qn("w:space"), "1")
    line.set(qn("w:color"), color)
    borders.append(line)


def to_chinese_date(text: str | None) -> str:
    """把 2026年7月30日 / 2026-07-30 转成细则第十一条要求的汉字日期（二○二六年七月三十日）。"""
    if not text:
        return ""
    digits = re.findall(r"\d+", text)
    if len(digits) < 3:
        return text.strip()
    year, month, day = (int(item) for item in digits[:3])

    def cn_day(value: int) -> str:
        if value in _CN_TENS:
            return _CN_TENS[value]
        if value < 10:
            return _CN_DIGITS[value]
        tens, ones = divmod(value, 10)
        return _CN_TENS[tens * 10] + _CN_DIGITS[ones]

    year_text = "".join(_CN_DIGITS[int(ch)] for ch in str(year))
    return f"{year_text}年{cn_day(month)}月{cn_day(day)}日"


class TemplatePreParser:
    """Extract standard elements and placeholders from text or a Word template before rendering."""

    _LABELS = {
        "reference_number": ("发文字号", "文号"),
        "title": ("标题",),
        "body": ("正文",),
        "signature": ("落款", "署名"),
        "issue_date": ("日期", "成文日期"),
        "recipient": ("主送机关", "主送单位"),
    }

    def extract_elements(self, source_text: str) -> OfficialDocumentElements:
        """Extract labeled formal-document fields, applying a safe title/body fallback when unlabeled."""
        values: dict[str, str | None] = {key: self._find_labeled_value(source_text, labels) for key, labels in self._LABELS.items()}
        lines = [line.strip() for line in source_text.splitlines() if line.strip()]
        title = values["title"] or (lines[0] if lines else "未命名文件")
        attachments = self._extract_attachments(source_text)
        # 正文是唯一可能跨多段的字段：从「正文：」取到落款/日期之前，附件块单独渲染
        body = self._extract_body(source_text) or values["body"] or "\n".join(line for line in lines if line != title)
        if not body:
            body = "正文内容待补充。"
        return OfficialDocumentElements(
            reference_number=values["reference_number"],
            title=title,
            body=body,
            signature=values["signature"],
            issue_date=values["issue_date"],
            recipient=values["recipient"],
            attachments=attachments,
        )

    def _extract_body(self, source_text: str) -> str | None:
        """正文可跨多段：从「正文：」一直取到落款/日期标签，并摘掉附件块（附件另行渲染）。"""
        match = re.search(r"(?:^|\n)\s*正文\s*[：:][ \t]*(.*)", source_text, re.S)
        if not match:
            return None
        body = match.group(1)
        stop = re.search(r"\n\s*(?:落款|署名|日期|成文日期)\s*[：:]", body)
        if stop:
            body = body[: stop.start()]
        # 附件说明由 _add_attachments 单独排版，正文里不能重复出现
        body = re.split(r"\n\s*附件\s*[：:]", body, maxsplit=1)[0]
        body = "\n".join(line.rstrip() for line in body.splitlines()).strip()
        return body or None

    @staticmethod
    def _extract_attachments(source_text: str) -> list[str]:
        """附件说明可能折行：「附件：1.×××」后面跟续行「2.×××」。

        续行既可能按细则缩进对齐，也可能被手打或模型输出成顶格，
        两种都要收，否则导出 DOCX 会静默丢掉第二条以后的附件。
        """
        items: list[str] = []
        capturing = False
        for line in source_text.splitlines():
            stripped = line.strip()
            head = re.match(r"^附件\s*[：:]\s*(.*)$", stripped)
            if head:
                capturing = True
                if head.group(1).strip():
                    items.append(head.group(1).strip())
                continue
            if not capturing:
                continue
            if not stripped:
                break
            # 续行必须是条目编号，否则附件块到此结束
            if re.match(r"^[（(]?\d+[）).、．]", stripped):
                items.append(stripped)
                continue
            break
        return items

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
            self._build_sdnu_document(document, elements)
        document.save(output_path)
        return output_path

    def _configure_default_layout(self, document: Document) -> None:
        """A4 纸、上 37mm 下 35mm 左 28mm 右 26mm，正文 3 号仿宋（细则第二十一、二十二条）。"""
        section = document.sections[0]
        section.top_margin = Cm(3.7)
        section.bottom_margin = Cm(3.5)
        section.left_margin = Cm(2.8)
        section.right_margin = Cm(2.6)
        normal = document.styles["Normal"]
        normal.font.name = BODY_FONT
        normal.font.size = BODY_SIZE
        rpr = normal._element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        rfonts.set(qn("w:eastAsia"), BODY_FONT)
        normal.paragraph_format.space_before = Pt(0)
        normal.paragraph_format.space_after = Pt(0)

    # ---------- 版头 ----------

    def _add_secrecy_and_urgency(self, document: Document, elements: OfficialDocumentElements) -> None:
        """细则第五、六条：密级在前、紧急程度在后，均用 3 号黑体，注在首页右上角。"""
        marks = [item for item in (elements.secrecy, elements.urgency) if item]
        if not marks:
            return
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _set_run_font(paragraph.add_run("　".join(marks)), HEITI_FONT, BODY_SIZE)

    def _add_banner(self, document: Document, elements: OfficialDocumentElements) -> None:
        """细则第三、七、八条：红色机关名称 + 红头横线 + 发文字号（上报件加签发人）。"""
        banner = get_banner(elements.doc_type) or {}
        banner_name = elements.banner_name or banner.get("name") or "山东师范大学文件"
        is_minutes = elements.doc_type == "minutes"

        # 机关名称：红色小标宋，会议纪要按细则第二十条用 2 号黑体
        name_paragraph = document.add_paragraph()
        name_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        name_paragraph.paragraph_format.space_after = Pt(18)
        if is_minutes:
            _set_run_font(name_paragraph.add_run(banner_name), HEITI_FONT, TITLE_SIZE)
        else:
            _set_run_font(name_paragraph.add_run(banner_name), TITLE_FONT, Pt(36), bold=True, color=RED)

        # 红头横线
        line_paragraph = document.add_paragraph()
        line_paragraph.paragraph_format.space_after = Pt(6)
        _add_border(line_paragraph, "bottom", color="C00000", size="18")

        # 发文字号：无签发人时居中；上报件发文字号左移、签发人置右（第七条）
        if elements.reference_number:
            number_paragraph = document.add_paragraph()
            number_paragraph.paragraph_format.space_before = Pt(6)
            if elements.signer:
                number_paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                _set_run_font(number_paragraph.add_run(f"　{elements.reference_number}"), BODY_FONT, BODY_SIZE)
                number_paragraph.add_run("\t")
                _set_run_font(number_paragraph.add_run("签发人："), BODY_FONT, BODY_SIZE)
                _set_run_font(number_paragraph.add_run(elements.signer), KAITI_FONT, BODY_SIZE)
            else:
                number_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                _set_run_font(number_paragraph.add_run(elements.reference_number), BODY_FONT, BODY_SIZE)

    def _add_title(self, document: Document, elements: OfficialDocumentElements) -> None:
        """细则第八、二十二条：标题 2 号小标宋，红线下空 2 行，居中。"""
        document.add_paragraph()
        title = document.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title.paragraph_format.space_after = Pt(12)
        title.paragraph_format.line_spacing = 1.4
        _set_run_font(title.add_run(elements.title), TITLE_FONT, TITLE_SIZE)

    # ---------- 正文 ----------

    def _add_recipient(self, document: Document, elements: OfficialDocumentElements) -> None:
        """细则第九条：标题下空 1 行，左侧顶格，名称后加冒号，3 号仿宋。公告与纪要不写主送。"""
        if elements.doc_type in {"announcement", "minutes"}:
            return
        if not elements.recipient:
            return
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(6)
        _set_run_font(paragraph.add_run(elements.recipient), BODY_FONT, BODY_SIZE)

    def _add_body(self, document: Document, elements: OfficialDocumentElements) -> None:
        """细则第十条：每段左空 2 字、回行顶格；「一、」黑体、「（一）」楷体、「1．」仿宋。"""
        for raw_line in elements.body.splitlines():
            text = raw_line.strip()
            if not text:
                continue
            paragraph = document.add_paragraph()
            fmt = paragraph.paragraph_format
            fmt.first_line_indent = BODY_SIZE * 2          # 左空 2 字
            fmt.line_spacing_rule = WD_LINE_SPACING.EXACTLY
            fmt.line_spacing = Pt(29)                      # 3 号字常规行距
            if re.match(r"^[一二三四五六七八九十]+、", text):
                _set_run_font(paragraph.add_run(text), HEITI_FONT, BODY_SIZE)      # 一级标题黑体
            elif re.match(r"^[（(][一二三四五六七八九十]+[）)]", text):
                _set_run_font(paragraph.add_run(text), KAITI_FONT, BODY_SIZE)      # 二级标题楷体
            else:
                _set_run_font(paragraph.add_run(text), BODY_FONT, BODY_SIZE)

    def _add_closing(self, document: Document, elements: OfficialDocumentElements) -> None:
        """结束语按文种自动补，如「特此通知。」「妥否，请批示。」"""
        template = get_template(elements.doc_type) or {}
        closing = elements.closing if elements.closing is not None else template.get("closing", "")
        if not closing or closing in elements.body:
            return
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.first_line_indent = BODY_SIZE * 2
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        paragraph.paragraph_format.line_spacing = Pt(29)
        _set_run_font(paragraph.add_run(closing), BODY_FONT, BODY_SIZE)

    def _add_attachments(self, document: Document, elements: OfficialDocumentElements) -> None:
        """细则第十二条：正文下空 1 行、落款之上，3 号仿宋，附件名称后不加标点。"""
        if not elements.attachments:
            return
        document.add_paragraph()
        for index, name in enumerate(elements.attachments, start=1):
            label = "附件：" if index == 1 else "　　　"
            cleaned = name.rstrip("。.；;，,")
            paragraph = document.add_paragraph()
            _set_run_font(paragraph.add_run(f"{label}{index}.{cleaned}"), BODY_FONT, BODY_SIZE)

    def _add_signature(self, document: Document, elements: OfficialDocumentElements) -> None:
        """细则第十一条：落款与成文时间右对齐，成文时间用汉字标全。"""
        signature = elements.signature
        date_text = to_chinese_date(elements.issue_date)
        if not signature and not date_text:
            return
        document.add_paragraph()
        for value in (signature, date_text):
            if not value:
                continue
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            paragraph.paragraph_format.right_indent = BODY_SIZE * 2
            _set_run_font(paragraph.add_run(value), BODY_FONT, BODY_SIZE)

    # ---------- 版记 ----------

    def _add_register(self, document: Document, elements: OfficialDocumentElements) -> None:
        """细则第十四～十六条：主题词 → 抄送机关 → 印发机关与印发日期，三栏上下加细线。"""
        if not (elements.keywords or elements.cc or elements.print_agency):
            return
        document.add_paragraph()

        if elements.keywords:
            paragraph = document.add_paragraph()
            _add_border(paragraph, "top", size="8")
            _set_run_font(paragraph.add_run("主题词："), HEITI_FONT, BODY_SIZE)
            _set_run_font(paragraph.add_run("　".join(elements.keywords[:5])), TITLE_FONT, BODY_SIZE)

        if elements.cc:
            paragraph = document.add_paragraph()
            if not elements.keywords:
                _add_border(paragraph, "top", size="8")
            _set_run_font(paragraph.add_run(f"抄送：{'，'.join(elements.cc)}。"), BODY_FONT, BODY_SIZE)

        agency = elements.print_agency or "山东师范大学校长办公室"
        date_text = to_chinese_date(elements.issue_date)
        paragraph = document.add_paragraph()
        _add_border(paragraph, "top", size="8")
        _add_border(paragraph, "bottom", size="8")
        _set_run_font(paragraph.add_run(f"　{agency}　　　　　　{date_text}印发　"), BODY_FONT, BODY_SIZE)

    def _add_page_number(self, document: Document) -> None:
        """细则第十七条：4 号半角阿拉伯数码，置于版心下边缘之下一行。"""
        footer = document.sections[0].footer
        paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = paragraph.add_run()
        _set_run_font(run, BODY_FONT, SMALL_SIZE)
        field = OxmlElement("w:fldSimple")
        field.set(qn("w:instr"), "PAGE")
        inner = OxmlElement("w:r")
        text = OxmlElement("w:t")
        text.text = "1"
        inner.append(text)
        field.append(inner)
        paragraph._p.append(field)

    def _build_sdnu_document(self, document: Document, elements: OfficialDocumentElements) -> None:
        """按细则顺序拼装：密级 → 版头 → 标题 → 主送 → 正文 → 结束语 → 附件 → 落款 → 版记。"""
        self._add_secrecy_and_urgency(document, elements)
        self._add_banner(document, elements)
        self._add_title(document, elements)
        self._add_recipient(document, elements)
        self._add_body(document, elements)
        self._add_closing(document, elements)
        self._add_attachments(document, elements)
        self._add_signature(document, elements)
        self._add_register(document, elements)
        self._add_page_number(document)

    def _add_standard_content(self, document: Document, elements: OfficialDocumentElements) -> None:
        """保留旧接口：等价于完整版式渲染。"""
        self._build_sdnu_document(document, elements)

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
