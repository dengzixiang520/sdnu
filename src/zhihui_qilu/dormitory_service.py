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
    CommonIssue,
    DimensionInput,
    DimensionNote,
    DimensionState,
    DormInspection,
    DutyAssignment,
    ExpenseSettlement,
    InspectionDimension,
    InspectionRecord,
    InspectionReport,
    IssueDigest,
    ScheduleConflict,
    ScheduleEvent,
    ScheduleSource,
    SettlementTransfer,
    SharedExpense,
    SwapSuggestion,
)

# 五个维度的中文名，顺序就是命题二列举的顺序。
_DIMENSION_LABELS: dict[str, str] = {
    InspectionDimension.HYGIENE: "卫生",
    InspectionDimension.SAFETY: "安全秩序",
    InspectionDimension.SCHEDULE: "作息规律",
    InspectionDimension.RELATION: "关系调适",
    InspectionDimension.CIVILITY: "文明习惯",
}

# 每个维度三档各给一句「具体做什么」。空话（「加强管理」）在这里没有位置。
_DIMENSION_ADVICE: dict[str, dict[str, str]] = {
    InspectionDimension.HYGIENE: {
        "good": "保持就好，不用为检查临时收拾。",
        "watch": "把「每周固定一次十分钟公共区收拾」写进值日表，比突击更省事。",
        "issue": "先分工再动手：谁管地面、谁管阳台、谁管垃圾清运，写下来贴门后。",
    },
    InspectionDimension.SAFETY: {
        "good": "插排和线路没发现问题，继续别在床上充电。",
        "watch": "把插排从床上挪到桌面，睡前拔掉大功率电器。",
        "issue": "本周清一次违规电器和私拉线路，清完拍照存进宿舍群。",
    },
    InspectionDimension.SCHEDULE: {
        "good": "作息基本一致，互相不打扰。",
        "watch": "商量一个「熄灯后戴耳机」的默认规则，不用每次提醒。",
        "issue": "开一次十分钟的宿舍会，把最晚关灯时间和早起闹钟写下来。",
    },
    InspectionDimension.RELATION: {
        "good": "舍友之间能正常商量事，这比什么都强。",
        "watch": "有话说在当面，别攒着；攒到最后一句就变成吵架。",
        "issue": "找一个中立的时间坐下来，只说「我希望」不说「你总是」。",
    },
    InspectionDimension.CIVILITY: {
        "good": "公共物品和垃圾清运有人管，习惯已经立住了。",
        "watch": "把公用品采购列成一张清单，谁买谁记账，月底一起结。",
        "issue": "先定一条最小公约：垃圾谁最后出门谁带走，试行两周。",
    },
}

