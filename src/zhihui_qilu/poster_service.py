"""学术海报生成（定向命题六）。

思路：**填表 → 生成可打印的 HTML → 浏览器另存为 PDF**。

为什么不让模型直接画一张图：
- 海报要打印出来贴在墙上，位图放大就糊，还得管 300dpi；
- 生成完总要改字，位图改一个标点就得整张重来；
- 现场断网时位图方案直接不可用，HTML 方案照样出结果。

所以这里做的事是：把「排版规则」和「内容体检」自动化，
每个字都留在用户手里。字号按纸张宽度等比缩放，换尺寸不用重新排版。
"""

from __future__ import annotations

import html
import re

from zhihui_qilu.poster_models import (
    PosterCheckItem,
    PosterFontPlan,
    PosterPlan,
    PosterRequest,
)

# A 系列竖版尺寸（mm）。海报基本都是竖版贴在展板上。
SIZES: dict[str, tuple[int, int, str]] = {
    "a0": (841, 1189, "A0 竖版 · 841 × 1189 mm"),
    "a1": (594, 841, "A1 竖版 · 594 × 841 mm"),
    "a2": (420, 594, "A2 竖版 · 420 × 594 mm"),
    "a3": (297, 420, "A3 竖版 · 297 × 420 mm"),
}

BASE_WIDTH = 841  # 以 A0 宽度为基准，其余尺寸等比缩放字号

# 体检阈值。海报不是论文：正文超过 220 字，站着看的人就不会读了。
TITLE_MAX_CHARS = 60
BODY_MAX_CHARS = 220
SECTION_MIN, SECTION_MAX = 3, 5
KEYWORD_MIN, KEYWORD_MAX = 3, 5
FIGURE_MIN = 1
FIGURE_MAX = 4

CONCLUSION_WORDS = ("结论", "小结", "总结", "讨论与结论", "结语")

PRINT_HINT = (
    "浏览器按 Ctrl+P → 目标打印机选「另存为 PDF」→ 边距选「无」→ 勾选「背景图形」→ 保存。"
    "纸张尺寸要和上面选的一致，否则会被缩放。"
)

_BASE_CSS = """
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #e9ece4; }
body {
  font-family: "Source Han Sans SC", "Noto Sans SC", "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", sans-serif;
  color: #14201f;
  -webkit-font-smoothing: antialiased;
}
.poster {
  width: var(--pw);
  min-height: var(--ph);
  margin: 0 auto;
  padding: var(--pad);
  display: flex;
  flex-direction: column;
  gap: var(--gap);
  background: #ffffff;
}
.poster-head {
  padding-bottom: calc(var(--gap) / 2);
  border-bottom: calc(var(--gap) / 5) solid #173f43;
}
.poster-title {
  margin: 0 0 calc(var(--gap) / 3);
  font-size: var(--title);
  line-height: 1.16;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.poster-authors {
  margin: 0;
  font-size: calc(var(--body) * 1.02);
  font-weight: 600;
}
.poster-affil {
  margin: 0.35em 0 0;
  font-size: var(--cap);
  color: #4b5b58;
}
.poster-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4em;
  margin: calc(var(--gap) / 3) 0 0;
  padding: 0;
  list-style: none;
}
.poster-keywords li {
  padding: 0.16em 0.65em;
  border: 1px solid #cfd7cb;
  border-radius: 999px;
  font-size: var(--cap);
  color: #2f4a45;
}
.poster-body {
  flex: 1;
  column-count: var(--cols);
  column-gap: var(--gap);
}
.poster-body section {
  break-inside: avoid;
  margin: 0 0 calc(var(--gap) * 0.7);
}
.poster-body h2 {
  margin: 0 0 0.4em;
  padding-left: 0.45em;
  border-left: 0.18em solid #397f72;
  font-size: var(--sec);
  line-height: 1.22;
}
.poster-body p {
  margin: 0 0 0.55em;
  font-size: var(--body);
  line-height: 1.55;
  text-align: justify;
}
.poster-body ul {
  margin: 0 0 0.55em;
  padding-left: 1.15em;
  font-size: var(--body);
  line-height: 1.5;
}
.poster-body li { margin: 0 0 0.28em; }
.poster-figure {
  break-inside: avoid;
  margin: 0 0 calc(var(--gap) * 0.7);
}
.poster-figure-box {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(var(--gap) * 4);
  padding: 2em;
  border: calc(var(--gap) / 12) dashed #cfd7cb;
  border-radius: 2mm;
  background: #faf9f2;
  color: #8f9c98;
  font-size: var(--cap);
  text-align: center;
}
.poster-figure figcaption {
  margin-top: 0.45em;
  font-size: var(--cap);
  color: #4b5b58;
}
.poster-foot {
  display: flex;
  justify-content: space-between;
  gap: 1em;
  padding-top: calc(var(--gap) / 3);
  border-top: 0.1em solid #d8ded4;
  font-size: var(--cap);
  color: #667572;
}
@media print {
  html, body { background: #ffffff; }
  .poster { margin: 0; }
}
""".strip()


