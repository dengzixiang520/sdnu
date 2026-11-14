"""学术海报的输入与输出模型（定向命题六）。

命题六要「一键生成学术海报」。这里刻意不走「让模型画一张图」的路子：
海报是要打印出来贴墙上的，生成一张位图既不能改字，也不能保证 300dpi。
所以做成**结构化填表 → 生成可打印的 HTML → 浏览器另存为 PDF**，
每个字都在用户手里，改一个标点不用重新生成。
"""

from pydantic import BaseModel, Field


class PosterSection(BaseModel):
    """海报上的一个栏目。标题 + 一段正文 + 若干条要点。"""

    heading: str = Field(min_length=1, max_length=30)
    body: str = Field(default="", max_length=1200)
    bullets: list[str] = Field(default_factory=list, max_length=8)


class PosterFigure(BaseModel):
    """图表占位。海报必须有图，但生成阶段不替用户造数据。"""

    caption: str = Field(default="", max_length=80)
    hint: str = Field(default="在此处替换为你的图表", max_length=80)


class PosterRequest(BaseModel):
    """一次海报生成请求。"""

    title: str = Field(min_length=1, max_length=200)
    authors: str = Field(default="", max_length=120)
    affiliation: str = Field(default="", max_length=160)
    contact: str = Field(default="", max_length=120)
    keywords: list[str] = Field(default_factory=list, max_length=10)
    sections: list[PosterSection] = Field(default_factory=list, max_length=8)
    figures: list[PosterFigure] = Field(default_factory=list, max_length=6)
    size: str = Field(default="a0", max_length=8)
    footer: str = Field(default="", max_length=160)


class PosterFontPlan(BaseModel):
    """字号方案。按纸张宽度等比缩放，换尺寸不用重新排版。"""

    title_pt: int
    section_pt: int
    body_pt: int
    caption_pt: int
    columns: int


class PosterCheckItem(BaseModel):
    """体检项：过没过、为什么、怎么改。"""

    id: str
    label: str
    passed: bool
    advice: str
    level: str = "warn"


class PosterPlan(BaseModel):
    """生成结果。html 就是可以直接打印的那一页。"""

    size: str
    size_label: str
    width_mm: int
    height_mm: int
    fonts: PosterFontPlan
    section_count: int
    figure_count: int
    word_count: int
    checklist: list[PosterCheckItem]
    passed_count: int
    warnings: list[str]
    print_hint: str
    html: str
