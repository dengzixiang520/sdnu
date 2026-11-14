"""Task 4 Skill: postgraduate interview simulation and note organization."""

import base64
import binascii
import io
import math
import os
import re
from typing import Any

from zhihui_qilu.academic_models import InterviewConfig, StructuredNote, TranscriptSegment
from zhihui_qilu.academic_service import (
    AcademicService,
    DocumentTextExtractor,
    LearningMaterialParser,
    NoteOrganizer,
    SpeechToTextProvider,
)
from zhihui_qilu.config import Settings, get_settings
from zhihui_qilu.core.models import AgentRequest, AgentResponse
from zhihui_qilu.credit_service import CreditWarningService
from zhihui_qilu.skills.base import BaseSkill
from zhihui_qilu.speech_service import AsrUnavailableError, MimoAsrService

# 浏览器 base64 上传的硬上限；语音链路另有 mimo_asr_max_bytes，取两者较小值。
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# 前端只渲染有限数量的片段，避免一次上传把响应撑成几 MB。
_MAX_SEGMENTS = 400
# 没有真实时长时，中文口语按 4.5 字/秒估算时间轴。
_ESTIMATED_CHARS_PER_SECOND = 4.5

_AUDIO_FORMATS = {
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
    "audio/mp4": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "aac",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
    "video/x-matroska": "mkv",
}

_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;])|\n+")


def _decode_base64(value: object) -> bytes:
    """Decode a bare or data-URL base64 payload, raising ValueError with a readable reason."""
    text = str(value or "").strip()
    if not text:
        raise ValueError("没有收到文件内容")
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    compact = re.sub(r"\s+", "", text)
    try:
        return base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("文件内容不是合法的 base64 编码") from None


def _audio_format(mime_type: str) -> str:
    """Map a browser MIME type onto the short format token the ASR endpoint expects."""
    cleaned = str(mime_type or "").split(";", 1)[0].strip().lower()
    if cleaned in _AUDIO_FORMATS:
        return _AUDIO_FORMATS[cleaned]
    subtype = cleaned.split("/", 1)[-1] if "/" in cleaned else cleaned
    subtype = re.sub(r"[^a-z0-9]", "", subtype)
    return subtype or "wav"


def _coerce_duration(value: object) -> float | None:
    """Accept an optional client-measured duration; reject nonsense silently."""
    try:
        duration = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return duration if 0 < duration <= 24 * 3600 else None


def _split_into_segments(text: str, duration_seconds: float | None = None) -> list[TranscriptSegment]:
    """Split a transcript blob into ordered, monotonically timed segments.

    The ASR provider returns one text blob without word timings, so the timeline is either
    scaled across the client-measured duration or estimated from the character rate.
    """
    cleaned = re.sub(r"[ \t\u3000]+", " ", str(text or "")).strip()
    if not cleaned:
        raise ValueError("没有识别到可整理的文本内容")
    pieces = [piece.strip() for piece in _SENTENCE_BOUNDARY.split(cleaned) if piece and piece.strip()]
    if not pieces:
        raise ValueError("没有识别到可整理的文本内容")
    if len(pieces) > _MAX_SEGMENTS:
        step = math.ceil(len(pieces) / _MAX_SEGMENTS)
        pieces = ["".join(pieces[index:index + step]) for index in range(0, len(pieces), step)]

    total_chars = sum(len(piece) for piece in pieces) or 1
    measured = duration_seconds if duration_seconds and duration_seconds > 0 else None
    segments: list[TranscriptSegment] = []
    consumed = 0
    previous_end = 0
    for piece in pieces:
        start_chars = consumed
        consumed += len(piece)
        if measured is not None:
            start = int(round(measured * start_chars / total_chars))
            end = int(round(measured * consumed / total_chars))
        else:
            start = int(round(start_chars / _ESTIMATED_CHARS_PER_SECOND))
            end = int(round(consumed / _ESTIMATED_CHARS_PER_SECOND))
        start = max(start, previous_end)
        end = max(end, start + 1)
        previous_end = end
        segments.append(TranscriptSegment(start_seconds=start, end_seconds=end, text=piece))
    return segments