def _font_plan(width: int, columns: int) -> PosterFontPlan:
    """按纸张宽度等比缩放字号。A0 基准：标题 84pt、栏目 44pt、正文 28pt。"""
    scale = width / BASE_WIDTH
    return PosterFontPlan(
        title_pt=max(18, round(84 * scale)),
        section_pt=max(11, round(44 * scale)),
        body_pt=max(8, round(28 * scale)),
        caption_pt=max(7, round(20 * scale)),
        columns=columns,
    )


def _word_count(request: PosterRequest) -> int:
    """中文按字、英文按词，估个总量。海报正文一般 400–900 字。"""
    chunks = [request.title, request.authors, request.affiliation]
    for section in request.sections:
        chunks.append(section.heading)
        chunks.append(section.body)
        chunks.extend(section.bullets)
    chunks.extend(request.keywords)
    text = " ".join(chunks)
    cjk = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    latin = len(re.findall(r"[A-Za-z0-9]+", text))
    return cjk + latin


def _checklist(request: PosterRequest) -> list[PosterCheckItem]:
    """内容体检。每条都给「怎么改」，不只是判对错。"""
    items: list[PosterCheckItem] = []

    title_len = len(request.title.strip())
    items.append(
        PosterCheckItem(
            id="title_length",
            label="标题长度",
            passed=title_len <= TITLE_MAX_CHARS,
            advice=f"现在 {title_len} 字。标题控制在 {TITLE_MAX_CHARS} 字以内——三米外只看得清一行。",
        )
    )

    count = len(request.sections)
    items.append(
        PosterCheckItem(
            id="section_count",
            label="栏目数量",
            passed=SECTION_MIN <= count <= SECTION_MAX,
            advice=f"现在 {count} 栏。海报 {SECTION_MIN}–{SECTION_MAX} 栏最稳：太少讲不清，太多没人读。",
        )
    )

    has_conclusion = any(word in section.heading for section in request.sections for word in CONCLUSION_WORDS)
    items.append(
        PosterCheckItem(
            id="has_conclusion",
            label="有结论栏",
            passed=has_conclusion,
            advice="缺一栏「结论」。评委停留 40 秒，最想看的是你得到了什么，而不是你怎么做的。",
        )
    )

    longest = max((len(section.body.strip()) for section in request.sections), default=0)
    items.append(
        PosterCheckItem(
            id="body_length",
            label="单栏正文长度",
            passed=longest <= BODY_MAX_CHARS,
            advice=f"最长一栏 {longest} 字。超过 {BODY_MAX_CHARS} 字就换成要点，或者把细节留到口头讲。",
        )
    )

    figures = len(request.figures)
    items.append(
        PosterCheckItem(
            id="figure_count",
            label="图表数量",
            passed=FIGURE_MIN <= figures <= FIGURE_MAX,
            advice=f"现在 {figures} 个图表位。{FIGURE_MIN}–{FIGURE_MAX} 个比较合适：一张主图加一两张辅图。",
        )
    )

    keywords = [item for item in request.keywords if item.strip()]
    items.append(
        PosterCheckItem(
            id="keyword_count",
            label="关键词数量",
            passed=KEYWORD_MIN <= len(keywords) <= KEYWORD_MAX,
            advice=f"现在 {len(keywords)} 个。{KEYWORD_MIN}–{KEYWORD_MAX} 个关键词方便别人检索到你。",
        )
    )

    items.append(
        PosterCheckItem(
            id="affiliation",
            label="单位署名",
            passed=bool(request.affiliation.strip()),
            advice="补上单位。海报没有单位，别人不知道该把成果算在谁头上。",
        )
    )

    items.append(
        PosterCheckItem(
            id="authors",
            label="作者署名",
            passed=bool(request.authors.strip()),
            advice="补上作者与顺序。署名顺序在学术场合是有含义的，别空着。",
        )
    )

    items.append(
        PosterCheckItem(
            id="contact",
            label="联系方式",
            passed=bool(request.contact.strip()),
            advice="建议留一个邮箱或电话。有人想追问时，找不到你就等于没讲。",
            level="info",
        )
    )

    return items


