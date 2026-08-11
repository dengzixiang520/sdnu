"""Task 3 implementations for timetable parsing, AA ledgering, and conflict avoidance."""

import csv
import io
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Iterable

from zhihui_qilu.dormitory_models import (
    DormInspection,
    DutyAssignment,
    ExpenseSettlement,
    ScheduleConflict,
    ScheduleEvent,
    ScheduleSource,
    SettlementTransfer,
    SharedExpense,
    SwapSuggestion,
)


class TimetableParseError(ValueError):
    """Raised when an imported timetable cannot be safely normalized."""


class OcrRecognizer(ABC):
    """Port for a vision/OCR provider used by screenshot timetable imports."""

    @abstractmethod
    async def extract_text(self, image_bytes: bytes) -> str:
        """Return recognized timetable text; provider implementations belong to later integration work."""


class TimetableParser:
    """Normalize ICS, CSV/XLSX, OCR text, and pasted text into schedule events."""

    _TEXT_LINE = re.compile(r"^\s*(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<start>\d{1,2}:\d{2})\s*[-~至]\s*(?P<end>\d{1,2}:\d{2})\s+(?P<title>.+?)(?:\s+@\s*(?P<location>.+))?\s*$")
    _COLUMN_ALIASES = {
        "title": ("title", "course", "课程", "课程名称", "事项"),
        "starts_at": ("starts_at", "start", "开始时间", "开始"),
        "ends_at": ("ends_at", "end", "结束时间", "结束"),
        "location": ("location", "地点", "教室"),
    }

    def parse_ics(self, content: str) -> list[ScheduleEvent]:
        """Parse the common VEVENT fields required by exported calendar .ics files."""
        unfolded = re.sub(r"\r?\n[ \t]", "", content)
        events: list[ScheduleEvent] = []
        for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfolded, flags=re.DOTALL):
            values: dict[str, str] = {}
            for line in block.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                values[key.split(";", 1)[0].upper()] = value.strip()
            try:
                events.append(ScheduleEvent(title=values["SUMMARY"], starts_at=self._parse_ics_datetime(values["DTSTART"]), ends_at=self._parse_ics_datetime(values["DTEND"]), location=values.get("LOCATION"), source=ScheduleSource.ICS))
            except KeyError as exc:
                raise TimetableParseError(f"VEVENT is missing required field: {exc.args[0]}") from exc
        if not events:
            raise TimetableParseError("No VEVENT entries were found in ICS content")
        return events

    def parse_csv(self, content: str) -> list[ScheduleEvent]:
        """Parse UTF-8 CSV with English or Chinese common timetable column names."""
        rows = list(csv.DictReader(io.StringIO(content)))
        return self._parse_tabular_rows(rows, ScheduleSource.SPREADSHEET)

    def parse_xlsx(self, content: bytes) -> list[ScheduleEvent]:
        """Parse the active worksheet of an XLSX upload when optional openpyxl is installed."""
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover - guarded by package dependency
            raise TimetableParseError("XLSX import requires openpyxl") from exc
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        worksheet = workbook.active
        rows = list(worksheet.iter_rows(values_only=True))
        if not rows:
            raise TimetableParseError("Spreadsheet is empty")
        headers = [str(value).strip() if value is not None else "" for value in rows[0]]
        mappings = [dict(zip(headers, row, strict=False)) for row in rows[1:] if any(value is not None for value in row)]
        return self._parse_tabular_rows(mappings, ScheduleSource.SPREADSHEET)

    def parse_text(self, content: str, source: ScheduleSource = ScheduleSource.TEXT) -> list[ScheduleEvent]:
        """Parse one `YYYY-MM-DD HH:MM-HH:MM title @ location` entry per line."""
        events: list[ScheduleEvent] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                continue
            match = self._TEXT_LINE.match(line)
            if not match:
                raise TimetableParseError(f"Cannot parse timetable text at line {line_number}")
            date = match.group("date")
            events.append(ScheduleEvent(title=match.group("title").strip(), starts_at=self._parse_datetime(f"{date} {match.group('start')}") , ends_at=self._parse_datetime(f"{date} {match.group('end')}") , location=match.group("location"), source=source))
        if not events:
            raise TimetableParseError("No schedule entries were found")
        return events

    async def parse_ocr(self, image_bytes: bytes, recognizer: OcrRecognizer) -> list[ScheduleEvent]:
        """Delegate image recognition, then normalize the returned text using the same parser."""
        return self.parse_text(await recognizer.extract_text(image_bytes), source=ScheduleSource.OCR)

    def _parse_tabular_rows(self, rows: list[dict[object, object]], source: ScheduleSource) -> list[ScheduleEvent]:
        events: list[ScheduleEvent] = []
        for index, row in enumerate(rows, start=2):
            normalized = {str(key).strip(): value for key, value in row.items() if key is not None}
            try:
                title = str(self._pick(normalized, "title"))
                starts_at = self._parse_datetime(self._pick(normalized, "starts_at"))
                ends_at = self._parse_datetime(self._pick(normalized, "ends_at"))
                location_value = self._pick(normalized, "location", required=False)
                events.append(ScheduleEvent(title=title, starts_at=starts_at, ends_at=ends_at, location=str(location_value) if location_value else None, source=source))
            except (KeyError, ValueError) as exc:
                raise TimetableParseError(f"Cannot parse spreadsheet row {index}: {exc}") from exc
        if not events:
            raise TimetableParseError("Spreadsheet contains no timetable entries")
        return events

    def _pick(self, row: dict[str, object], field: str, required: bool = True) -> object | None:
        for name in self._COLUMN_ALIASES[field]:
            if name in row and row[name] not in (None, ""):
                return row[name]
        if required:
            raise KeyError(field)
        return None

    @staticmethod
    def _parse_datetime(value: object) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        raw = str(value).strip().replace("/", "-")
        for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(raw, pattern).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        raise ValueError(f"Unsupported datetime: {value}")

    @staticmethod
    def _parse_ics_datetime(value: str) -> datetime:
        raw = value.rstrip("Z")
        for pattern in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"):
            try:
                return datetime.strptime(raw, pattern).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        raise TimetableParseError(f"Unsupported ICS datetime: {value}")


