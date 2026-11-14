"""Task 2 services: warm guidance, check-ins, privacy-safe alerts, and counselor tools."""

from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import uuid4

from pydantic import ValidationError

from zhihui_qilu.config import Settings
from zhihui_qilu.core.enums import AccessScope, MemoryTier, SensitivityLevel
from zhihui_qilu.core.models import utc_now
from zhihui_qilu.core.security import SecurityIsolationGateway
from zhihui_qilu.memory.base import MemorySystem
from zhihui_qilu.memory.models import MemoryRecord
from zhihui_qilu.wellbeing_models import (
    AlertLevel,
    AmbientTrack,
    CounselorAlert,
    GuideControlCommand,
    HappyShare,
    HappyShareDraft,
    MoodCheckIn,
    MoodCheckInResult,
    MoodWeather,
    TalkLedgerEntry,
    TalkLedgerInput,
    WallMessage,
)


class HappyShareRejected(Exception):
    """Raised when a draft does not pass the deterministic positivity gate.

    ``redirect`` tells the UI which safer surface to point the student at: ``support``
    for high-risk language (crisis path) and ``checkin`` for ordinary bad days.
    """

    def __init__(self, message: str, redirect: str) -> None:
        super().__init__(message)
        self.message = message
        self.redirect = redirect