# good 档的观察默认语，用户没写备注时用它，不留空。
_DIMENSION_GOOD_NOTE: dict[str, str] = {
    InspectionDimension.HYGIENE: "地面、阳台、垃圾清运都没有明显问题。",
    InspectionDimension.SAFETY: "未发现违规电器与私拉线路。",
    InspectionDimension.SCHEDULE: "熄灯时间基本一致，没有明显互相打扰。",
    InspectionDimension.RELATION: "舍友之间能正常沟通，没有积压的矛盾。",
    InspectionDimension.CIVILITY: "公共物品有人管，垃圾清运有固定安排。",
}


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

    def build_inspection_report(
        self,
        dormitory_label: str,
        inputs: Iterable[DimensionInput],
        strengths: Iterable[str] = (),
    ) -> InspectionReport:
        """把现场观察转成结构化反馈：五个维度各一句「看到什么 + 怎么改」。

        刻意不打分、不排名。命题二的原话是「避免简单通报批评」，
        所以每一条都带一个具体动作，而不是一个分数。
        """
        provided = {item.dimension: item for item in inputs}
        notes: list[DimensionNote] = []
        issue_count = 0
        watch_count = 0

        for dimension in InspectionDimension:
            entry = provided.get(dimension)
            state = entry.state if entry else DimensionState.GOOD
            note_text = (entry.note.strip() if entry else "") or _DIMENSION_GOOD_NOTE[dimension]
            if state is DimensionState.ISSUE:
                issue_count += 1
            elif state is DimensionState.WATCH:
                watch_count += 1
            label = _DIMENSION_LABELS[dimension]
            feedback = (
                f"{label}这一项不用操心。"
                if state is DimensionState.GOOD
                else f"{label}上有一点苗头，还不算问题。"
                if state is DimensionState.WATCH
                else f"{label}这一项需要这周就动一次。"
            )
            notes.append(
                DimensionNote(
                    dimension=dimension,
                    label=label,
                    state=state,
                    observation=note_text,
                    feedback=feedback,
                    action=_DIMENSION_ADVICE[dimension][state],
                )
            )

        if issue_count >= 3:
            summary = f"{dormitory_label}这次有 {issue_count} 项需要动，先挑最影响生活的那一项做，别一次全改。"
        elif issue_count >= 1:
            summary = f"{dormitory_label}整体可以，{issue_count} 项要这周处理，其余保持。"
        elif watch_count >= 1:
            summary = f"{dormitory_label}这次没有硬问题，{watch_count} 项有点苗头，提前商量一下就行。"
        else:
            summary = f"{dormitory_label}五项都稳，这次不用改什么。"

        strength_list = [item.strip() for item in strengths if item.strip()]
        if not strength_list:
            strength_list = [f"{_DIMENSION_LABELS[item.dimension]}保持得住" for item in notes if item.state is DimensionState.GOOD][:2]

        return InspectionReport(
            dormitory_label=dormitory_label,
            notes=notes,
            strengths=strength_list,
            summary=summary,
            encouragement="检查是为了让住着舒服，不是比谁好谁差。有需要随时找宿管老师。",
            issue_count=issue_count,
            watch_count=watch_count,
        )

    def summarize_issues(self, records: Iterable[InspectionRecord]) -> IssueDigest:
        """跨多次检查找共性问题与个别隐患。

        命题二要「帮助辅导员发现共性问题与个别隐患」：同一个维度过半宿舍都有问题，
        就是共性，值得开一次会讲；只有一两个宿舍有，是个别隐患，单独提醒即可。
        """
        rows = list(records)
        total_inspections = len(rows)
        dorms = {item.dormitory_label for item in rows}
        total_dorms = len(dorms)

        if not total_dorms:
            return IssueDigest(
                total_inspections=0,
                total_dorms=0,
                common_issues=[],
                isolated_issues=[],
                summary="还没有检查记录，先记一次就能看到共性问题。",
                note="汇总只统计维度状态，不含任何学生个人信息。",
            )

        # 每个维度被多少「不同的宿舍」标成 issue 或 watch
        touched: dict[str, set[str]] = {dimension: set() for dimension in InspectionDimension}
        for record in rows:
            for dimension, state in record.dimensions.items():
                if state in (DimensionState.ISSUE, DimensionState.WATCH) and dimension in touched:
                    touched[dimension].add(record.dormitory_label)

        common: list[CommonIssue] = []
        isolated: list[CommonIssue] = []
        for dimension in InspectionDimension:
            hits = len(touched[dimension])
            if not hits:
                continue
            share = round(hits / total_dorms * 100)
            is_common = share >= 50
            item = CommonIssue(
                dimension=dimension,
                label=_DIMENSION_LABELS[dimension],
                dorms=hits,
                total_dorms=total_dorms,
                share=share,
                advice=_DIMENSION_ADVICE[dimension][DimensionState.ISSUE],
                is_common=is_common,
            )
            (common if is_common else isolated).append(item)

        common.sort(key=lambda item: -item.share)
        isolated.sort(key=lambda item: -item.share)

        if common:
            summary = (
                f"{total_dorms} 个宿舍里，"
                + "、".join(f"{item.label}（{item.dorms} 个宿舍，{item.share}%）" for item in common[:3])
                + " 属于共性问题，值得开一次短会统一讲。"
            )
        elif isolated:
            summary = f"{total_dorms} 个宿舍没有共性问题，{len(isolated)} 项只是个别情况，单独提醒就行。"
        else:
            summary = f"{total_dorms} 个宿舍这次都没有需要提醒的项。"

        return IssueDigest(
            total_inspections=total_inspections,
            total_dorms=total_dorms,
            common_issues=common,
            isolated_issues=isolated,
            summary=summary,
            note="汇总只统计维度状态与宿舍数量，不含任何学生个人信息。",
        )


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
