"""Task 2 services: warm guidance, check-ins, privacy-safe alerts, and counselor tools."""

from datetime import datetime, timedelta, timezone
from typing import Iterable

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
    MoodCheckIn,
    MoodCheckInResult,
    MoodWeather,
    TalkLedgerEntry,
    TalkLedgerInput,
    WallMessage,
)


class WellbeingService:
    """Implements non-diagnostic wellbeing workflows on the platform memory boundary."""

    _HIGH_RISK_TERMS = ("自杀", "自殘", "自残", "结束生命", "不想活", "suicide", "kill myself")
    _NEGATIVE_WEATHER = {MoodWeather.RAINY, MoodWeather.STORMY}

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

    async def record_check_in(self, user_id: str, session_id: str, check_in: MoodCheckIn) -> MoodCheckInResult:
        """Persist a private check-in, calculate the transparent support level, and alert safely."""
        prior = await self._memory.query(user_id=user_id, tier=MemoryTier.SHORT_TERM, category="wellbeing.mood_checkin")
        level, reasons = self._evaluate_alert((*prior, self._as_record(user_id, session_id, check_in)))
        record = self._as_record(user_id, session_id, check_in)
        await self._memory.put(record)
        if level in {AlertLevel.ORANGE, AlertLevel.RED}:
            await self._create_staff_alert(user_id, level, reasons)
        return self._student_result(level)

    async def publish_wall_message(self, message: WallMessage) -> WallMessage:
        """Publish a vetted counselor message; its author identity is never exposed to students."""
        self._wall_messages.append(message)
        return message

    async def list_wall_messages(self) -> list[WallMessage]:
        """Return warm-card content only, ordered from newest to oldest."""
        return sorted(self._wall_messages, key=lambda item: item.published_at, reverse=True)

    async def list_counselor_alerts(self) -> list[CounselorAlert]:
        """Return all counselor alerts for staff view."""
        records = await self._memory.query(user_id="", tier=MemoryTier.SHORT_TERM, category="wellbeing.counselor_alert", permitted_scopes={AccessScope.AUTHORIZED_STAFF, AccessScope.SYSTEM_ONLY})
        alerts = []
        for record in records:
            try:
                alert = CounselorAlert.model_validate(record.value)
                alert_dict = alert.model_dump()
                alert_dict["created_at"] = record.created_at.isoformat()
                alerts.append(alert_dict)
            except Exception:
                continue
        return alerts
        """Return warm-card content only, ordered from newest to oldest."""
        return sorted(self._wall_messages, key=lambda item: item.published_at, reverse=True)

    def build_talk_ledger(self, source: TalkLedgerInput) -> TalkLedgerEntry:
        """Create a counselor-reviewable ledger from confirmed facts, never raw audio/transcripts."""
        topic_summary = "；".join(item.strip() for item in source.topics if item.strip())
        return TalkLedgerEntry(student_id=source.student_id, counselor_name=source.counselor_name, meeting_at=source.meeting_at, location=source.location, topic_summary=topic_summary, agreed_actions=source.agreed_actions, follow_up_at=source.follow_up_at)

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
            AlertLevel.RED: "你的安全很重要。请尽快联系身边可信任的人、辅导员或当地紧急支持服务；我们也会发出人工关怀提醒。",
        }
        return MoodCheckInResult(alert_level=level, support_message=messages[level], booking_suggested=level in {AlertLevel.ORANGE, AlertLevel.RED}, human_follow_up_requested=level == AlertLevel.RED)

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