def _render_html(request: PosterRequest, fonts: PosterFontPlan, width: int, height: int) -> str:
    """生成自包含的 HTML：不引外部字体、不引外部图片，断网也能打印。"""
    esc = html.escape
    pad = max(6, round(width * 0.031))
    gap = max(4, round(width * 0.017))

    parts: list[str] = [
        "<!doctype html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{esc(request.title)}</title>",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<style>",
        f"@page {{ size: {width}mm {height}mm; margin: 0; }}",
        ":root{"
        f"--pw:{width}mm;--ph:{height}mm;--pad:{pad}mm;--gap:{gap}mm;"
        f"--title:{fonts.title_pt}pt;--sec:{fonts.section_pt}pt;"
        f"--body:{fonts.body_pt}pt;--cap:{fonts.caption_pt}pt;--cols:{fonts.columns}"
        "}",
        _BASE_CSS,
        "</style>",
        "</head>",
        "<body>",
        '<div class="poster">',
        '<header class="poster-head">',
        f'<h1 class="poster-title">{esc(request.title)}</h1>',
    ]

    if request.authors.strip():
        parts.append(f'<p class="poster-authors">{esc(request.authors)}</p>')
    if request.affiliation.strip():
        parts.append(f'<p class="poster-affil">{esc(request.affiliation)}</p>')
    if request.keywords:
        parts.append('<ul class="poster-keywords">')
        for keyword in request.keywords:
            if keyword.strip():
                parts.append(f"<li>{esc(keyword.strip())}</li>")
        parts.append("</ul>")
    parts.append("</header>")
    parts.append('<div class="poster-body">')

    for section in request.sections:
        parts.append("<section>")
        parts.append(f"<h2>{esc(section.heading)}</h2>")
        # 正文按行分段：作者在表单里换行就是想分段。
        for chunk in (line.strip() for line in section.body.split("\n")):
            if chunk:
                parts.append(f"<p>{esc(chunk)}</p>")
        bullets = [item.strip() for item in section.bullets if item.strip()]
        if bullets:
            parts.append("<ul>")
            for bullet in bullets:
                parts.append(f"<li>{esc(bullet)}</li>")
            parts.append("</ul>")
        parts.append("</section>")

    for index, figure in enumerate(request.figures, start=1):
        caption = figure.caption.strip() or "图表"
        hint = figure.hint.strip() or "在此处替换为你的图表"
        parts.append('<figure class="poster-figure">')
        parts.append(f'<div class="poster-figure-box">{esc(hint)}</div>')
        parts.append(f"<figcaption>图 {index} · {esc(caption)}</figcaption>")
        parts.append("</figure>")

    parts.append("</div>")

    footer = request.footer.strip()
    contact = request.contact.strip()
    if footer or contact:
        parts.append('<footer class="poster-foot">')
        parts.append(f"<span>{esc(footer)}</span>")
        parts.append(f"<span>{esc(contact)}</span>")
        parts.append("</footer>")

    parts.extend(["</div>", "</body>", "</html>"])
    return "\n".join(parts)


class PosterService:
    """把填好的内容变成一页可打印的海报。"""

    def build(self, request: PosterRequest) -> PosterPlan:
        key = (request.size or "a0").strip().lower()
        width, height, label = SIZES.get(key, SIZES["a0"])
        resolved_size = key if key in SIZES else "a0"

        columns = 3 if width >= 560 else 2
        fonts = _font_plan(width, columns)
        checklist = _checklist(request)
        passed = sum(1 for item in checklist if item.passed)
        warnings = [f"{item.label}：{item.advice}" for item in checklist if not item.passed and item.level == "warn"]

        return PosterPlan(
            size=resolved_size,
            size_label=label,
            width_mm=width,
            height_mm=height,
            fonts=fonts,
            section_count=len(request.sections),
            figure_count=len(request.figures),
            word_count=_word_count(request),
            checklist=checklist,
            passed_count=passed,
            warnings=warnings,
            print_hint=PRINT_HINT,
            html=_render_html(request, fonts, width, height),
        )
