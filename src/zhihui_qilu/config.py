"""Application configuration loaded from environment variables and a local .env file."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed runtime settings; secrets are never included in normal logs."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ZHQ_", extra="ignore")

    app_name: str = "智汇齐鲁·全域同频"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    secret_key: SecretStr = Field(default=SecretStr("development-only-change-me"))
    ai_provider: Literal["deepseek", "offline"] = "deepseek"
    ai_base_url: str = "https://api.deepseek.com"
    ai_model: str = "deepseek-chat"
    ai_api_key: SecretStr | None = None
    ai_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    ai_read_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    ai_max_context_messages: int = Field(default=12, ge=2, le=30)

    # 课表截图识别走独立的视觉模型，不复用对话模型：两者的超时与额度诉求不同。
    # 实测（tools/bench_three_models.py，同一提示词、同一图、各 3 轮）：
    #   deepseek-flash + effort=low  平均 4.03s / 中位 5.46s
    #   deepseek-flash               平均 4.85s / 中位 6.69s
    #   mimo-v2.6-pro                平均 7.47s / 中位 7.03s
    #   mimo-v2.6-flash              平均 14.65s / 中位 15.54s
    # 四者准确率都是 100%，因此默认选最快的 deepseek-flash，MiMo 保留为可切换备选。
    # 两个模型都是推理模型，reasoning_tokens 会占用 max_tokens，额度给小了会只返回
    # reasoning_content 而 content 为空，所以这里单独放一个较大的默认值。
    # 实测（tools/diag_vision_budget.py，1080×2400 真实教务系统截图）：
    #   max_tokens=2500  → finish=length，reasoning 吃满 2500，content 为空
    #   max_tokens=8000  → 仍然 finish=length（effort=low / 默认档）
    #   max_tokens=16000 → finish=stop，reasoning 2675，content 正常
    # 真实课表比合成测试图复杂得多，推理链会长很多，所以默认值必须给到 16000。
    # effort=low 时推理最短（2675 tokens / 15.6s），比 high 的 6481 tokens / 39.3s 快一倍多。
    vision_provider: Literal["deepseek", "mimo"] = "deepseek"
    vision_effort: str | None = "low"
    vision_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    vision_max_tokens: int = Field(default=16000, ge=1024, le=32768)

    deepseek_vision_base_url: str = "https://api.deepseek.com"
    deepseek_vision_model: str = "deepseek-flash"
    deepseek_vision_api_key: SecretStr | None = None

    mimo_base_url: str = "https://api.xiaomimimo.com/v1"
    mimo_model: str = "mimo-v2.6-pro"
    mimo_api_key: SecretStr | None = None

    # 复试现场的导师语音走 Breeze Blue TTS，不用浏览器自带 speechSynthesis：
    # 后者在中文场景下是逐字拼接的机械音，投屏到答辩现场听感极差，也无法指定语气。
    # 实测（同一段 120 字中文）：同步接口 13.08s 才返回完整音频；
    # 流式接口首字节 2.0s、6.5s 播完，所以现场只走流式。
    breeze_base_url: str = "https://api.breeze.blue"
    breeze_api_key: SecretStr | None = None
    breeze_tts_model: str = "breeze-tts-2"
    breeze_timeout_seconds: float = Field(default=180.0, gt=0, le=900)
    breeze_tts_cache_dir: str = "./data/tts_cache"
    breeze_tts_cache_items: int = Field(default=400, ge=0, le=5000)

    # 复试现场的语音识别走小米 MiMo-ASR，不用浏览器 Web Speech API：
    # 后者依赖 Google 的在线识别服务，国内网络基本连不上，表现就是"麦克风有信号但不出字"。
    # 注意模型名是 asr 不是 vsr；端点也不是 Whisper 风格的 /v1/audio/transcriptions（那个是 404），
    # 而是复用 /v1/chat/completions，用一个 input_audio part 送音频，网关会注入识别指令。
    # 实测（Breeze TTS 生成已知中文文本再喂回来）：
    #   13.1s 整段 → 2.57s 出结果，字级命中 100%
    #   5s 分块   → 1.84s；2s 以下会丢字甚至幻觉，所以前端按"停顿处切句"而不是固定时长切
    mimo_asr_model: str = "mimo-v2.5-asr"
    mimo_asr_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    mimo_asr_max_bytes: int = Field(default=8 * 1024 * 1024, ge=64 * 1024, le=32 * 1024 * 1024)

    database_url: str | None = None
    redis_url: str | None = None
    memory_backend: Literal["memory", "sqlite"] = "memory"
    sqlite_memory_path: str = "./data/zhihui_qilu_memory.sqlite3"
    web_origin: str = "http://localhost:5173"
    ephemeral_memory_ttl_seconds: int = Field(default=4 * 60 * 60, gt=0)
    short_term_memory_ttl_seconds: int = Field(default=7 * 24 * 60 * 60, gt=0)
    security_rate_limit_per_minute: int = Field(default=60, gt=0)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Reject development defaults whenever the deployment is production."""
        if self.environment == "production":
            if self.secret_key.get_secret_value() == "development-only-change-me":
                raise ValueError("ZHQ_SECRET_KEY must be set to a non-default value in production")
            if self.ai_provider != "offline" and self.ai_api_key is None:
                raise ValueError("ZHQ_AI_API_KEY is required for the configured production AI provider")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable settings instance."""
    return Settings()
