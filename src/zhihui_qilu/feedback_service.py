"""学生评价：这条回答到底有没有用，由学生说了算。

赛题把「用户评分」列进了评审维度，平台就必须真的收得到评价，而不是自己说好。
这里做两件事：

1. **记下来**。每次「有用 / 没用 + 一句话」都写进记忆系统，重启不丢，
   半年后自然过期，不占地方。
2. **算出来**。按评价对象聚合出有用率和条数，前端直接展示；
   后续要拿它做「同类问题优先推高评价的版本」，入口就在 ``summary`` 里。

刻意不做的事：不让人给别人的评价点赞，不做排行榜，不把差评挂出来羞辱谁。
评价只用来改进，不用来评比。
"""

from collections import Counter
from datetime import timedelta
from typing import Any

from zhihui_qilu.core.enums import AccessScope, MemoryTier
from zhihui_qilu.core.models import utc_now
from zhihui_qilu.memory.base import MemorySystem
from zhihui_qilu.memory.models import MemoryRecord

FEEDBACK_CATEGORY = "feedback"
# 评价留半年：够看趋势，又不至于把老数据当现状。
FEEDBACK_TTL_SECONDS = 60 * 60 * 24 * 180
# 一句话评价最多留 200 字，防止有人贴一整篇。
NOTE_MAX_CHARS = 200

# 能评价的对象。id 用稳定英文，名称给前端直接显示。
TARGETS: dict[str, str] = {
    "wellbeing_chat": "暖心对话",
    "interview_report": "复试评分报告",
    "doc_normalize": "公文规范化",
    "growth_note": "成长导言",
    "credit_warning": "学业预警自检",
    "proposal_outline": "竞赛申报大纲",
    "self_check": "四题自评",
    "timetable": "课表解析",
    "phishing_check": "钓鱼识别",
    "poster_plan": "学术海报",
}


class FeedbackService:
    """收集并聚合学生对各模块输出的评价。"""

    def __init__(self, memory: MemorySystem) -> None:
        self._memory = memory

    async def record(
        self,
        *,
        user_id: str,
        session_id: str,
        target: str,
        helpful: bool,
        note: str = "",
    ) -> dict[str, Any]:
        """记一条评价。目标必须是已知对象，避免前端写错字把数据写散。"""
        if target not in TARGETS:
            raise ValueError(f"不认识这个评价对象：{target}")
        cleaned = " ".join(note.split())[:NOTE_MAX_CHARS]
        record = MemoryRecord(
            user_id=user_id,
            session_id=session_id,
            tier=MemoryTier.LONG_TERM,
            category=FEEDBACK_CATEGORY,
            value={"target": target, "helpful": helpful, "note": cleaned},
            source_agent="feedback",
            access_scope=AccessScope.OWNER,
            expires_at=utc_now() + timedelta(seconds=FEEDBACK_TTL_SECONDS),
        )
        await self._memory.put(record)
        return {
            "record_id": str(record.record_id),
            "target": target,
            "target_name": TARGETS[target],
            "helpful": helpful,
        }

    async def summary(self) -> dict[str, Any]:
        """按对象聚合有用率。跨用户统计，只出数字，不出人名。"""
        records = await self._memory.query(
            category=FEEDBACK_CATEGORY,
            permitted_scopes=set(AccessScope),
        )
        rows = [item for item in records if not item.is_expired()]
        total = len(rows)
        helpful = sum(1 for item in rows if item.value.get("helpful"))

        buckets: dict[str, dict[str, Any]] = {}
        for item in rows:
            target = str(item.value.get("target", "unknown"))
            bucket = buckets.setdefault(
                target,
                {
                    "target": target,
                    "target_name": TARGETS.get(target, target),
                    "total": 0,
                    "helpful": 0,
                },
            )
            bucket["total"] += 1
            if item.value.get("helpful"):
                bucket["helpful"] += 1
        for bucket in buckets.values():
            bucket["rate"] = round(bucket["helpful"] / bucket["total"] * 100) if bucket["total"] else 0

        # 最近 5 条有文字的评价，给辅导员看「学生到底卡在哪」。
        notes = [str(item.value.get("note")) for item in rows if item.value.get("note")]
        targets_seen = Counter(str(item.value.get("target", "")) for item in rows)

        return {
            "total": total,
            "helpful": helpful,
            "rate": round(helpful / total * 100) if total else 0,
            "by_target": sorted(buckets.values(), key=lambda item: -item["total"]),
            "recent_notes": notes[-5:][::-1],
            "covered_targets": [target for target, _ in targets_seen.most_common() if target],
            "available_targets": [{"id": key, "name": name} for key, name in TARGETS.items()],
            "note": (
                "评价只用来改进输出，不进个人档案，也不会显示是谁打的分。"
                if total
                else "还没有人评价。学生给一次「有用 / 没用」，这里就会出现真实数字。"
            ),
        }
