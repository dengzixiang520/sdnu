"""上传公文一键规范化的回归测试。

命题三验收的是「上传一份已经写好的公文，能不能改到合规」。所以这里造一份
故意格式很乱的 DOCX：宋体五号、无缩进、单倍行距、`1、` 序号、阿拉伯数字日期，
然后逐项断言它被改成了什么，以及改动清单里有没有写清依据。
"""

from pathlib import Path

import pytest
import re
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from zhihui_qilu.doc_normalizer import (
    BODY_FONT,
    BODY_LINE_SPACING,
    HEITI_FONT,
    MARGIN_BOTTOM_MM,
    MARGIN_LEFT_MM,
    MARGIN_RIGHT_MM,
    MARGIN_TOP_MM,
    NormalizeError,
    normalize_docx,
)


def _strip_markers(text: str) -> str:
    """去掉层次序数前缀，只留正文内容，用来判断「有没有改字」。"""
    cleaned = text.strip()
    cleaned = re.sub(r"^[一二三四五六七八九十]+\s*[、.．]\s*", "", cleaned)
    cleaned = re.sub(r"^[（(]\s*[一二三四五六七八九十\d]+\s*[）)]\s*[、.．]?\s*", "", cleaned)
    cleaned = re.sub(r"^\d+\s*[.．、]\s*", "", cleaned)
    return cleaned.strip()


def _make_messy_document(path: Path) -> Path:
    """造一份「学生自己拼出来的通知」：宋体五号、单倍行距、序号乱、日期阿拉伯数字。"""
    document = Document()
    normal = document.styles["Normal"]
    normal.font.name = "宋体"
    normal.font.size = Pt(10.5)

    lines = [
        "关于做好2026年寒假前后学生安全教育工作的通知",
        "各学院、各有关部门：",
        "为切实做好寒假前后学生安全教育管理工作，现将有关事项通知如下。",
        "一.提高思想认识",
        "各单位要充分认识安全教育工作的重要性，把责任落实到人。",
        "（一）压实工作责任",
        "1、开展一次全覆盖的安全教育主题班会。",
        "2、建立离校返校学生台账。",
        "（1）离校前完成登记",
        "请各单位于12月30日前报送工作总结。",
        "附件：1.安全教育主题班会记录表",
        "2026年1月8日",
    ]
    for line in lines:
        paragraph = document.add_paragraph(line)
        paragraph.paragraph_format.line_spacing = 1.0
        for run in paragraph.runs:
            run.font.name = "宋体"
            run.font.size = Pt(10.5)

    document.save(str(path))
    return path


@pytest.fixture()
def messy_doc(tmp_path: Path) -> Path:
    return _make_messy_document(tmp_path / "通知-学生版.docx")


def test_page_setup_follows_national_standard(messy_doc: Path, tmp_path: Path) -> None:
    """版心必须是 A4 + 上 37 下 35 左 28 右 26 毫米。"""
    out = tmp_path / "out.docx"
    normalize_docx(messy_doc, out, doc_type="notice")

    section = Document(str(out)).sections[0]
    assert round(section.top_margin.mm) == MARGIN_TOP_MM
    assert round(section.bottom_margin.mm) == MARGIN_BOTTOM_MM
    assert round(section.left_margin.mm) == MARGIN_LEFT_MM
    assert round(section.right_margin.mm) == MARGIN_RIGHT_MM
    assert round(section.page_width.mm) == 210


def test_title_and_heading_levels_get_their_fonts(messy_doc: Path, tmp_path: Path) -> None:
    """标题 2 号小标宋居中；一级标题黑体；正文仿宋三号。"""
    out = tmp_path / "out.docx"
    normalize_docx(messy_doc, out, doc_type="notice")
    document = Document(str(out))

    title = document.paragraphs[0]
    assert title.alignment == WD_ALIGN_PARAGRAPH.CENTER
    assert title.runs[0].font.size == Pt(22)
    assert title.runs[0].font.name == "方正小标宋简体"

    h1 = next(item for item in document.paragraphs if item.text.startswith("一、"))
    assert h1.runs[0].font.name == HEITI_FONT
    assert h1.runs[0].font.size == Pt(16)

    body = next(item for item in document.paragraphs if item.text.startswith("为切实做好"))
    assert body.runs[0].font.name == BODY_FONT
    assert body.runs[0].font.size == Pt(16)
    assert body.paragraph_format.first_line_indent == Pt(32)
    assert body.paragraph_format.line_spacing == BODY_LINE_SPACING


def test_numbering_is_normalized(messy_doc: Path, tmp_path: Path) -> None:
    """`一.` 改 `一、`，`1、` 改 `1.`，半角括号改全角。"""
    out = tmp_path / "out.docx"
    outcome = normalize_docx(messy_doc, out, doc_type="notice")
    texts = [item.text for item in Document(str(out)).paragraphs]

    assert "一、提高思想认识" in texts
    assert "1.开展一次全覆盖的安全教育主题班会。" in texts
    assert "（一）压实工作责任" in texts
    assert any(item.category == "序号编号" for item in outcome.changes)


