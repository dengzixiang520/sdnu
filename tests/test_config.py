from pydantic import ValidationError

from zhihui_qilu.config import Settings


def test_production_rejects_default_secret() -> None:
    try:
        Settings(environment="production", ai_base_url="https://ai.example", ai_api_key="key")
    except ValidationError:
        return
    raise AssertionError("Production settings must reject the development default secret")


def test_development_defaults_are_runnable() -> None:
    assert Settings().ephemeral_memory_ttl_seconds == 14_400