class WellbeingService:
    """Implements non-diagnostic wellbeing workflows on the platform memory boundary."""

    _HIGH_RISK_TERMS = ("自杀", "自殘", "自残", "结束生命", "不想活", "suicide", "kill myself")
    _NEGATIVE_WEATHER = {MoodWeather.RAINY, MoodWeather.STORMY}

    #: 心情不好时的疏导动作库。分三组，每组都能落到一个具体动作上：
    #: 出口（把情绪放出来）、身体（先让身体松）、不用动脑（把注意力从反刍里挪开）。
    #: ``target`` 对应前端可跳转的锚点，空字符串表示不需要跳转、直接去做。
    _SOOTHE_GROUPS: tuple[tuple[str, str, tuple[dict[str, str], ...]], ...] = (
        (
            "outlet",
            "给情绪找个出口",
            (
                {
                    "id": "outlet-talk",
                    "title": "找个人说出来",
                    "detail": "挑一个不用你解释前因后果的人，说十分钟就够。",
                    "why": "情绪越压反弹越强，先让它出来，才有缓解的余地。",
                    "target": "chat",
                },
                {
                    "id": "outlet-journal",
                    "title": "写下来，不用给任何人看",
                    "detail": "打开下面「只写给自己」，写三行，写不通顺也算。",
                    "why": "写出来会把一团模糊的难受，变成看得见的几件事。",
                    "target": "journal",
                },
                {
                    "id": "outlet-cry",
                    "title": "想哭就哭一场",
                    "detail": "找个不被打扰的地方，不用忍着，也不用为哭找理由。",
                    "why": "哭是身体的减压反应，不是软弱，也不需要被批准。",
                    "target": "",
                },
            ),
        ),
        (
            "body",
            "先让身体松下来",
            (
                {
                    "id": "body-walk",
                    "title": "出门快走或慢跑 15 分钟",
                    "detail": "不用换运动服，绕操场或宿舍楼走一圈都算。",
                    "why": "有节奏的走动能让绷紧的身体先松下来，脑子跟着慢。",
                    "target": "",
                },
                {
                    "id": "body-sun",
                    "title": "去晒 10 分钟太阳",
                    "detail": "下午四点前后光最好，站楼底下就行，不用专门去公园。",
                    "why": "光照直接影响情绪调节，比坐在屋里反复想有用。",
                    "target": "",
                },
                {
                    "id": "body-ball",
                    "title": "打一场挥拍类运动",
                    "detail": "羽毛球、乒乓球都行，二十分钟就够。",
                    "why": "手上要追球的时候，反刍会自己停下来。",
                    "target": "",
                },
            ),
        ),
        (
            "idle",
            "做一件不用动脑的小事",
            (
                {
                    "id": "idle-tidy",
                    "title": "只整理一小块地方",
                    "detail": "收桌面，或者只叠衣服，不用收拾整个宿舍。",
                    "why": "手上在做具体的事，脑子会跟着安静下来。",
                    "target": "",
                },
                {
                    "id": "idle-shower",
                    "title": "洗个热水澡",
                    "detail": "水热一点，待久一点，不赶时间。",
                    "why": "身体暖起来，紧绷感会跟着退一截。",
                    "target": "",
                },
                {
                    "id": "idle-build",
                    "title": "拼点什么，或者做点手工",
                    "detail": "乐高、拼图、折纸、涂色都算。",
                    "why": "要一点手部专注但不用思考的事，最容易把人从反刍里拉出来。",
                    "target": "",
                },
                {
                    "id": "idle-sound",
                    "title": "听点不用动脑的声音",
                    "detail": "右栏「声音角落」里有钢琴和雨声，随手听就行。",
                    "why": "有声音填着，脑子就没那么容易被同一件事占满。",
                    "target": "music",
                },
            ),
        ),
    )

    # 开心分享墙的确定性闸门。刻意不使用大模型判定：与危机拦截同源，
    # 结果可复现、可解释，也不会把学生的原文发到外部服务。
    _SHARE_NEGATIVE_TERMS = (
        "难过", "伤心", "痛苦", "崩溃", "绝望", "焦虑", "抑郁", "烦躁", "好烦", "烦死",
        "讨厌", "想哭", "失眠", "压力大", "心累", "累死", "没意思", "不想上学", "不想上班",
        "失败", "被骂", "吵架", "分手", "孤独", "难受", "emo", "摆烂", "活着没劲",
    )
    _SHARE_CRISIS_MESSAGE = (
        "这条内容里有需要认真对待的信号，先不发布。"
        "请用「心情记录」写下此刻的状态，或直接拨打 24 小时心理援助热线 12356。"
    )
    _SHARE_NEGATIVE_MESSAGE = (
        "分享墙只收开心的事。今天如果不太好受，用「心情记录」写下来吧——"
        "那一条只有你和辅导员能看到，不会公开。"
    )

    def __init__(self, memory: MemorySystem, gateway: SecurityIsolationGateway, settings: Settings) -> None:
        self._memory = memory
        self._gateway = gateway
        self._settings = settings
        self._wall_messages: list[WallMessage] = []

    async def create_greeting(self, user_id: str, session_id: str) -> str:
        """Compose a gentle deterministic greeting from non-sensitive recalled preferences."""
        long_term = await self._memory.query(user_id=user_id, tier=MemoryTier.LONG_TERM)
        short_term = await self._memory.query(user_id=user_id, tier=MemoryTier.SHORT_TERM)
        preferred_name = self._find_value(long_term, "preferred_name")
        recent_weather = self._find_latest_weather(short_term)
        name = str(preferred_name) if preferred_name else "同学"
        if recent_weather in self._NEGATIVE_WEATHER:
            return f"{name}，欢迎回来。最近似乎不太轻松，想聊聊或安静待一会儿都可以。"
        return f"{name}，欢迎来到暖心空间。今天的心情怎么样？"

    def parse_control_command(self, user_text: str) -> GuideControlCommand | None:
        """Parse supported music/system controls without giving an LLM device authority."""
        normalized = user_text.lower().replace(" ", "")
        if any(word in normalized for word in ("关掉", "停止", "暂停")) and any(word in normalized for word in ("音乐", "声音", "背景音")):
            return GuideControlCommand(command="stop_audio")
        track_terms = {AmbientTrack.RAIN: ("雨声", "白噪音"), AmbientTrack.PIANO: ("钢琴", "琴声"), AmbientTrack.FOREST: ("森林", "鸟鸣")}
        for track, terms in track_terms.items():
            if any(term in normalized for term in terms):
                return GuideControlCommand(command="play_audio", track=track)
        return None

    async def compose_opening(self, user_id: str) -> dict[str, object]:
        """进暖心空间时引导员主动说的第一句。

        不走大模型：进页面就该立刻有话，等 2 秒的空白比说错话更伤。
        但语气必须跟着最近的状态走，所以先把打卡读出来再选分支。
        """
        records = await self._memory.query(user_id=user_id, tier=MemoryTier.SHORT_TERM, category="wellbeing.mood_checkin")
        checkins: list[tuple[str, str, str]] = []
        for record in records:
            checked_at = record.value.get("checked_at")
            if not isinstance(checked_at, str):
                continue
            checkins.append((checked_at, str(record.value.get("weather") or ""), str(record.value.get("reflection") or "")))
        checkins.sort(key=lambda item: item[0])

        today = utc_now().astimezone(timezone.utc).date().isoformat()
        checked_today = bool(checkins) and checkins[-1][0][:10] == today
        negative = [item for item in checkins if item[1] in self._NEGATIVE_WEATHER]
        level = "green"
        if len(negative) >= 5:
            level = "orange"
        elif len(negative) >= 3:
            level = "yellow"

        if not checkins:
            opening = "我是小齐。第一次来不用急着说什么，坐着发会儿呆也行。今天过得怎么样？"
            chips = ["今天还行", "有点累", "先不说话，陪我待一会儿"]
            mood = ""
        elif negative and not checked_today:
            last = negative[-1]
            quoted = last[2].strip()
            tail = f"上次你写的是「{quoted[:24]}」。不用急着讲原因，想说的时候我听着。" if quoted else "不用急着讲原因，想说的时候我听着。"
            opening = f"我在。最近这阵子看着一直绷着，{tail}"
            chips = ["我想说说", "不知道从哪说起", "先不说这个"]
            mood = last[1]
        elif checked_today and checkins[-1][1] == "sunny":
            opening = "今天记的是晴，看到这个我挺高兴的。要不要说说，是什么让你今天松了一点？"
            chips = ["就是天气好", "有件小事挺开心", "也说不上来"]
            mood = "sunny"
        elif checked_today:
            opening = "今天已经记过了，我看到了。现在这会儿和刚才比，是差不多还是不太一样？"
            chips = ["差不多", "好一点了", "更差了"]
            mood = checkins[-1][1]
        else:
            opening = "今天还没记。不过不急着打卡——现在这会儿你更想被听听，还是一起想想办法？"
            chips = ["想被听听", "一起想办法", "随便聊聊"]
            mood = checkins[-1][1] if checkins else ""

        return {"opening": opening, "chips": chips, "mood": mood, "alert_level": level, "checked_today": checked_today}

    async def compose_soothe(self, user_id: str) -> dict[str, object]:
        """心情不好时给的具体疏导动作。

        和「安慰话」分开：安慰是态度，这里给的是能立刻执行的动作。
        每条都带一个前端可跳转的锚点，避免推荐完还要自己找入口。
        """
        state = await self.compose_opening(user_id)
        level = str(state["alert_level"])
        mood = str(state["mood"])
        # 绿等级 + 非负面心情时不必推动作，避免变成又一块没人看的文案
        show = level != "green" or mood in {weather.value for weather in self._NEGATIVE_WEATHER}
        groups = [
            {"id": group_id, "label": label, "actions": [dict(action) for action in actions]}
            for group_id, label, actions in self._SOOTHE_GROUPS
        ]
        return {"show": show, "level": level, "mood": mood, "groups": groups}

    async def record_check_in(self, user_id: str, session_id: str, check_in: MoodCheckIn) -> MoodCheckInResult:
        """Persist a private check-in, calculate the transparent support level, and alert safely."""
        prior = await self._memory.query(user_id=user_id, tier=MemoryTier.SHORT_TERM, category="wellbeing.mood_checkin")
        level, reasons = self._evaluate_alert((*prior, self._as_record(user_id, session_id, check_in)))
        record = self._as_record(user_id, session_id, check_in)
        await self._memory.put(record)
        if level in {AlertLevel.ORANGE, AlertLevel.RED}:
            await self._create_staff_alert(user_id, level, reasons)
        return self._student_result(level)

    async def list_check_ins(self, user_id: str, days: int = 7) -> list[dict[str, object]]:
        """返回该用户最近 N 天的心情打卡，按时间正序。

        ``days`` 会被夹在 1..7：短期记忆保留期只有 7 天，超过窗口的记录已被
        ``prune_expired`` 清掉，返回更长的区间只会让前端画出一段假空白。
        只有记录所有者本人能走到这里（默认 OWNER 作用域），所以 reflection
        原文可以回传给本人；辅导员侧永远走独立的预警记录。
        """
        try:
            window = int(days)
        except (TypeError, ValueError):
            window = 7
        window = max(1, min(window, 7))
        cutoff = utc_now() - timedelta(days=window)
        records = await self._memory.query(user_id=user_id, tier=MemoryTier.SHORT_TERM, category="wellbeing.mood_checkin")
        items: list[dict[str, object]] = []
        for record in records:
            try:
                checked_at = self._record_time(record)
            except (TypeError, ValueError):
                checked_at = record.created_at
            if checked_at.tzinfo is None:
                checked_at = checked_at.replace(tzinfo=timezone.utc)
            if checked_at < cutoff:
                continue
            weather = record.value.get("weather")
            items.append(
                {
                    "weather": weather.value if isinstance(weather, MoodWeather) else str(weather or ""),
                    "checked_at": checked_at.isoformat(),
                    "reflection": str(record.value.get("reflection") or ""),
                }
            )
        items.sort(key=lambda item: str(item["checked_at"]))
        return items

    async def publish_wall_message(self, message: WallMessage) -> WallMessage:
        """Publish a vetted counselor message; its author identity is never exposed to students."""
        self._wall_messages.append(message)
        return message

    async def list_wall_messages(self) -> list[WallMessage]:
        """Return warm-card content only, ordered from newest to oldest."""
        return sorted(self._wall_messages, key=lambda item: item.published_at, reverse=True)

    async def list_counselor_alerts(self) -> list[dict[str, object]]:
        """Return all counselor alerts across students for the authorized staff view.

        Alerts are stored per-student, so staff retrieval is a cross-owner lookup that
        must always pass explicit staff scopes; the default OWNER scope is never widened.
        Only the minimal alert record is returned, never the student's reflection text.
        """
        records = await self._memory.query(
            user_id=None,
            tier=MemoryTier.SHORT_TERM,
            category="wellbeing.counselor_alert",
            permitted_scopes={AccessScope.AUTHORIZED_STAFF, AccessScope.SYSTEM_ONLY},
        )
        alerts: list[dict[str, object]] = []
        for record in records:
            try:
                alert = CounselorAlert.model_validate(record.value)
            except ValidationError:
                continue
            payload = alert.model_dump(mode="json")
            payload["created_at"] = record.created_at.isoformat()
            alerts.append(payload)
        return sorted(alerts, key=lambda item: str(item["created_at"]), reverse=True)

    def build_talk_ledger(self, source: TalkLedgerInput) -> TalkLedgerEntry:
        """Create a counselor-reviewable ledger from confirmed facts, never raw audio/transcripts."""
        topic_summary = "；".join(item.strip() for item in source.topics if item.strip())
        return TalkLedgerEntry(student_id=source.student_id, counselor_name=source.counselor_name, meeting_at=source.meeting_at, location=source.location, topic_summary=topic_summary, agreed_actions=source.agreed_actions, follow_up_at=source.follow_up_at)

    async def request_booking(self, user_id: str, session_id: str, slot: str, note: str, alert_level: str) -> dict[str, object]:
        """学生主动约一次谈心：落成辅导员可见的记录，而不是只在前端留一行字。

        与预警记录分开存：预警是系统判定，预约是本人主动求助，两者的处置流程不同。
        note 只给辅导员看，不会回传给其他学生。
        """
        booking: dict[str, object] = {
            "booking_id": f"booking-{uuid4().hex[:12]}",
            "user_id": user_id,
            "slot": slot.strip()[:80],
            "note": note.strip()[:500],
            "alert_level": alert_level or "",
            "requested_at": utc_now().isoformat(),
            "status": "pending",
        }
        await self._memory.put(
            MemoryRecord(
                user_id=user_id,
                session_id=session_id,
                tier=MemoryTier.SHORT_TERM,
                category="wellbeing.booking_request",
                value=booking,
                source_agent="wellbeing-service",
                access_scope=AccessScope.AUTHORIZED_STAFF,
                sensitivity=SensitivityLevel.RESTRICTED,
                expires_at=utc_now() + timedelta(seconds=self._settings.short_term_memory_ttl_seconds),
            )
        )
        return booking

    async def list_bookings(self) -> list[dict[str, object]]:
        """辅导员侧：待处理的谈心预约，按提交时间倒序。"""
        records = await self._memory.query(
            user_id=None,
            tier=MemoryTier.SHORT_TERM,
            category="wellbeing.booking_request",
            permitted_scopes={AccessScope.AUTHORIZED_STAFF, AccessScope.SYSTEM_ONLY},
        )
        bookings: list[dict[str, object]] = []
        for record in records:
            payload = dict(record.value)
            payload.setdefault("requested_at", record.created_at.isoformat())
            bookings.append(payload)
        return sorted(bookings, key=lambda item: str(item["requested_at"]), reverse=True)

    async def publish_happy_share(self, user_id: str, session_id: str, author_name: str, draft: HappyShareDraft) -> HappyShare:
        """Screen a positive moment deterministically, then publish it to everyone.

        Rejection never silently drops the text: the student is pointed at the private
        check-in surface (or the crisis line) instead of being told "发布失败".
        """
        verdict = self.screen_share_content(draft.content)
        if verdict == "crisis":
            raise HappyShareRejected(self._SHARE_CRISIS_MESSAGE, "support")
        if verdict == "negative":
            raise HappyShareRejected(self._SHARE_NEGATIVE_MESSAGE, "checkin")
        share = HappyShare(
            author_id=user_id,
            author_name="匿名同学" if draft.anonymous else (author_name.strip()[:40] or "同学"),
            content=draft.content.strip(),
            image_data_url=draft.image_data_url,
        )
        await self._memory.put(
            MemoryRecord(
                record_id=share.share_id,
                user_id=user_id,
                session_id=session_id,
                tier=MemoryTier.LONG_TERM,
                category="wellbeing.happy_share",
                value=share.model_dump(mode="json"),
                source_agent="wellbeing-service",
                access_scope=AccessScope.PUBLIC,
                sensitivity=SensitivityLevel.PUBLIC,
                expires_at=None,
            )
        )
        return share

    async def list_happy_shares(self, limit: int = 30) -> list[HappyShare]:
        """Return every public share, newest first; no owner filter is applied."""
        records = await self._memory.query(
            user_id=None,
            tier=MemoryTier.LONG_TERM,
            category="wellbeing.happy_share",
            permitted_scopes={AccessScope.PUBLIC},
        )
        shares: list[HappyShare] = []
        for record in records:
            try:
                shares.append(HappyShare.model_validate(record.value))
            except ValidationError:
                continue
        shares.sort(key=lambda item: item.created_at, reverse=True)
        return shares[: max(1, min(limit, 100))]

    async def cheer_happy_share(self, share_id: str) -> HappyShare | None:
        """Increment one share's encouragement counter and return the updated record."""
        records = await self._memory.query(
            user_id=None,
            tier=MemoryTier.LONG_TERM,
            category="wellbeing.happy_share",
            permitted_scopes={AccessScope.PUBLIC},
        )
        for record in records:
            if str(record.value.get("share_id")) != share_id:
                continue
            try:
                share = HappyShare.model_validate(record.value)
            except ValidationError:
                return None
            updated = share.model_copy(update={"cheer_count": share.cheer_count + 1})
            await self._memory.put(record.model_copy(update={"value": updated.model_dump(mode="json")}))
            return updated
        return None

    @classmethod
    def screen_share_content(cls, content: str) -> str:
        """Classify a draft as ``ok``, ``crisis``, or ``negative`` without any model call."""
        normalized = content.lower().replace(" ", "")
        if any(term.lower().replace(" ", "") in normalized for term in cls._HIGH_RISK_TERMS):
            return "crisis"
        if any(term.lower() in normalized for term in cls._SHARE_NEGATIVE_TERMS):
            return "negative"
        return "ok"

    def _as_record(self, user_id: str, session_id: str, check_in: MoodCheckIn) -> MemoryRecord:
        # Reflection is restricted to the student context; staff retrieval uses separate alert records.
        return MemoryRecord(user_id=user_id, session_id=session_id, tier=MemoryTier.SHORT_TERM, category="wellbeing.mood_checkin", value={"weather": check_in.weather, "checked_at": check_in.checked_at.isoformat(), "reflection": check_in.reflection}, source_agent="wellbeing-service", access_scope=AccessScope.OWNER, sensitivity=SensitivityLevel.SENSITIVE, expires_at=check_in.checked_at + timedelta(seconds=self._settings.short_term_memory_ttl_seconds))

    def _evaluate_alert(self, records: Iterable[MemoryRecord]) -> tuple[AlertLevel, list[str]]:
        records_list = list(records)
        reflections = " ".join(str(record.value.get("reflection", "")).lower() for record in records_list)
        if any(term.lower() in reflections for term in self._HIGH_RISK_TERMS):
            return AlertLevel.RED, ["high_risk_language_detected"]
        now = utc_now()
        recent = [record for record in records_list if self._record_time(record) >= now - timedelta(days=7)]
        negative = [record for record in recent if record.value.get("weather") in self._NEGATIVE_WEATHER]
        if len(negative) >= 5:
            return AlertLevel.ORANGE, ["five_negative_checkins_within_seven_days"]
        negative_days = {self._record_time(record).astimezone(timezone.utc).date() for record in negative}
        if len(negative_days) >= 3 and self._has_three_consecutive_days(negative_days):
            return AlertLevel.YELLOW, ["three_consecutive_negative_checkins"]
        return AlertLevel.GREEN, []

    async def _create_staff_alert(self, user_id: str, level: AlertLevel, reasons: list[str]) -> None:
        alert = CounselorAlert(student_id=user_id, level=level, reason_codes=reasons)
        await self._memory.put(MemoryRecord(user_id=user_id, tier=MemoryTier.SHORT_TERM, category="wellbeing.counselor_alert", value=alert.model_dump(mode="json"), source_agent="wellbeing-service", access_scope=AccessScope.AUTHORIZED_STAFF, sensitivity=SensitivityLevel.RESTRICTED, expires_at=utc_now() + timedelta(seconds=self._settings.short_term_memory_ttl_seconds)))

    @staticmethod
    def _record_time(record: MemoryRecord) -> datetime:
        value = record.value.get("checked_at")
        return datetime.fromisoformat(value) if isinstance(value, str) else record.created_at

    @staticmethod
    def _has_three_consecutive_days(days: set[object]) -> bool:
        ordered = sorted(days)
        return any((ordered[index + 2] - ordered[index]).days == 2 for index in range(len(ordered) - 2))

    @staticmethod
    def _student_result(level: AlertLevel) -> MoodCheckInResult:
        messages = {
            AlertLevel.GREEN: "已收到你的心情记录。照顾好自己，有需要时暖心空间一直在。",
            AlertLevel.YELLOW: "我注意到你最近可能有些累。要不要找一个舒服的时间聊聊？",
            AlertLevel.ORANGE: "你最近承受了不少。建议预约一次辅导员谈心或校内心理支持服务。",
            AlertLevel.RED: "你的安全很重要。请尽快联系身边可信任的人、辅导员，或拨打 24 小时心理援助热线 12356；我们也会发出人工关怀提醒。",
        }
        # 黄等级对应「要不要找时间聊聊」，所以预约入口从黄就开始给，不必等到橙
        return MoodCheckInResult(alert_level=level, support_message=messages[level], booking_suggested=level in {AlertLevel.YELLOW, AlertLevel.ORANGE, AlertLevel.RED}, human_follow_up_requested=level == AlertLevel.RED)

    @staticmethod
    def _find_value(records: list[MemoryRecord], key: str) -> object | None:
        for record in reversed(records):
            if key in record.value:
                return record.value[key]
        return None

    @staticmethod
    def _find_latest_weather(records: list[MemoryRecord]) -> MoodWeather | None:
        checkins = [record for record in records if record.category == "wellbeing.mood_checkin"]
        if not checkins:
            return None
        value = max(checkins, key=lambda item: item.created_at).value.get("weather")
        return MoodWeather(value) if value else None
