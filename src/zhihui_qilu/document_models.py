"""Typed models for formal-document extraction, DOCX generation, and LaTeX recovery."""

from pathlib import Path
from pydantic import BaseModel, Field


class OfficialDocumentElements(BaseModel):
    """The four core elements required by the administrative-document engine.

    后面几项是按《山东师范大学行政文件格式细则》补的版式要素，全部有默认值，
    旧的调用方（只传五项）行为不变。
    """

    reference_number: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    signature: str | None = Field(default=None, max_length=200)
    issue_date: str | None = Field(default=None, max_length=50)

    # 版式要素
    doc_type: str = Field(default="notice", max_length=40)
    banner_name: str | None = Field(default=None, max_length=100)
    recipient: str | None = Field(default=None, max_length=300)
    attachments: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    urgency: str | None = Field(default=None, max_length=20)
    secrecy: str | None = Field(default=None, max_length=20)
    signer: str | None = Field(default=None, max_length=50)
    closing: str | None = Field(default=None, max_length=100)
    print_agency: str | None = Field(default=None, max_length=100)


class TemplateSpecification(BaseModel):
    """Pre-parsed template metadata used to select rendering behavior."""

    template_name: str
    reference_number: str | None = None
    title_hint: str | None = None
    body_hint: str | None = None
    signature_hint: str | None = None
    placeholder_names: list[str] = Field(default_factory=list)


class LatexError(BaseModel):
    """A structured pdflatex error supplied to a syntax-only correction adapter."""

    message: str
    line_number: int | None = None
    context: str | None = None


class LatexCompileResult(BaseModel):
    """Result returned by a compiler port for one LaTeX source attempt."""

    success: bool
    pdf_path: Path | None = None
    log: str = ""
    error: LatexError | None = None


class LatexBuildResult(BaseModel):
    """Final result of the bounded self-correction loop and its DOCX fallback."""

    success: bool
    attempts: int = Field(ge=1)
    tex_path: Path
    pdf_path: Path | None = None
    fallback_docx_path: Path | None = None
    errors: list[LatexError] = Field(default_factory=list)
