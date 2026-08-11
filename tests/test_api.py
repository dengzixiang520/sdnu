from fastapi.testclient import TestClient

from zhihui_qilu.api.app import create_app
from zhihui_qilu.config import Settings


def test_development_command_bridge_executes_registered_skill() -> None:
    client = TestClient(create_app(Settings(environment="test")))
    response = client.post("/api/v1/commands", headers={"X-User-Id": "u1", "X-Session-Id": "s1", "X-User-Role": "student"}, json={"capability": "wellbeing", "action": "control", "text": "请播放雨声"})
    assert response.status_code == 200
    assert response.json()["success"] is True