class _MimoSpeechProvider(SpeechToTextProvider):
    """Adapt the MiMo-ASR chat endpoint onto the timestamped transcript port."""

    def __init__(self, service: MimoAsrService, duration_seconds: float | None = None) -> None:
        self._service = service
        self._duration_seconds = duration_seconds

    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> list[TranscriptSegment]:
        result = await self._service.transcribe(audio_bytes, _audio_format(mime_type))
        return _split_into_segments(result.text, self._duration_seconds)


class _CapturingProvider(SpeechToTextProvider):
    """Remember the segments produced for this request so the UI can jump back to the source."""

    def __init__(self, inner: SpeechToTextProvider) -> None:
        self._inner = inner
        self.segments: list[TranscriptSegment] = []

    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> list[TranscriptSegment]:
        self.segments = await self._inner.transcribe(audio_bytes, mime_type)
        return self.segments


class _LocalDocumentExtractor(DocumentTextExtractor):
    """Extract text from the document formats the desk accepts using already-installed libraries."""

    _PLAIN_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".tsv", ".log", ".json", ".text", ""}

    async def extract(self, document_bytes: bytes, filename: str) -> list[TranscriptSegment]:
        if not document_bytes:
            raise ValueError("文档内容为空，请重新选择文件")
        suffix = os.path.splitext(filename)[1].lower()
        if suffix in self._PLAIN_SUFFIXES:
            text = self._decode_text(document_bytes)
        elif suffix == ".pdf":
            text = self._pdf_text(document_bytes)
        elif suffix == ".docx":
            text = self._docx_text(document_bytes)
        elif suffix == ".doc":
            raise ValueError("旧版 .doc 暂不支持，请另存为 .docx 后重试")
        else:
            raise ValueError(f"暂不支持 {suffix or '该'} 格式，请上传 txt / md / csv / pdf / docx")
        return _split_into_segments(text, None)

    @staticmethod
    def _decode_text(data: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError("无法识别文档编码，请另存为 UTF-8 后重试")

    @staticmethod
    def _pdf_text(data: bytes) -> str:
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError("当前环境缺少 PDF 解析库 pypdf，请改用 txt 或 docx") from None
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [(page.extract_text() or "") for page in reader.pages]
        except Exception as exc:  # noqa: BLE001 - third-party parser raises many types
            raise ValueError(f"PDF 文本提取失败：{exc}") from exc
        text = "\n".join(pages).strip()
        if not text:
            raise ValueError("这个 PDF 里没有可提取的文字（可能是扫描件），请先转成文本")
        return text

    @staticmethod
    def _docx_text(data: bytes) -> str:
        try:
            from docx import Document
        except ImportError:
            raise ValueError("当前环境缺少 Word 解析库 python-docx，请改用 txt") from None
        try:
            document = Document(io.BytesIO(data))
            blocks = [paragraph.text for paragraph in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    blocks.append(" | ".join(cell.text.strip() for cell in row.cells))
        except Exception as exc:  # noqa: BLE001 - third-party parser raises many types
            raise ValueError(f"Word 文本提取失败：{exc}") from exc
        text = "\n".join(block for block in blocks if block and block.strip()).strip()
        if not text:
            raise ValueError("这个 Word 文档里没有可提取的文字")
        return text


class _CapturingExtractor(DocumentTextExtractor):
    """Remember the segments produced for this request so the UI can jump back to the source."""

    def __init__(self, inner: DocumentTextExtractor) -> None:
        self._inner = inner
        self.segments: list[TranscriptSegment] = []

    async def extract(self, document_bytes: bytes, filename: str) -> list[TranscriptSegment]:
        self.segments = await self._inner.extract(document_bytes, filename)
        return self.segments


def _select_segments(segments: list[TranscriptSegment], note: StructuredNote) -> list[TranscriptSegment]:
    """Keep the response bounded while never dropping a segment a todo timestamp points at."""
    if len(segments) <= _MAX_SEGMENTS:
        return segments
    wanted = {item.timestamp_seconds for item in note.todo_items}
    chosen: dict[int, TranscriptSegment] = {
        index: segment for index, segment in enumerate(segments) if segment.start_seconds in wanted
    }
    for index, segment in enumerate(segments):
        if len(chosen) >= _MAX_SEGMENTS:
            break
        chosen.setdefault(index, segment)
    return [chosen[index] for index in sorted(chosen)]


def _note_payload(note: StructuredNote, segments: list[TranscriptSegment], source: dict[str, Any]) -> dict[str, Any]:
    """Flatten a StructuredNote plus the segments that produced it into one JSON-safe payload."""
    payload = note.model_dump(mode="json")
    payload["segments"] = [segment.model_dump(mode="json") for segment in _select_segments(segments, note)]
    payload["source"] = source
    return payload


class AcademicSkill(BaseSkill):
    """Expose bounded, structured Task 4 operations through the central router."""

    skill_id = "academic"
    display_name = "考研复试模拟与笔记整理"

    def __init__(self, service: AcademicService, organizer: NoteOrganizer | None = None, settings: Settings | None = None) -> None:
        self._service = service
        self._organizer = organizer or NoteOrganizer()
        self._settings = settings or get_settings()
        self._credit = CreditWarningService()
        # 复用同一个 httpx 客户端；未配置密钥时 available 为 False，只在调用时才真正发请求。
        self._asr = MimoAsrService(self._settings)

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Dispatch interview planning, assessment, or transcript/audio/document organization actions."""
        action = str(request.payload.get("action", ""))
        if action == "start_interview":
            session = self._service.simulator.start(InterviewConfig.model_validate(request.payload.get("config", {})))
            return AgentResponse(success=True, message="复试模拟已创建", data=session.model_dump(mode="json"))
        if action == "evaluate_interview":
            evaluation = await self._service.evaluate_and_remember(request.context.user_id, request.context.session_id, request.text)
            return AgentResponse(success=True, message="五维评估已生成", data=evaluation.model_dump(mode="json"))
        if action == "organize_transcript":
            return self._organize_transcript(request)
        if action == "organize_audio":
            return await self._organize_audio(request)
        if action == "organize_document":
            return await self._organize_document(request)
        if action == "credit_warning":
            return self._credit_warning(request)
        return AgentResponse(success=False, message="不支持的学业成长操作", data={"supported_actions": list(SUPPORTED_ACTIONS)})

    def _credit_warning(self, request: AgentRequest) -> AgentResponse:
        """按学校学业预警办法做一次自检，缺参数时回一句能照着填的提示。"""
        payload = request.payload
        try:
            assessment = self._credit.assess(
                grade=int(payload.get("grade", 0)),
                program_years=int(payload.get("program_years", 0)),
                required_credits=float(payload.get("required_credits", 0)),
                earned_credits=float(payload.get("earned_credits", 0)),
                year_credits=float(payload.get("year_credits", 0)),
                failed_courses=int(payload.get("failed_courses", 0) or 0),
            )
        except (TypeError, ValueError) as exc:
            return AgentResponse(success=False, message=f"学分数据填得不对：{exc}")
        labels = {"ok": "学分进度正常", "watch": "有需要留意的信号", "warning": "已命中学校预警标准"}
        return AgentResponse(
            success=True,
            message=f"{labels[assessment.level]}（累计完成 {assessment.progress * 100:.1f}%）",
            data={
                "level": assessment.level,
                "progress": assessment.progress,
                "required_credits": assessment.required_credits,
                "earned_credits": assessment.earned_credits,
                "triggers": [trigger.__dict__ for trigger in assessment.triggers],
                "student_steps": assessment.student_steps,
                "school_steps": assessment.school_steps,
                "note": assessment.note,
            },
        )

    def _organize_transcript(self, request: AgentRequest) -> AgentResponse:
        """Organize pasted transcript lines; an empty box is a user error, not a server fault."""
        try:
            segments = [TranscriptSegment.model_validate(item) for item in request.payload.get("segments", [])]
            if not segments:
                return AgentResponse(success=False, message="左侧还没有内容，请先粘贴转录文本，或上传音频 / 文档")
            note = self._organizer.organize(segments)
        except ValueError as exc:
            return AgentResponse(success=False, message=f"转录片段不可用：{exc}")
        except Exception as exc:  # noqa: BLE001 - never leak a 500 for user-supplied input
            return AgentResponse(success=False, message=f"整理失败：{exc}")
        source = {"kind": "text", "name": "文本粘贴", "duration_seconds": None, "timestamp_source": "segment"}
        return AgentResponse(success=True, message="结构化笔记已生成", data=_note_payload(note, segments, source))

    async def _organize_audio(self, request: AgentRequest) -> AgentResponse:
        """Transcribe an uploaded recording through MiMo-ASR, then reuse the shared note format."""
        try:
            raw = _decode_base64(request.payload.get("audio_base64", ""))
        except ValueError as exc:
            return AgentResponse(success=False, message=str(exc))
        if not raw:
            return AgentResponse(success=False, message="音频内容为空，请重新选择文件")
        limit = min(_MAX_UPLOAD_BYTES, self._settings.mimo_asr_max_bytes)
        if len(raw) > limit:
            return AgentResponse(success=False, message=f"音频超过 {limit // (1024 * 1024)}MB，请先裁剪")
        if not self._asr.available:
            return AgentResponse(success=False, message="当前未配置语音转写服务（缺少 ZHQ_MIMO_API_KEY），可先把文字粘贴到左侧文本框整理")

        duration = _coerce_duration(request.payload.get("duration_seconds"))
        mime_type = str(request.payload.get("mime_type") or "audio/webm")
        filename = str(request.payload.get("filename") or "录音")
        provider = _CapturingProvider(_MimoSpeechProvider(self._asr, duration))
        parser = LearningMaterialParser(organizer=self._organizer, speech_provider=provider)
        try:
            note = await parser.organize_audio(raw, mime_type)
        except AsrUnavailableError as exc:
            return AgentResponse(success=False, message=f"语音转写失败：{exc}")
        except ValueError as exc:
            return AgentResponse(success=False, message=str(exc))
        except Exception as exc:  # noqa: BLE001 - never leak a 500 for user-supplied input
            return AgentResponse(success=False, message=f"音频整理失败：{exc}")
        source = {
            "kind": "audio",
            "name": filename,
            "duration_seconds": duration,
            "mime_type": mime_type,
            "bytes": len(raw),
            "timestamp_source": "measured" if duration else "estimated",
        }
        return AgentResponse(success=True, message="音频已整理为结构化笔记", data=_note_payload(note, provider.segments, source))

    async def _organize_document(self, request: AgentRequest) -> AgentResponse:
        """Extract text from an uploaded document, then reuse the shared note format."""
        try:
            raw = _decode_base64(request.payload.get("document_base64", ""))
        except ValueError as exc:
            return AgentResponse(success=False, message=str(exc))
        if not raw:
            return AgentResponse(success=False, message="文档内容为空，请重新选择文件")
        if len(raw) > _MAX_UPLOAD_BYTES:
            return AgentResponse(success=False, message="文档超过 20MB")

        filename = str(request.payload.get("filename") or "upload.txt")
        extractor = _CapturingExtractor(_LocalDocumentExtractor())
        parser = LearningMaterialParser(organizer=self._organizer, document_extractor=extractor)
        try:
            note = await parser.organize_document(raw, filename)
        except ValueError as exc:
            return AgentResponse(success=False, message=str(exc))
        except Exception as exc:  # noqa: BLE001 - never leak a 500 for user-supplied input
            return AgentResponse(success=False, message=f"文档整理失败：{exc}")
        source = {
            "kind": "document",
            "name": filename,
            "duration_seconds": None,
            "bytes": len(raw),
            "timestamp_source": "estimated",
        }
        return AgentResponse(success=True, message="文档已整理为结构化笔记", data=_note_payload(note, extractor.segments, source))


supported_actions = ["start_interview", "evaluate_interview", "organize_transcript", "organize_audio", "organize_document", "credit_warning"]
SUPPORTED_ACTIONS = tuple(supported_actions)
