"""Composition root for application dependencies."""

from zhihui_qilu.agents.router import SuperAgentRouter
from zhihui_qilu.ai.provider import DeepSeekProvider, OfflineProvider
from zhihui_qilu.ai.service import CampusConversationService
from zhihui_qilu.academic_service import AcademicService
from zhihui_qilu.config import Settings
from zhihui_qilu.core.security import SecurityIsolationGateway
from zhihui_qilu.memory.in_memory import InMemoryMemorySystem
from zhihui_qilu.memory.sqlite import SqliteMemorySystem
from zhihui_qilu.skills.dormitory import DormitorySkill
from zhihui_qilu.skills.academic import AcademicSkill
from zhihui_qilu.skills.innovation import InnovationSkill
from zhihui_qilu.skills.document_engine import DocumentEngineSkill
from zhihui_qilu.skills.wellbeing import WellbeingSkill
from zhihui_qilu.competition_service import CompetitionService
from zhihui_qilu.points_service import PointsService
from zhihui_qilu.speech_service import BreezeSpeechService, MimoAsrService
from zhihui_qilu.system_integration import SystemIntegrationService
from zhihui_qilu.wellbeing_service import WellbeingService


class PlatformContainer:
    """Owns Task 1 infrastructure and exposes future dependency-injection seams."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audit_events = []
        self.memory = SqliteMemorySystem(settings.sqlite_memory_path) if settings.memory_backend == "sqlite" else InMemoryMemorySystem()
        self.security_gateway = SecurityIsolationGateway(settings, audit_sink=self.audit_events.append)
        if settings.ai_provider == "deepseek" and settings.ai_api_key is not None:
            self.ai_provider = DeepSeekProvider(
                api_key=settings.ai_api_key.get_secret_value(),
                base_url=settings.ai_base_url,
                model=settings.ai_model,
                connect_timeout=settings.ai_connect_timeout_seconds,
                read_timeout=settings.ai_read_timeout_seconds,
            )
        else:
            self.ai_provider = OfflineProvider()
        self.conversation = CampusConversationService(self.ai_provider, self.memory, settings)
        self.speech = BreezeSpeechService(settings)
        self.asr = MimoAsrService(settings)
        self.wellbeing = WellbeingService(self.memory, self.security_gateway, settings)
        self.academic = AcademicService(self.memory, settings)
        self.innovation = InnovationSkill()
        self.competition_service = CompetitionService("./data")
        self.points_service = PointsService("./data")
        self.system_integration = SystemIntegrationService()
        self.router = SuperAgentRouter(self.security_gateway, [WellbeingSkill(self.wellbeing), DormitorySkill(), AcademicSkill(self.academic), self.innovation, DocumentEngineSkill()])