class DormitoryService:
    """Provide transparent shared-expense calculations and positive dormitory feedback."""

    def settle_expenses(self, expenses: Iterable[SharedExpense]) -> ExpenseSettlement:
        """Calculate cent-accurate AA balances and the minimum greedy settlement transfers."""
        balances: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
        for expense in expenses:
            cents = int((expense.amount * 100).to_integral_value(rounding=ROUND_DOWN))
            share_cents, remainder = divmod(cents, len(expense.participant_ids))
            balances[expense.payer_id] += expense.amount
            for index, member_id in enumerate(sorted(expense.participant_ids)):
                owed_cents = share_cents + (1 if index < remainder else 0)
                balances[member_id] -= Decimal(owed_cents) / Decimal(100)
        rounded = {member: amount.quantize(Decimal("0.01")) for member, amount in balances.items() if amount != 0}
        debtors = [[member, -amount] for member, amount in rounded.items() if amount < 0]
        creditors = [[member, amount] for member, amount in rounded.items() if amount > 0]
        transfers: list[SettlementTransfer] = []
        debtor_index = creditor_index = 0
        while debtor_index < len(debtors) and creditor_index < len(creditors):
            debtor, debt = debtors[debtor_index]
            creditor, credit = creditors[creditor_index]
            payment = min(debt, credit).quantize(Decimal("0.01"))
            transfers.append(SettlementTransfer(from_member_id=debtor, to_member_id=creditor, amount=payment))
            debtors[debtor_index][1] -= payment
            creditors[creditor_index][1] -= payment
            if debtors[debtor_index][1] == 0:
                debtor_index += 1
            if creditors[creditor_index][1] == 0:
                creditor_index += 1
        return ExpenseSettlement(balances=rounded, transfers=transfers)

    @staticmethod
    def create_improvement_suggestion(inspection: DormInspection) -> str:
        """Turn inspection observations into a specific, appreciative, non-punitive suggestion."""
        strength = inspection.strengths[0] if inspection.strengths else "大家对宿舍公共空间的共同维护"
        observation = inspection.observations[0] if inspection.observations else "部分公共区域还可以再整理一下"
        return f"{inspection.dormitory_label}的{strength}值得肯定。针对“{observation}”，建议大家商量一个方便执行的小分工，并在下次值日时一起完成；需要帮助可随时联系宿管老师。"


class ScheduleCoordinator:
    """Detect interval intersections and propose non-binding duty-swap candidates."""

    def find_conflicts(self, assignments: Iterable[DutyAssignment], member_events: dict[str, list[ScheduleEvent]]) -> list[ScheduleConflict]:
        """Return all overlaps between shared duties and a member's personal schedule."""
        conflicts: list[ScheduleConflict] = []
        for duty in assignments:
            for event in member_events.get(duty.member_id, []):
                if self._overlaps(duty.starts_at, duty.ends_at, event.starts_at, event.ends_at):
                    conflicts.append(ScheduleConflict(member_id=duty.member_id, duty=duty, conflicting_event=event))
        return conflicts

    def suggest_swaps(self, conflicts: Iterable[ScheduleConflict], assignments: Iterable[DutyAssignment], member_events: dict[str, list[ScheduleEvent]]) -> list[SwapSuggestion]:
        """Find roommates with no overlap during the conflicted duty period; never auto-changes rosters."""
        roster = {assignment.member_id for assignment in assignments}
        suggestions: list[SwapSuggestion] = []
        for conflict in conflicts:
            candidates = sorted(member for member in roster if member != conflict.member_id and all(not self._overlaps(conflict.duty.starts_at, conflict.duty.ends_at, event.starts_at, event.ends_at) for event in member_events.get(member, [])))
            if candidates:
                suggestions.append(SwapSuggestion(original_member_id=conflict.member_id, suggested_member_id=candidates[0], duty=conflict.duty, rationale=f"检测到与“{conflict.conflicting_event.title}”重叠；候选同学该时段暂无课表或日程冲突。"))
        return suggestions

    @staticmethod
    def _overlaps(first_start: datetime, first_end: datetime, second_start: datetime, second_end: datetime) -> bool:
        return max(first_start, second_start) < min(first_end, second_end)
