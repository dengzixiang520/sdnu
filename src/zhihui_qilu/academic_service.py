"""Task 4 services with provider ports and deterministic development-safe reference logic."""

import re
from abc import ABC, abstractmethod
from collections import Counter
from datetime import timedelta

from zhihui_qilu.academic_models import (
    DimensionScore,
    FiveDimensionEvaluation,
    InterviewConfig,
    InterviewDuration,
    InterviewFocus,
    InterviewQuestion,
    InterviewSession,
    InterviewStrictness,
    PromptMessage,
    StructuredNote,
    TodoItem,
    TranscriptSegment,
)
from zhihui_qilu.config import Settings
from zhihui_qilu.core.enums import AccessScope, MemoryTier, SensitivityLevel
from zhihui_qilu.core.models import utc_now
from zhihui_qilu.memory.base import MemorySystem
from zhihui_qilu.memory.models import MemoryRecord


class LanguageModelClient(ABC):
    """Port for an approved campus LLM provider; never call a provider directly from a Skill."""

    @abstractmethod
    async def complete(self, messages: list[PromptMessage]) -> str:
        """Generate a completion for the supplied provider-neutral prompt chain."""


class SpeechToTextProvider(ABC):
    """Port for approved ASR providers used by classroom and meeting recordings."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> list[TranscriptSegment]:
        """Produce timestamped transcript segments without retaining the raw audio in this service."""


class DocumentTextExtractor(ABC):
    """Port for PPT/PDF/Word parsing adapters."""

    @abstractmethod
    async def extract(self, document_bytes: bytes, filename: str) -> list[TranscriptSegment]:
        """Return ordered text segments extracted from an uploaded document."""


class InterviewSimulator:
    """Build duration-aware question plans and a vendor-neutral prompt chain."""

    _QUESTION_COUNTS = {InterviewDuration.MINUTES_5: 3, InterviewDuration.MINUTES_15: 8, InterviewDuration.MINUTES_30: 15}

    def start(self, config: InterviewConfig) -> InterviewSession:
        """Create an interview session with questions weighted by requested focus and duration."""
        questions = self._make_questions(config)
        return InterviewSession(config=config, prompt_chain=self.build_prompt_chain(config), questions=questions)

    def build_prompt_chain(self, config: InterviewConfig) -> list[PromptMessage]:
        """Describe immutable safety, interviewer style, and the learner's requested scope."""
        strictness_text = {
            InterviewStrictness.ENCOURAGING: "温和鼓励，指出改进点时使用建设性措辞。",
            InterviewStrictness.BALANCED: "中规中矩，按研究生复试的常规深度追问。",
            InterviewStrictness.CHALLENGING: "严格追问假设、证据和边界，但不得羞辱或贬低学生。",
        }[config.strictness]
        english_ratio = "80% 问题使用英语。" if config.focus == InterviewFocus.ENGLISH else "英语与中文问题按计划均衡安排。"
        return [
            PromptMessage(role="system", content="你是研究生复试训练导师。仅提供教育训练，不作录取承诺或人格评判。"),
            PromptMessage(role="developer", content=f"风格：{strictness_text} {english_ratio} 总时长：{config.duration_minutes} 分钟。"),
            PromptMessage(role="user", content=f"请围绕{config.major}进行模拟复试，并在每个问题后等待回答。"),
        ]

    def _make_questions(self, config: InterviewConfig) -> list[InterviewQuestion]:
        count = self._QUESTION_COUNTS[config.duration_minutes]
        english_target = round(count * 0.8) if config.focus == InterviewFocus.ENGLISH else max(1, count // 4)
        templates = [
            ("请简要介绍你的研究兴趣，以及它与本专业的联系。", "zh", "表达能力"),
            (f"请解释{config.major}中一个你最有把握的核心概念，并说明它的适用边界。", "zh", "专业深度"),
            ("Describe a project challenge and how you validated your solution.", "en", "英语水平"),
            ("如果导师质疑你的结论，你会如何回应并补充证据？", "zh", "抗压能力"),
            ("What would you do if your first research approach failed?", "en", "情绪稳定性"),
        ]
        questions: list[InterviewQuestion] = []
        for index in range(count):
            if index < english_target:
                candidates = [item for item in templates if item[1] == "en"]
                text, language, dimension = candidates[index % len(candidates)]
            else:
                candidates = [item for item in templates if item[1] == "zh"]
                text, language, dimension = candidates[(index - english_target) % len(candidates)]
            questions.append(InterviewQuestion(sequence=index + 1, question=text, language=language, dimension=dimension))
        return questions


class InterviewEvaluator:
    """Generate a conservative, explainable five-dimension training report from transcript text."""

    def evaluate(self, answers: str) -> FiveDimensionEvaluation:
        """Score observable textual signals only; empty content receives actionable low baseline guidance."""
        compact = re.sub(r"\s+", " ", answers).strip()
        words = re.findall(r"[A-Za-z]+|[\u4e00-\u9fff]+", compact)
        english_words = re.findall(r"[A-Za-z]+", compact)
        sentence_count = max(1, len(re.findall(r"[。！？.!?]", compact)))
        connectors = len(re.findall(r"因此|首先|其次|因为|however|therefore|for example", compact, flags=re.IGNORECASE))
        technical_terms = len(re.findall(r"模型|算法|实验|方法|数据|理论|model|algorithm|experiment|method", compact, flags=re.IGNORECASE))
        pressure_signals = len(re.findall(r"我会|验证|澄清|补充|复盘|first|validate|clarify", compact, flags=re.IGNORECASE))
        calm_signals = len(re.findall(r"冷静|调整|学习|计划|calm|adapt|plan", compact, flags=re.IGNORECASE))
        expression = min(95, 35 + min(40, len(words) // 3) + min(20, connectors * 4))
        professional = min(95, 30 + technical_terms * 12 + min(25, len(words) // 8))
        english = min(95, 20 + min(60, len(english_words) * 2))
        pressure = min(95, 35 + pressure_signals * 12 + min(20, sentence_count * 2))
        stability = min(95, 40 + calm_signals * 14 + min(15, connectors * 3))
        return FiveDimensionEvaluation(
            expression=self._score(expression, f"检测到 {sentence_count} 个回答句段与 {connectors} 个逻辑连接词。", "使用“观点—证据—结论”结构，控制每题回答在 1–2 分钟。"),
            professional_knowledge=self._score(professional, f"检测到 {technical_terms} 个专业方法或证据类词汇。", "为每个核心概念准备定义、实例和适用边界。"),
            english=self._score(english, f"检测到 {len(english_words)} 个英文词。", "围绕项目经历准备英语 STAR 回答，并练习追问。"),
            pressure_resilience=self._score(pressure, f"检测到 {pressure_signals} 个回应质疑或验证的行动信号。", "面对反问时先澄清前提，再说明验证路径。"),
            emotional_stability=self._score(stability, f"检测到 {calm_signals} 个调整、计划或冷静应对信号。", "练习短暂停顿后作答，避免把不确定性等同于失败。"),
        )

    @staticmethod
    def _score(score: int, evidence: str, recommendation: str) -> DimensionScore:
        return DimensionScore(score=max(0, score), evidence=evidence, recommendation=recommendation)


class AcademicService:
    """Coordinates session planning, short-term evaluation trend storage, and note organization."""

    def __init__(self, memory: MemorySystem, settings: Settings) -> None:
        self._memory = memory
        self._settings = settings
        self.simulator = InterviewSimulator()
        self.evaluator = InterviewEvaluator()

    async def evaluate_and_remember(self, user_id: str, session_id: str, answers: str) -> FiveDimensionEvaluation:
        """Store an assessment summary in short-term memory for the latest-five trend view."""
        evaluation = self.evaluator.evaluate(answers)
        record = MemoryRecord(user_id=user_id, session_id=session_id, tier=MemoryTier.SHORT_TERM, category="academic.interview_assessment", value=evaluation.model_dump(mode="json"), source_agent="academic-service", access_scope=AccessScope.OWNER, sensitivity=SensitivityLevel.INTERNAL, expires_at=utc_now() + timedelta(seconds=self._settings.short_term_memory_ttl_seconds))
        await self._memory.put(record)
        return evaluation


class NoteOrganizer:
    """Create concise summaries, a Markdown knowledge tree, and timestamped action items."""

    _TODO_MARKERS = re.compile(r"(?:待办|todo|需要|请|截止|follow\s*up|action)[:：\s]*(.+)", flags=re.IGNORECASE)

    def organize(self, segments: list[TranscriptSegment]) -> StructuredNote:
        """Organize ordered transcript segments without making up content absent from the source."""
        if not segments:
            raise ValueError("At least one transcript segment is required")
        sentences = [segment.text.strip() for segment in segments if segment.text.strip()]
        summary = self._make_summary(sentences)
        todos = self._extract_todos(segments)
        tree = self._make_tree(sentences, todos)
        return StructuredNote(three_sentence_summary=summary, markdown_knowledge_tree=tree, todo_items=todos)

    @staticmethod
    def _make_summary(sentences: list[str]) -> list[str]:
        selected = sentences[:3]
        while len(selected) < 3:
            selected.append("原始材料未提供更多内容。")
        return selected

    def _extract_todos(self, segments: list[TranscriptSegment]) -> list[TodoItem]:
        todos: list[TodoItem] = []
        for segment in segments:
            for match in self._TODO_MARKERS.finditer(segment.text):
                task = match.group(1).strip(" 。；;")
                if task:
                    todos.append(TodoItem(task=task, timestamp_seconds=segment.start_seconds))
        return todos

    @staticmethod
    def _make_tree(sentences: list[str], todos: list[TodoItem]) -> str:
        keywords = Counter(word for sentence in sentences for word in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{4,}", sentence)).most_common(5)
        topic_lines = [f"  - {word}" for word, _ in keywords] or ["  - 未能从材料中稳定提取关键词"]
        todo_lines = [f"  - [{item.timestamp_seconds:>4}s] {item.task}" for item in todos] or ["  - 暂未识别明确待办"]
        return "# 知识树\n\n- 核心主题\n" + "\n".join(topic_lines) + "\n- 待办事项\n" + "\n".join(todo_lines)


class LearningMaterialParser:
    """Connect approved ASR/document adapters to the common structured-note workflow."""

    def __init__(self, organizer: NoteOrganizer | None = None, speech_provider: SpeechToTextProvider | None = None, document_extractor: DocumentTextExtractor | None = None) -> None:
        self._organizer = organizer or NoteOrganizer()
        self._speech_provider = speech_provider
        self._document_extractor = document_extractor

    async def organize_audio(self, audio_bytes: bytes, mime_type: str) -> StructuredNote:
        """Transcribe audio through the injected provider and return the shared note format."""
        if self._speech_provider is None:
            raise RuntimeError("No SpeechToTextProvider has been configured")
        return self._organizer.organize(await self._speech_provider.transcribe(audio_bytes, mime_type))

    async def organize_document(self, document_bytes: bytes, filename: str) -> StructuredNote:
        """Extract document text through the injected provider and return the shared note format."""
        if self._document_extractor is None:
            raise RuntimeError("No DocumentTextExtractor has been configured")
        return self._organizer.organize(await self._document_extractor.extract(document_bytes, filename))