def test_date_becomes_chinese(messy_doc: Path, tmp_path: Path) -> None:
    """成文日期用汉字，右空四字。"""
    out = tmp_path / "out.docx"
    normalize_docx(messy_doc, out, doc_type="notice")
    document = Document(str(out))

    date_paragraph = next(item for item in document.paragraphs if "二○二六年" in item.text)
    assert date_paragraph.text == "二○二六年一月八日"
    assert date_paragraph.alignment == WD_ALIGN_PARAGRAPH.RIGHT
    assert date_paragraph.paragraph_format.right_indent == Pt(64)


def test_footer_has_page_field(messy_doc: Path, tmp_path: Path) -> None:
    """页脚要有 PAGE 域，不是写死的「1」。"""
    out = tmp_path / "out.docx"
    normalize_docx(messy_doc, out, doc_type="notice")
    document = Document(str(out))

    footer = document.sections[0].footer
    xml = footer.paragraphs[0]._p.xml
    assert "PAGE" in xml
    assert "fldChar" in xml


def test_changes_carry_basis_and_category(messy_doc: Path, tmp_path: Path) -> None:
    """每一处改动都要有依据，前端要逐条展示给评委看。"""
    out = tmp_path / "out.docx"
    outcome = normalize_docx(messy_doc, out, doc_type="notice")

    assert outcome.total_changes > 5
    categories = outcome.by_category()
    assert "页边距" in categories
    assert "字体字号" in categories
    assert "行距" in categories
    for change in outcome.changes:
        assert change.basis, f"第 {change.index} 段「{change.category}」没有依据"
        assert change.before != change.after


def test_checklist_points_out_missing_elements(messy_doc: Path, tmp_path: Path) -> None:
    """文种要素自检要能说出缺哪一项，而不是笼统说「不完整」。"""
    out = tmp_path / "out.docx"
    outcome = normalize_docx(messy_doc, out, doc_type="notice")

    items = {item.item: item.present for item in outcome.checklist}
    assert items["标题"] is True
    assert items["主送机关"] is True
    assert items["成文日期"] is True
    # 这份文档没有发文机关署名
    assert items["发文机关署名"] is False
    assert any("发文机关署名" in warning for warning in outcome.warnings)


def test_content_is_never_rewritten(messy_doc: Path, tmp_path: Path) -> None:
    """除序号与日期外，正文文字必须逐字保留。"""
    out = tmp_path / "out.docx"
    normalize_docx(messy_doc, out, doc_type="notice")

    before = [item.text for item in Document(str(messy_doc)).paragraphs if item.text.strip()]
    after = [item.text for item in Document(str(out)).paragraphs if item.text.strip()]
    assert len(before) == len(after)

    for old, new in zip(before, after):
        if re.search(r"\d{4}\s*年\s*\d{1,2}\s*月", old):
            continue  # 日期整体转汉字，由 test_date_becomes_chinese 单独覆盖
        assert _strip_markers(old) == _strip_markers(new), f"正文被改了：{old!r} → {new!r}"


def test_legacy_doc_format_is_rejected(tmp_path: Path) -> None:
    """老 .doc 读不了，要说清怎么办，而不是抛一堆栈。"""
    bad = tmp_path / "old.doc"
    bad.write_bytes(b"\xd0\xcf\x11\xe0")
    with pytest.raises(NormalizeError) as error:
        normalize_docx(bad, tmp_path / "out.docx", doc_type="notice")
    assert "另存为" in str(error.value)


def test_pdf_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "scan.pdf"
    bad.write_bytes(b"%PDF-1.4")
    with pytest.raises(NormalizeError) as error:
        normalize_docx(bad, tmp_path / "out.docx", doc_type="notice")
    assert ".docx" in str(error.value)


def test_corrupt_docx_reports_readable_error(tmp_path: Path) -> None:
    """坏文件不能 500，要给一句人能看懂的话。"""
    bad = tmp_path / "broken.docx"
    bad.write_bytes(b"not a zip at all")
    with pytest.raises(NormalizeError) as error:
        normalize_docx(bad, tmp_path / "out.docx", doc_type="notice")
    assert "打不开" in str(error.value)


def test_unknown_doc_type_falls_back_to_notice(messy_doc: Path, tmp_path: Path) -> None:
    """文种传错不能炸，退回通知并按通知核对要素。"""
    out = tmp_path / "out.docx"
    outcome = normalize_docx(messy_doc, out, doc_type="not-a-real-type")
    assert outcome.doc_type == "notice"
    assert outcome.doc_type_name == "通知"
