# -*- coding: utf-8 -*-
"""自检：按山师细则渲染 DOCX，并把结构 dump 成 UTF-8 文本供核对。"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docx import Document  # noqa: E402

from zhihui_qilu.document_models import OfficialDocumentElements  # noqa: E402
from zhihui_qilu.document_service import (  # noqa: E402
    AdministrativeDocxEngine,
    to_chinese_date,
)
from zhihui_qilu.document_templates import TEMPLATE_CATALOG  # noqa: E402

OUT_DIR = Path(tempfile.gettempdir())
REPORT = Path(__file__).with_name("_docx_report.txt")
lines: list[str] = []


def dump(path: Path, label: str) -> None:
    document = Document(path)
    lines.append(f"\n===== {label} | {path.name} | {path.stat().st_size} bytes =====")
    for index, paragraph in enumerate(document.paragraphs):
        if not paragraph.text.strip():
            continue
        fonts = sorted({run.font.name for run in paragraph.runs if run.font.name})
        sizes = sorted({round(run.font.size.pt, 1) for run in paragraph.runs if run.font.size})
        colors = sorted({str(run.font.color.rgb) for run in paragraph.runs if run.font.color and run.font.color.rgb})
        align = str(paragraph.alignment).split(" ")[0] if paragraph.alignment is not None else "-"
        lines.append(f"[{index:02d}] {paragraph.text[:60]!r} font={fonts} size={sizes} color={colors} align={align}")
    footer = document.sections[0].footer
    footer_text = "".join(p.text for p in footer.paragraphs)
    has_page_field = b"PAGE" in path.read_bytes()
    lines.append(f"footer={footer_text!r} page_field={has_page_field}")


def main() -> None:
    lines.append(f"chinese_date(2026年7月30日) = {to_chinese_date('2026年7月30日')}")
    lines.append(f"chinese_date(2007-08-15) = {to_chinese_date('2007-08-15')}")

    engine = AdministrativeDocxEngine()
    for template in TEMPLATE_CATALOG:
        elements = OfficialDocumentElements(
            reference_number=template["reference_sample"],
            title=f"（{template['name']}示例）山东师范大学关于测试事项的{template['name']}",
            body=(
                "这是正文首段，用于验证每段左空两字、回行顶格。\n"
                "一、一级标题应使用黑体且句尾不加标点\n"
                "正文内容，使用仿宋三号。\n"
                "（一）二级标题应使用楷体\n"
                "1．三级标题使用仿宋。\n"
            ),
            signature="山东师范大学",
            issue_date="2026年9月28日",
            doc_type=template["id"],
            banner_name="山东师范大学文件" if template["banner"] == "sdnu" else "山东师范大学校长办公室文件",
            recipient=template.get("recipient") or None,
            attachments=["附件名称一", "附件名称二"],
            cc=["党委办公室", "学生工作部（处）"],
            keywords=["人工智能", "竞赛", template["name"]],
            print_agency="山东师范大学校长办公室",
            signer="×××" if template["id"] in {"report", "request"} else None,
            secrecy="秘密★1年" if template["id"] == "report" else None,
            urgency="急件" if template["id"] == "request" else None,
        )
        path = OUT_DIR / f"sdnu_{template['id']}.docx"
        engine.render(elements, path)
        dump(path, template["name"])

    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"report written: {REPORT} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
