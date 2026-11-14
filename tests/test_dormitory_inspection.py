"""宿舍检查反馈与典型问题汇总的回归测试。

命题二要「宿舍检查反馈」和「典型问题汇总」，还特别写了「避免简单通报批评」。
所以这里要证明：每条反馈都带一个具体动作、没有分数排名、共性与个别能分开。
"""

import pytest

from zhihui_qilu.dormitory_models import (
    DimensionInput,
    DimensionState,
    InspectionDimension,
    InspectionRecord,
)
from zhihui_qilu.dormitory_service import DormitoryService


@pytest.fixture()
def service() -> DormitoryService:
    return DormitoryService()


def test_report_covers_all_five_dimensions(service: DormitoryService) -> None:
    """没填的维度按「良好」补齐，五项都要有话说，不留空。"""
    report = service.build_inspection_report("文渊楼 3-502", [])
    assert len(report.notes) == 5
    assert {note.label for note in report.notes} == {"卫生", "安全秩序", "作息规律", "关系调适", "文明习惯"}
    for note in report.notes:
        assert note.observation
        assert note.action


def test_issue_counts_and_summary(service: DormitoryService) -> None:
    """三项以上要动就提醒「先挑最影响生活的那一项」，别让人一次全改。"""
    report = service.build_inspection_report(
        "文渊楼 3-502",
        [
            DimensionInput(dimension=InspectionDimension.HYGIENE, state=DimensionState.ISSUE, note="阳台堆了纸箱"),
            DimensionInput(dimension=InspectionDimension.SAFETY, state=DimensionState.ISSUE, note="插排上床"),
            DimensionInput(dimension=InspectionDimension.SCHEDULE, state=DimensionState.ISSUE),
        ],
    )
    assert report.issue_count == 3
    assert "先挑最影响生活的那一项" in report.summary


def test_feedback_is_never_a_score_or_ranking(service: DormitoryService) -> None:
    """反馈里不能出现分数、排名、批评性字眼——命题二明说不做通报批评。"""
    report = service.build_inspection_report(
        "文渊楼 3-502",
        [DimensionInput(dimension=InspectionDimension.HYGIENE, state=DimensionState.ISSUE, note="地面有杂物")],
    )
    joined = report.summary + report.encouragement + "".join(note.feedback + note.action for note in report.notes)
    for banned in ("扣分", "排名", "通报", "批评", "不合格", "警告"):
        assert banned not in joined


def test_observation_note_is_kept(service: DormitoryService) -> None:
    """辅导员写的现场观察要原样带回，不能被通用话术顶掉。"""
    report = service.build_inspection_report(
        "文渊楼 3-502",
        [DimensionInput(dimension=InspectionDimension.SAFETY, state=DimensionState.WATCH, note="插排放在床头")],
    )
    safety = next(note for note in report.notes if note.dimension is InspectionDimension.SAFETY)
    assert safety.observation == "插排放在床头"
    assert safety.state is DimensionState.WATCH


def test_strengths_default_to_good_dimensions(service: DormitoryService) -> None:
    """没手写亮点时，用「保持得住」的维度顶上，不留空数组。"""
    report = service.build_inspection_report(
        "文渊楼 3-502",
        [DimensionInput(dimension=InspectionDimension.HYGIENE, state=DimensionState.ISSUE)],
    )
    assert report.strengths
    assert all("保持得住" in item for item in report.strengths)


def test_digest_splits_common_and_isolated(service: DormitoryService) -> None:
    """4 个宿舍里 3 个卫生有问题 = 共性；1 个作息有问题 = 个别隐患。"""
    records = [
        InspectionRecord(dormitory_label="3-501", dimensions={"hygiene": "issue"}),
        InspectionRecord(dormitory_label="3-502", dimensions={"hygiene": "issue"}),
        InspectionRecord(dormitory_label="3-503", dimensions={"hygiene": "watch"}),
        InspectionRecord(dormitory_label="3-504", dimensions={"schedule": "issue"}),
    ]
    digest = service.summarize_issues(records)

    assert digest.total_dorms == 4
    common_labels = [item.label for item in digest.common_issues]
    isolated_labels = [item.label for item in digest.isolated_issues]
    assert common_labels == ["卫生"]
    assert isolated_labels == ["作息规律"]
    assert digest.common_issues[0].share == 75


def test_digest_without_records_is_honest(service: DormitoryService) -> None:
    """没有记录就直说没有，不编造共性问题。"""
    digest = service.summarize_issues([])
    assert digest.total_dorms == 0
    assert digest.common_issues == []
    assert "还没有检查记录" in digest.summary


def test_digest_says_so_when_nothing_needs_attention(service: DormitoryService) -> None:
    """全部良好时不能硬凑问题出来。"""
    records = [
        InspectionRecord(dormitory_label="3-501", dimensions={"hygiene": "good"}),
        InspectionRecord(dormitory_label="3-502", dimensions={"hygiene": "good"}),
    ]
    digest = service.summarize_issues(records)
    assert digest.common_issues == []
    assert digest.isolated_issues == []
    assert "都没有需要提醒的项" in digest.summary
