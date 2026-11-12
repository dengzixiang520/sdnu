"""学习计划服务：把一个大目标拆成可执行的一周。

三条设计约束：

1. **结构由服务端保证，模型只负责措辞**。模型返回的 JSON 一律当不可信输入，
   先过 Pydantic，再按时间预算裁剪，最后才交给前端渲染。
2. **断网也能用**。模型不可用、超时、返回的不是 JSON 时，回落到确定性模板，
   答辩现场不会出现空白页。
3. **计划要能被推翻**。用户勾掉/漏掉任务后，用 ``adjust`` 只重排剩下的几天，
   而不是让他从头再生成一遍。
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from zhihui_qilu.ai.provider import ChatMessage, LanguageModelProvider, ProviderUnavailableError

_WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
_JSON_BLOCK = re.compile(r"\{.*\}", re.S)
_KINDS = {"focus", "drill", "review"}
_KIND_LABEL = {"focus": "推进", "drill": "练手", "review": "复盘"}


class PlanRequest(BaseModel):
    """生成一周计划需要的最小上下文。"""

    goal: str = Field(min_length=1, max_length=200)
    hours_per_week: int = Field(default=12, ge=1, le=60)
    major: str = Field(default="", max_length=40)
    deadline: str = Field(default="", max_length=40)
    weak_points: str = Field(default="", max_length=300)
    start_date: date | None = None


class RemainingDay(BaseModel):
    """前端回传的剩余日期，保留原始星期与日期文案。"""

    day: str = Field(min_length=1, max_length=10)
    date: str = Field(default="", max_length=10)


class AdjustRequest(BaseModel):
    """按真实完成情况重排剩下的几天。"""

    goal: str = Field(min_length=1, max_length=200)
    hours_per_week: int = Field(default=12, ge=1, le=60)
    remaining: list[RemainingDay] = Field(default_factory=list, max_length=7)
    done_titles: list[str] = Field(default_factory=list, max_length=40)
    missed_titles: list[str] = Field(default_factory=list, max_length=40)
    note: str = Field(default="", max_length=200)


class PlanTask(BaseModel):
    """一个能在连续时间里做完的具体动作。"""

    title: str = Field(min_length=1, max_length=80)
    minutes: int = Field(ge=5, le=300)
    kind: str = Field(default="focus", max_length=20)

    @property
    def kind_label(self) -> str:
        return _KIND_LABEL.get(self.kind, "推进")


class PlanDay(BaseModel):
    """一天的计划：一个主题 + 若干任务。"""

    day: str
    date: str
    focus: str
    minutes: int
    tasks: list[PlanTask]


class StudyPlan(BaseModel):
    """一整周（或剩余几天）的计划，附带自检标准与来源标记。"""

    goal: str
    week_start: str
    week_end: str
    total_minutes: int
    summary: str
    days: list[PlanDay]
    checkpoint: str
    source: Literal["model", "offline"]


class StudyPlanService:
    """调用大模型排一周，失败时回落到确定性模板。"""

    _SYSTEM = (
        "你是山东师范大学的学业规划助理，服务对象是要备考或做项目的大学生。"
        "你只输出一个 JSON 对象，不要 Markdown 代码块，不要任何解释文字。"
        '结构：{"summary":"一句话说明这周的主线",'
        '"checkpoint":"周日自检的可验证标准",'
        '"days":[{"day":"周一","date":"11-12","focus":"当天主题",'
        '"tasks":[{"title":"可执行动作","minutes":45,"kind":"focus"}]}]}。'
        "硬性要求："
        "① 每个 title 必须是能在一段连续时间里做完的具体动作，例如“读完第 3 章并手写 5 个名词解释”，"
        "禁止“努力学习”“认真复习”“加强练习”这类无法执行的表述；"
        "② 每天 1–3 个 task；"
        "③ minutes 是 15 的倍数，单条 15–180；"
        "④ kind 只能是 focus（推进主线）、drill（刷题练手）、review（复盘巩固）之一；"
        "⑤ day 和 date 必须照抄用户给出的顺序，不得增删日期。"
    )

    #: 一周的强度权重，周末略高一点，因为白天没有课。
    _WEIGHTS = (1.0, 1.0, 1.0, 1.0, 1.0, 1.4, 1.4)

    def __init__(self, provider: LanguageModelProvider) -> None:
        self._provider = provider

    @property
    def available(self) -> bool:
        """模型是否配置了真实推理能力。"""
        return self._provider.available

    async def generate(self, request: PlanRequest) -> StudyPlan:
        """从今天起排 7 天；模型失败时静默回落到模板。"""
        slots = self._slots(request.start_date or date.today())
        budget = request.hours_per_week * 60
        try:
            return await self._from_model(request, slots, budget)
        except (ProviderUnavailableError, ValueError):
            return self._from_template(request, slots, budget)

    async def adjust(self, request: AdjustRequest) -> StudyPlan:
        """只重排剩余几天，把已完成和漏掉的任务当作输入条件。"""
        if not request.remaining:
            raise ValueError("没有需要重排的日期")
        slots = [
            (item.day, item.date, item.day in {"周六", "周日"})
            for item in request.remaining
        ]
        budget = max(60, int(request.hours_per_week * 60 * len(slots) / 7))
        try:
            return await self._from_model(request, slots, budget, adjusting=True)
        except (ProviderUnavailableError, ValueError):
            return self._from_template(request, slots, budget, adjusting=True)

    # ------------------------------------------------------------------ 模型

    async def _from_model(
        self,
        request: PlanRequest | AdjustRequest,
        slots: list[tuple[str, str, bool]],
        budget: int,
        *,
        adjusting: bool = False,
    ) -> StudyPlan:
        messages = [
            ChatMessage(role="system", content=self._SYSTEM),
            ChatMessage(role="user", content=self._user_prompt(request, slots, budget, adjusting=adjusting)),
        ]
        raw = await self._provider.complete(messages, temperature=0.7)
        return self._normalise(request, slots, budget, self._load_json(raw), "model")

    @staticmethod
    def _load_json(raw: str) -> dict[str, object]:
        """从可能带代码围栏或前后废话的回复里抠出第一个 JSON 对象。"""
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text).strip()
        match = _JSON_BLOCK.search(text)
        if match is None:
            raise ValueError("模型没有返回 JSON")
        payload = json.loads(match.group(0))
        if not isinstance(payload, dict):
            raise ValueError("模型返回的 JSON 不是对象")
        return payload

    @staticmethod
    def _user_prompt(
        request: PlanRequest | AdjustRequest,
        slots: list[tuple[str, str, bool]],
        budget: int,
        *,
        adjusting: bool = False,
    ) -> str:
        lines = [f"目标：{request.goal}", f"可投入总时长：{budget} 分钟"]
        if isinstance(request, PlanRequest):
            if request.major:
                lines.append(f"专业方向：{request.major}")
            if request.deadline:
                lines.append(f"关键节点：{request.deadline}")
            if request.weak_points:
                lines.append(f"薄弱环节：{request.weak_points}")
        else:
            if request.done_titles:
                lines.append("已完成：" + "；".join(request.done_titles[:8]))
            if request.missed_titles:
                lines.append("还没做：" + "；".join(request.missed_titles[:8]))
            if request.note:
                lines.append(f"补充说明：{request.note}")
            lines.append("请只重排下面这些天，把没做完的内容压缩进剩余时间。")
        lines.append("必须覆盖这些日期，顺序与写法照抄：" + "、".join(f"{name}({text})" for name, text, _ in slots))
        lines.append("所有 task 的 minutes 之和不要超过可投入总时长。")
        return "\n".join(lines)

    # ---------------------------------------------------------------- 归一化

    def _normalise(
        self,
        request: PlanRequest | AdjustRequest,
        slots: list[tuple[str, str, bool]],
        budget: int,
        data: dict[str, object],
        source: Literal["model", "offline"],
    ) -> StudyPlan:
        """把模型输出对齐到真实日期槽位，缺哪天补哪天，超预算就等比压缩。"""
        entries = data.get("days")
        rows = [item for item in entries if isinstance(item, dict)] if isinstance(entries, list) else []
        by_name = {str(item.get("day", "")).strip(): item for item in rows if str(item.get("day", "")).strip()}

        days: list[PlanDay] = []
        for index, (name, date_text, is_weekend) in enumerate(slots):
            item = by_name.get(name)
            if item is None and index < len(rows):
                item = rows[index]
            item = item or {}
            tasks = self._tasks(item.get("tasks")) or self._fallback_tasks(request.goal, is_weekend)
            focus = str(item.get("focus", "")).strip() or f"{name}：推进「{request.goal}」"
            days.append(
                PlanDay(
                    day=name,
                    date=date_text,
                    focus=focus[:40],
                    minutes=sum(task.minutes for task in tasks),
                    tasks=tasks,
                )
            )

        days = self._fit_budget(days, budget)
        total = sum(day.minutes for day in days)
        summary = str(data.get("summary", "")).strip() or self._default_summary(request, total, len(days))
        checkpoint = str(data.get("checkpoint", "")).strip() or self._default_checkpoint(request.goal)
        return StudyPlan(
            goal=request.goal,
            week_start=slots[0][1],
            week_end=slots[-1][1],
            total_minutes=total,
            summary=summary[:120],
            days=days,
            checkpoint=checkpoint[:200],
            source=source,
        )

    @staticmethod
    def _tasks(raw: object) -> list[PlanTask]:
        """校验单日任务：丢掉空标题，时长取整到 15 分钟并夹到 15–240。"""
        items = raw if isinstance(raw, list) else []
        result: list[PlanTask] = []
        for item in items[:3]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            try:
                minutes = int(item.get("minutes", 45))
            except (TypeError, ValueError):
                minutes = 45
            minutes = max(15, min(240, minutes))
            minutes = max(15, int(round(minutes / 15.0)) * 15)
            kind = str(item.get("kind", "focus")).strip()
            result.append(
                PlanTask(
                    title=title[:80],
                    minutes=minutes,
                    kind=kind if kind in _KINDS else "focus",
                )
            )
        return result

    @staticmethod
    def _fit_budget(days: list[PlanDay], budget: int) -> list[PlanDay]:
        """超出可投入时间时先等比压缩；取整到 15 分钟后仍超，就继续削最大的那条任务。"""
        total = sum(day.minutes for day in days)
        if total <= budget or total <= 0:
            return days
        ratio = budget / total
        rows = [
            [
                task.model_copy(update={"minutes": max(15, int(round(task.minutes * ratio / 15.0)) * 15)})
                for task in day.tasks
            ]
            for day in days
        ]
        overflow = sum(task.minutes for row in rows for task in row) - budget
        while overflow >= 15:
            candidates = [
                (day_index, task_index)
                for day_index, row in enumerate(rows)
                for task_index, task in enumerate(row)
                if task.minutes > 15
            ]
            if not candidates:
                break
            day_index, task_index = max(candidates, key=lambda pair: rows[pair[0]][pair[1]].minutes)
            rows[day_index][task_index] = rows[day_index][task_index].model_copy(
                update={"minutes": rows[day_index][task_index].minutes - 15}
            )
            overflow -= 15
        return [
            day.model_copy(update={"tasks": row, "minutes": sum(task.minutes for task in row)})
            for day, row in zip(days, rows, strict=True)
        ]

    @staticmethod
    def _fallback_tasks(goal: str, is_weekend: bool) -> list[PlanTask]:
        """模型某天漏填时的兜底任务，仍然要求可执行。"""
        focus = 90 if is_weekend else 45
        return [
            PlanTask(title=f"推进「{goal}」的下一个具体小节", minutes=focus, kind="focus"),
            PlanTask(title="整理当天笔记，标出没弄懂的两处", minutes=15, kind="review"),
        ]

    # ---------------------------------------------------------------- 模板

    def _from_template(
        self,
        request: PlanRequest | AdjustRequest,
        slots: list[tuple[str, str, bool]],
        budget: int,
        *,
        adjusting: bool = False,
    ) -> StudyPlan:
        """确定性兜底：按权重把预算摊到每一天，75% 推进 + 25% 复盘。"""
        weights = [self._WEIGHTS[_WEEKDAYS.index(name)] if name in _WEEKDAYS else 1.0 for name, _, _ in slots]
        weight_total = sum(weights) or 1.0
        days: list[PlanDay] = []
        for index, (name, date_text, _) in enumerate(slots):
            share = budget * weights[index] / weight_total
            focus = max(15, int(round(share * 0.75 / 15.0)) * 15)
            review = max(15, int(round(share * 0.25 / 15.0)) * 15)
            tasks = [
                PlanTask(title=f"主攻：推进「{request.goal}」的下一个具体小节", minutes=focus, kind="focus"),
                PlanTask(title="复盘当天内容，整理错题或没弄懂的点", minutes=review, kind="review"),
            ]
            days.append(
                PlanDay(
                    day=name,
                    date=date_text,
                    focus=f"推进「{request.goal}」",
                    minutes=focus + review,
                    tasks=tasks,
                )
            )
        total = sum(day.minutes for day in days)
        summary = (
            f"只剩 {len(days)} 天，把没做完的部分压进可用时间，先保主线。"
            if adjusting
            else f"按每周 {request.hours_per_week} 小时的节奏推进「{request.goal}」，周末留出复盘时间。"
        )
        return StudyPlan(
            goal=request.goal,
            week_start=slots[0][1],
            week_end=slots[-1][1],
            total_minutes=total,
            summary=summary[:120],
            days=days,
            checkpoint=self._default_checkpoint(request.goal),
            source="offline",
        )

    @staticmethod
    def _default_summary(request: PlanRequest | AdjustRequest, total: int, day_count: int) -> str:
        hours = total / 60
        return f"{day_count} 天共 {hours:.1f} 小时，围绕「{request.goal}」推进，周末留出复盘。"

    @staticmethod
    def _default_checkpoint(goal: str) -> str:
        return f"周日用 20 分钟自检：不看资料能否说出「{goal}」的 3 个关键点；说不出来就写进下周一第一件事。"

    # ------------------------------------------------------------------ 工具

    @staticmethod
    def _slots(start: date) -> list[tuple[str, str, bool]]:
        """生成从 start 起 7 天的（星期、日期文案、是否周末）槽位。"""
        slots: list[tuple[str, str, bool]] = []
        for offset in range(7):
            current = start + timedelta(days=offset)
            slots.append((_WEEKDAYS[current.weekday()], current.strftime("%m-%d"), current.weekday() >= 5))
        return slots
