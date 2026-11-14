"""学术海报生成（定向命题六）的回归测试。

命题六要「一键生成学术海报」。这里证明三件事：
排版会随纸张尺寸等比缩放、内容体检说得出问题在哪、生成的 HTML 能离线打印。
"""

import asyncio

from zhihui_qilu.core.models import AgentRequest, RequestContext
from zhihui_qilu.poster_models import PosterFigure, PosterRequest, PosterSection
from zhihui_qilu.poster_service import PRINT_HINT, PosterService
from zhihui_qilu.skills.poster import PosterSkill


def _sample(**overrides) -> PosterRequest:
    data = dict(
        title="面向校园场景的多智能体协同助手",
        authors="张三、李四",
        affiliation="山东师范大学 信息科学与工程学院",
        contact="zhangsan@sdnu.edu.cn",
        keywords=["多智能体", "校园服务", "可解释"],
        sections=[
            PosterSection(heading="背景与问题", body="校园服务分散在十几个系统里。"),
            PosterSection(heading="方法", body="技能底座 + 安全网关 + 记忆层。", bullets=["技能可插拔", "动作有边界"]),
            PosterSection(heading="结论", body="五类事务在一个入口完成。"),
        ],
        figures=[PosterFigure(caption="系统结构")],
        size="a0",
    )
    data.update(overrides)
    return PosterRequest(**data)


def test_builds_a_complete_a0_poster() -> None:
    """A0 竖版：尺寸、栏数、字号都要对得上。"""
    plan = PosterService().build(_sample())

    assert plan.size == "a0"
    assert (plan.width_mm, plan.height_mm) == (841, 1189)
    assert plan.fonts.columns == 3
    assert plan.fonts.title_pt == 84
    assert plan.fonts.body_pt == 28
    assert plan.section_count == 3
    assert plan.figure_count == 1


def test_fonts_scale_down_with_paper_size() -> None:
    """换小纸不重排：字号按宽度等比缩，A3 明显小于 A0。"""
    service = PosterService()
    a0 = service.build(_sample(size="a0"))
    a3 = service.build(_sample(size="a3"))

    assert a3.width_mm == 297
    assert a3.fonts.columns == 2
    assert a3.fonts.title_pt < a0.fonts.title_pt
    assert a3.fonts.body_pt < a0.fonts.body_pt
    assert a3.fonts.body_pt >= 8  # 再小就印不出来了


def test_unknown_size_falls_back_to_a0() -> None:
    """尺寸写错不该报错，退回 A0 就行——现场别因为一个下拉框卡住。"""
    plan = PosterService().build(_sample(size="b9"))
    assert plan.size == "a0"
    assert plan.width_mm == 841


def test_page_rule_matches_chosen_size() -> None:
    """@page 必须写死真实尺寸，否则浏览器打印会缩放。"""
    plan = PosterService().build(_sample(size="a1"))
    assert "@page { size: 594mm 841mm; margin: 0; }" in plan.html


def test_html_is_self_contained_and_offline() -> None:
    """不引外部字体、不引外部图片、不 @import——断网也要能打印。"""
    html = PosterService().build(_sample()).html

    assert "@import" not in html
    assert "<img" not in html
    assert "http://" not in html
    assert "https://" not in html


def test_user_text_is_escaped() -> None:
    """标题里带尖括号不能变成标签，否则生成的页面会被注入。"""
    plan = PosterService().build(_sample(title='<script>alert(1)</script> 海报'))

    assert "<script>alert(1)</script>" not in plan.html
    assert "&lt;script&gt;" in plan.html


def test_multiline_body_becomes_paragraphs() -> None:
    """表单里换行就是分段，渲染时不能糊成一段。"""
    plan = PosterService().build(
        _sample(sections=[PosterSection(heading="结论", body="第一段。\n第二段。")])
    )
    assert plan.html.count("<p>") >= 2
    assert "第一段。" in plan.html
    assert "第二段。" in plan.html


def test_checklist_flags_missing_conclusion() -> None:
    """没有结论栏是海报最常见的硬伤，必须点名。"""
    plan = PosterService().build(
        _sample(
            sections=[
                PosterSection(heading="背景", body="甲。"),
                PosterSection(heading="方法", body="乙。"),
                PosterSection(heading="结果", body="丙。"),
            ]
        )
    )
    item = next(entry for entry in plan.checklist if entry.id == "has_conclusion")
    assert item.passed is False
    assert "结论" in item.advice
    assert any("结论" in warning for warning in plan.warnings)


def test_checklist_flags_overlong_title_and_body() -> None:
    """标题太长、单栏正文太长都要提醒，并给出改成什么样。"""
    plan = PosterService().build(
        _sample(title="很长" * 40, sections=[PosterSection(heading="结论", body="正文" * 300)])
    )
    ids = {entry.id for entry in plan.checklist if not entry.passed}
    assert "title_length" in ids
    assert "body_length" in ids


def test_clean_poster_passes_most_checks() -> None:
    """规范填写的样例应该大部分通过，否则体检就成了噪声。"""
    plan = PosterService().build(_sample())
    assert plan.passed_count >= len(plan.checklist) - 1
    assert plan.warnings == []


def test_print_hint_tells_how_to_make_pdf() -> None:
    """生成的下一步是「存成 PDF」，这句话要直接给出来。"""
    plan = PosterService().build(_sample())
    assert plan.print_hint == PRINT_HINT
    assert "另存为 PDF" in plan.print_hint
    assert "边距" in plan.print_hint


def test_skill_builds_from_payload() -> None:
    """Skill 层要能吃前端传来的整块 poster 对象。"""
    skill = PosterSkill()
    request = AgentRequest(
        capability="poster",
        payload={"action": "build_poster", "poster": _sample().model_dump(mode="json")},
        context=RequestContext(user_id="u1", session_id="s1"),
    )
    response = asyncio.run(skill.execute(request))

    assert response.success is True
    assert response.data["size"] == "a0"
    assert "<!doctype html>" in response.data["html"]


def test_skill_rejects_empty_sections() -> None:
    """一栏都没有就不该生成，否则出来的是一张空白海报。"""
    skill = PosterSkill()
    payload = _sample().model_dump(mode="json")
    payload["sections"] = []
    request = AgentRequest(
        capability="poster",
        payload={"action": "build_poster", "poster": payload},
        context=RequestContext(user_id="u1", session_id="s1"),
    )
    response = asyncio.run(skill.execute(request))

    assert response.success is False
    assert "至少写一栏" in response.message
