import asyncio

from zhihui_qilu.academic_models import InterviewConfig, InterviewDuration, InterviewFocus, TranscriptSegment
from zhihui_qilu.academic_service import AcademicService, InterviewSimulator, LearningMaterialParser, NoteOrganizer, SpeechToTextProvider
from zhihui_qilu.config import Settings
from zhihui_qilu.memory.in_memory import InMemoryMemorySystem


def test_interview_plan_honors_duration_and_english_focus() -> None:
    session = InterviewSimulator().start(InterviewConfig(major="人工智能", duration_minutes=InterviewDuration.MINUTES_5, focus=InterviewFocus.ENGLISH))
    assert len(session.questions) == 3
    assert sum(question.language == "en" for question in session.questions) == 2
    assert len(session.prompt_chain) == 3


def test_evaluation_is_json_ready_and_remembered() -> None:
    asyncio.run(_evaluate())


async def _evaluate() -> None:
    memory = InMemoryMemorySystem()
    evaluation = await AcademicService(memory, Settings(environment="test")).evaluate_and_remember("u1", "s1", "首先我会验证实验数据，因此调整模型。 I would validate the method and explain the result.")
    assert 0 <= evaluation.english.score <= 100
    assert len(await memory.query(user_id="u1")) == 1


def test_note_organizer_extracts_summary_tree_and_timestamped_todos() -> None:
    note = NoteOrganizer().organize([
        TranscriptSegment(start_seconds=0, end_seconds=15, text="本次组会讨论了算法实验设计。"),
        TranscriptSegment(start_seconds=16, end_seconds=30, text="需要：周五前补充对照实验。"),
    ])
    assert len(note.three_sentence_summary) == 3
    assert "# 知识树" in note.markdown_knowledge_tree
    assert note.todo_items[0].timestamp_seconds == 16


class FakeAsr(SpeechToTextProvider):
    async def transcribe(self, audio_bytes: bytes, mime_type: str) -> list[TranscriptSegment]:
        return [TranscriptSegment(start_seconds=3, end_seconds=8, text="待办：整理实验记录")]


def test_audio_parser_uses_injected_asr_provider() -> None:
    note = asyncio.run(LearningMaterialParser(speech_provider=FakeAsr()).organize_audio(b"audio", "audio/wav"))
    assert note.todo_items[0].timestamp_seconds == 3
