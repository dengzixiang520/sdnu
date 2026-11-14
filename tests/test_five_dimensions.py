"""五育积分映射的回归测试。

教育部要求「德智体美劳全要素横向评价」，这里证明三件事：
来源说明里的关键词能正确归类、认不出的不硬塞、空数据不编造分布。
"""

import json
from pathlib import Path

import pytest

from zhihui_qilu.points_service import FIVE_DIMENSIONS, PointsService


@pytest.fixture()
def service(tmp_path: Path) -> PointsService:
    """用临时目录起一个干净的积分服务，不碰 data/ 里的演示数据。"""
    (tmp_path / "points.json").write_text("[]", encoding="utf-8")
    (tmp_path / "points_records.json").write_text("[]", encoding="utf-8")
    (tmp_path / "exchange_products.json").write_text("[]", encoding="utf-8")
    (tmp_path / "exchange_records.json").write_text("[]", encoding="utf-8")
    return PointsService(tmp_path)


def seed(service: PointsService, rows: list[dict]) -> None:
    """直接写记录文件，跳过加分逻辑，专测归类。"""
    path = service._records_file  # noqa: SLF001 - 测试直接铺数据，比走加分逻辑更快也更稳
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def test_five_dimensions_cover_the_policy_words() -> None:
    """五育的标签必须是政策原话里的五个字。"""
    assert [item[1] for item in FIVE_DIMENSIONS] == ["德", "智", "体", "美", "劳"]


def test_checkin_goes_to_de(service: PointsService) -> None:
    """每日打卡归德育：坚持本身就是自我管理。"""
    seed(service, [{"user_id": "u1", "points": 5, "source": "checkin", "source_detail": "每日打卡", "created_at": "2026-11-01T09:00:00"}])
    summary = service.get_five_dimension_summary("u1")
    de = next(item for item in summary["dimensions"] if item["label"] == "德")
    assert de["points"] == 5
    assert summary["total"] == 5


def test_competition_goes_to_zhi(service: PointsService) -> None:
    """竞赛获奖归智育。"""
    seed(service, [{"user_id": "u1", "points": 60, "source": "competition", "source_detail": "数学建模 - A3", "created_at": "2026-11-01T09:00:00"}])
    summary = service.get_five_dimension_summary("u1")
    zhi = next(item for item in summary["dimensions"] if item["label"] == "智")
    assert zhi["points"] == 60


def test_keywords_override_source_default(service: PointsService) -> None:
    """activity 默认归德育，但说明里写了「体育」就该进体育。"""
    seed(
        service,
        [
            {"user_id": "u1", "points": 10, "source": "activity", "source_detail": "校园体育打卡", "created_at": "2026-11-01T09:00:00"},
            {"user_id": "u1", "points": 8, "source": "activity", "source_detail": "合唱演出", "created_at": "2026-11-02T09:00:00"},
            {"user_id": "u1", "points": 6, "source": "activity", "source_detail": "宿舍值日", "created_at": "2026-11-03T09:00:00"},
        ],
    )
    summary = service.get_five_dimension_summary("u1")
    points = {item["label"]: item["points"] for item in summary["dimensions"]}
    assert points["体"] == 10
    assert points["美"] == 8
    assert points["劳"] == 6
    assert points["德"] == 0


def test_unknown_source_is_not_forced(service: PointsService) -> None:
    """认不出的来源进「未归类」，不硬塞进某一育。"""
    seed(service, [{"user_id": "u1", "points": 20, "source": "mystery", "source_detail": "", "created_at": "2026-11-01T09:00:00"}])
    summary = service.get_five_dimension_summary("u1")
    assert summary["unclassified"] == 20
    assert summary["unclassified_share"] == 100
    assert all(item["points"] == 0 for item in summary["dimensions"])


def test_summary_names_thinnest_dimension(service: PointsService) -> None:
    """摘要要点出最薄的一育，并说从哪儿补。"""
    seed(service, [{"user_id": "u1", "points": 50, "source": "competition", "source_detail": "竞赛获奖", "created_at": "2026-11-01T09:00:00"}])
    summary = service.get_five_dimension_summary("u1")
    assert "智" in summary["summary"]
    assert "还是 0 分" in summary["summary"]


def test_empty_records_say_so(service: PointsService) -> None:
    """没有任何积分时不能编造分布。"""
    summary = service.get_five_dimension_summary("nobody")
    assert summary["total"] == 0
    assert "还没有积分记录" in summary["summary"]
    assert all(item["share"] == 0 for item in summary["dimensions"])


def test_other_users_are_excluded(service: PointsService) -> None:
    """只统计本人，别人的积分不能混进来。"""
    seed(
        service,
        [
            {"user_id": "u1", "points": 10, "source": "checkin", "source_detail": "每日打卡", "created_at": "2026-11-01T09:00:00"},
            {"user_id": "u2", "points": 99, "source": "competition", "source_detail": "竞赛", "created_at": "2026-11-01T09:00:00"},
        ],
    )
    summary = service.get_five_dimension_summary("u1")
    assert summary["total"] == 10
