"""针对本轮修复的回归测试。

覆盖四个曾经真实报错的路径：系统集成路由 500、辅导员预警查不到、课表文本解析错位、
DOCX 导出 500，以及积分兑换的错误记账与积分发放的越权。
"""

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from zhihui_qilu.api.app import create_app
from zhihui_qilu.api.routes.timetable import parse_text_content
from zhihui_qilu.config import Settings
from zhihui_qilu.core.enums import AccessScope, MemoryTier, UserRole
from zhihui_qilu.core.models import AgentRequest, RequestContext, utc_now
from zhihui_qilu.core.security import SecurityIsolationGateway
from zhihui_qilu.memory.in_memory import InMemoryMemorySystem
from zhihui_qilu.memory.models import MemoryRecord
from zhihui_qilu.memory.sqlite import SqliteMemorySystem
from zhihui_qilu.points_service import PointsService
from zhihui_qilu.skills.wellbeing import WellbeingSkill
from zhihui_qilu.wellbeing_models import HappyShareDraft, MoodCheckIn, MoodWeather
from zhihui_qilu.wellbeing_service import HappyShareRejected, WellbeingService

IDENTITY = {"X-User-Id": "u1", "X-Session-Id": "s1"}


def test_integration_dashboard_is_reachable() -> None:
    """container 必须持有 system_integration，否则集成面板整块 500。"""
    client = TestClient(create_app(Settings(environment="test")))
    response = client.get("/api/v1/integration/student/u1/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["student"]["student_id"] == "u1"


def test_counselor_sees_alerts_from_other_students() -> None:
    """预警按学生存储，辅导员必须能跨用户检索到，且看不到 reflection 原文。"""

    async def exercise() -> None:
        settings = Settings(environment="test")
        memory = InMemoryMemorySystem()
        service = WellbeingService(memory, SecurityIsolationGateway(settings), settings)
        await service.record_check_in("student-1", "s1", MoodCheckIn(weather=MoodWeather.STORMY, reflection="我有自残的想法"))

        skill = WellbeingSkill(service)
        request = AgentRequest(
            payload={"action": "list_alerts"},
            context=RequestContext(user_id="counselor-1", session_id="c1", role=UserRole.COUNSELOR),
        )
        result = await skill.execute(request)
        assert result.success is True
        alerts = result.data["alerts"]
        assert len(alerts) == 1
        assert alerts[0]["student_id"] == "student-1"
        assert alerts[0]["level"] == "red"
        assert "reflection" not in alerts[0]
        assert "自残" not in str(alerts[0])

    asyncio.run(exercise())


def test_cross_owner_query_never_widens_default_scope(tmp_path: Path) -> None:
    """user_id=None 是给授权员工用的；不显式传 scope 时仍只能看到 OWNER 记录。"""

    async def exercise() -> None:
        memory = SqliteMemorySystem(tmp_path / "memory.sqlite3")
        await memory.put(MemoryRecord(user_id="a", tier=MemoryTier.SHORT_TERM, category="note", value={"k": 1}))
        await memory.put(MemoryRecord(user_id="b", tier=MemoryTier.SHORT_TERM, category="alert", value={"k": 2}, access_scope=AccessScope.AUTHORIZED_STAFF))

        owner_only = await memory.query(user_id=None)
        assert [record.user_id for record in owner_only] == ["a"]

        staff_view = await memory.query(user_id=None, permitted_scopes={AccessScope.AUTHORIZED_STAFF})
        assert [record.user_id for record in staff_view] == ["b"]

    asyncio.run(exercise())


def test_timetable_text_keeps_course_name_in_title() -> None:
    """旧正则把 “:00-09:40” 当课程名、把课程名当地点，这里锁死正确切分。"""
    events = parse_text_content("周一 08:00-09:40 高等数学 A101 张教授\n周二 1-2节 数据结构 B202 李老师")
    assert len(events) == 2

    first = events[0]
    assert first["title"] == "高等数学"
    assert first["location"] == "A101"
    assert first["teacher"] == "张教授"
    assert first["day_of_week"] == "周一"
    assert first["starts_at"] == "2026-09-01T08:00:00"
    assert first["ends_at"] == "2026-09-01T09:40:00"

    second = events[1]
    assert second["title"] == "数据结构"
    assert second["day_of_week"] == "周二"
    assert second["starts_at"] == "2026-09-01T08:20:00"
    assert second["ends_at"] == "2026-09-01T09:55:00"


def test_timetable_text_skips_unparsable_lines() -> None:
    """识别不出的行必须跳过，不能靠默认时刻伪造课程。"""
    assert parse_text_content("随便一行没有星期的文字") == []
    assert parse_text_content("周一 高等数学 A101") == []


def test_docx_export_returns_a_real_file() -> None:
    """临时文件必须活到响应发送完成，否则下载 500。"""
    client = TestClient(create_app(Settings(environment="test")))
    response = client.post("/api/v1/documents/export-docx", json={"title": "关于测试的通知", "body": "请各单位按时完成。"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument")
    assert response.content[:2] == b"PK"
    assert len(response.content) > 1000


def _seed_products(data_dir: Path) -> None:
    """兑换商品属于部署数据，不是代码；测试自己播种，避免依赖仓库里的 ./data。"""
    (data_dir / "exchange_products.json").write_text(
        """[
  {"id": "prod-001", "name": "定制书签", "description": "", "category": "实物奖品",
   "points": 50, "stock": 3, "image": "x", "location": "学生事务中心"},
  {"id": "prod-009", "name": "优先选课资格", "description": "", "category": "优先权益",
   "points": 500, "stock": 1, "image": "x", "location": "教务系统"}
]""",
        encoding="utf-8",
    )


def test_exchange_only_reduces_total_points(tmp_path: Path) -> None:
    """兑换属于消费：总分下降，三个贡献分类都不应该被反向增加。"""
    service = PointsService(tmp_path)
    _seed_products(tmp_path)
    service.add_points("u1", "同学", 100, "competition", "测试竞赛")
    before = service.get_user_points("u1")
    assert before is not None and before["total_points"] == 100

    result = service.exchange_product("u1", "同学", "prod-001")
    assert result["success"] is True

    after = service.get_user_points("u1")
    assert after is not None
    assert after["total_points"] == 50
    assert after["competition_points"] == 100
    assert after["checkin_points"] == 0
    assert after["activity_points"] == 0

    # 兑换流水单独记录，且带上成本
    exchanges = service.get_user_exchanges("u1")
    assert len(exchanges) == 1
    assert exchanges[0]["points_cost"] == 50


def test_exchange_rejects_insufficient_points_without_touching_stock(tmp_path: Path) -> None:
    """积分不足时不得扣库存，也不得留下流水。"""
    service = PointsService(tmp_path)
    _seed_products(tmp_path)
    service.add_points("u1", "同学", 10, "checkin", "打卡")
    stock_before = {item["id"]: item["stock"] for item in service.get_exchange_products()}

    result = service.exchange_product("u1", "同学", "prod-009")
    assert result["success"] is False
    assert "积分不足" in result["error"]

    stock_after = {item["id"]: item["stock"] for item in service.get_exchange_products()}
    assert stock_before == stock_after
    assert service.get_user_exchanges("u1") == []


def test_manual_points_require_administrator() -> None:
    """学生不能给自己加分；权限在进入服务层之前就被挡住。"""
    client = TestClient(create_app(Settings(environment="test")))
    response = client.post(
        "/api/v1/points/add",
        headers={**IDENTITY, "X-User-Role": "student"},
        json={"user_id": "u1", "points": 9999, "source": "activity"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# 开心分享墙：公开可见的积极内容，与私密心情打卡分开
# ---------------------------------------------------------------------------


def test_happy_share_is_public_while_checkin_stays_owner_scoped() -> None:
    """分享用 PUBLIC 作用域、打卡用 OWNER 作用域；两者不能互相串读。"""

    async def exercise() -> None:
        settings = Settings(environment="test")
        memory = InMemoryMemorySystem()
        service = WellbeingService(memory, SecurityIsolationGateway(settings), settings)
        await service.record_check_in("student-1", "s1", MoodCheckIn(weather=MoodWeather.SUNNY, reflection="只给自己看"))
        await service.publish_happy_share(
            "student-1", "s1", "小明", HappyShareDraft(content="今天看到粉色晚霞")
        )

        # 另一个学生用默认 OWNER 作用域查不到任何分享
        owner_only = await memory.query(user_id=None, tier=MemoryTier.LONG_TERM)
        assert owner_only == []

        shares = await service.list_happy_shares()
        assert len(shares) == 1
        assert shares[0].content == "今天看到粉色晚霞"
        assert shares[0].visibility == "public"

        # 分享墙里绝不能出现打卡的反思原文
        assert all("只给自己看" not in share.content for share in shares)

    asyncio.run(exercise())


def test_happy_share_gate_rejects_negative_and_crisis_content() -> None:
    """积极度闸门是确定性规则，不经过大模型；拒绝时给出可执行的去处。"""

    async def exercise() -> None:
        settings = Settings(environment="test")
        memory = InMemoryMemorySystem()
        service = WellbeingService(memory, SecurityIsolationGateway(settings), settings)

        with pytest.raises(HappyShareRejected) as negative:
            await service.publish_happy_share(
                "student-1", "s1", "小明", HappyShareDraft(content="今天好难过，想哭")
            )
        assert negative.value.redirect == "checkin"

        with pytest.raises(HappyShareRejected) as crisis:
            await service.publish_happy_share(
                "student-1", "s1", "小明", HappyShareDraft(content="我不想活了")
            )
        assert crisis.value.redirect == "support"
        assert "12356" in crisis.value.message

        # 被拒绝的草稿不落库
        assert await service.list_happy_shares() == []

    asyncio.run(exercise())


def test_happy_share_anonymous_and_cheer() -> None:
    """匿名发布隐藏真实姓名；鼓励计数会持久化到同一条记录上。"""

    async def exercise() -> None:
        settings = Settings(environment="test")
        memory = InMemoryMemorySystem()
        service = WellbeingService(memory, SecurityIsolationGateway(settings), settings)
        share = await service.publish_happy_share(
            "student-1", "s1", "真实姓名", HappyShareDraft(content="食堂新菜好吃", anonymous=True)
        )
        assert share.author_name == "匿名同学"

        cheered = await service.cheer_happy_share(str(share.share_id))
        assert cheered is not None and cheered.cheer_count == 1
        # 重新读一遍，确认计数不是只改了内存里的副本
        reloaded = await service.list_happy_shares()
        assert reloaded[0].cheer_count == 1

        assert await service.cheer_happy_share("00000000-0000-0000-0000-000000000000") is None

    asyncio.run(exercise())


def test_happy_share_actions_are_reachable_through_the_skill() -> None:
    """前端只走 /api/v1/commands，因此三个动作必须挂在 Skill 上。"""
    client = TestClient(create_app(Settings(environment="test")))

    published = client.post(
        "/api/v1/commands",
        headers=IDENTITY,
        json={
            "capability": "wellbeing",
            "action": "publish_happy_share",
            "text": "",
            "payload": {"author_name": "小明", "share": {"content": "答辩过了"}},
        },
    )
    assert published.status_code == 200
    body = published.json()
    assert body["success"] is True
    share_id = body["data"]["share"]["share_id"]

    listed = client.post(
        "/api/v1/commands",
        headers=IDENTITY,
        json={"capability": "wellbeing", "action": "happy_shares", "text": "", "payload": {}},
    )
    assert listed.json()["data"]["shares"][0]["share_id"] == share_id

    cheered = client.post(
        "/api/v1/commands",
        headers=IDENTITY,
        json={"capability": "wellbeing", "action": "cheer_happy_share", "text": "", "payload": {"share_id": share_id}},
    )
    assert cheered.json()["data"]["share"]["cheer_count"] == 1

    rejected = client.post(
        "/api/v1/commands",
        headers=IDENTITY,
        json={
            "capability": "wellbeing",
            "action": "publish_happy_share",
            "text": "",
            "payload": {"share": {"content": "压力大，好烦"}},
        },
    )
    assert rejected.json()["success"] is False
    assert rejected.json()["data"]["redirect"] == "checkin"
