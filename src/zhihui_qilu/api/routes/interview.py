"""沉浸式复试现场接口：考官名册、导师语音流、下一问、复盘报告。

语音链路刻意做成两段式：

    POST /tts        文本 → 短 token（同时把 token 登记进服务端 LRU）
    GET  /tts/{t}.mp3  token → audio/mpeg 流（命中磁盘缓存则直接吐文件）

浏览器 ``<audio src>`` 只能发 GET，无法带长文本，所以必须先换 token。
这样既保留了 Breeze 流式合成的首字节 2 秒优势，也不用把正文塞进 URL。
"""

from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from zhihui_qilu.interview_service import (
    EXAMINER_INDEX,
    GREETINGS,
    InterviewDirector,
    InterviewReport,
    ReportRequest,
    TurnRequest,
    TurnResponse,
    build_report,
    examiner_public,
    plan_for,
    speech_profile,
)
from zhihui_qilu.speech_service import (
    AsrUnavailableError,
    SpeechRequest,
    SpeechUnavailableError,
)

router = APIRouter(prefix="/api/v1/interview", tags=["interview"])


class TtsBody(BaseModel):
    """前端只需要给"谁说"和"说什么"，音色与语气由服务端按考官档案决定。"""

    text: str = Field(min_length=1, max_length=1200)
    examiner: str = Field(default="host", max_length=20)
    language: str = Field(default="zh", pattern="^(zh|en)$")


class TtsTicket(BaseModel):
    token: str
    url: str
    cached: bool
    examiner: str
    voice_name: str
    chars: int


class AsrBody(BaseModel):
    """一段待识别的音频。前端按停顿切句后逐块送来，做准实时字幕。"""

    audio: str = Field(min_length=16, description="base64 编码的音频")
    format: str = Field(default="wav", pattern="^(wav|mp3|pcm|flac|m4a|ogg)$")


class AsrTicket(BaseModel):
    text: str
    elapsed_ms: int
    model: str


def _speech_request(body: TtsBody) -> SpeechRequest:
    if body.examiner not in EXAMINER_INDEX:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"未知考官：{body.examiner}")
    profile = speech_profile(body.examiner, body.text, body.language)
    return SpeechRequest(text=body.text.strip(), **profile)


@router.get("/panel")
async def get_panel(request: Request, minutes: int = 15) -> dict[str, object]:
    """考官名册 + 本次复试的题量与语音通道状态。"""
    speech = request.app.state.container.speech
    stages = plan_for(minutes)
    return {
        "examiners": [examiner_public(item) for item in EXAMINER_INDEX.values()],
        "minutes": minutes,
        "steps": len(stages),
        "plan": [
            {
                "step": index,
                "examiner": stage.examiner,
                "examiner_name": EXAMINER_INDEX[stage.examiner]["name"],
                "intent": stage.intent,
                "language": stage.language,
                "hard": stage.hard,
            }
            for index, stage in enumerate(stages)
        ],
        "speech": {
            "available": speech.available,
            "model": speech.model_id,
            "note": "导师语音由 Breeze Blue 流式合成，首字节约 2 秒" if speech.available else "未配置 ZHQ_BREEZE_API_KEY，将回落到浏览器语音合成",
        },
        "asr": {
            "available": request.app.state.container.asr.available,
            "model": request.app.state.container.asr.model_id,
            "note": "考生语音由小米 MiMo-ASR 转写，说完一句约 2 秒出字"
            if request.app.state.container.asr.available
            else "未配置 ZHQ_MIMO_API_KEY，语音转写不可用，只能文字作答",
        },
    }


@router.post("/tts", response_model=TtsTicket)
async def create_tts(body: TtsBody, request: Request) -> TtsTicket:
    """登记一次合成，返回可直接放进 ``<audio src>`` 的地址。"""
    speech = request.app.state.container.speech
    payload = _speech_request(body)
    token = speech.register(payload)
    examiner = EXAMINER_INDEX[body.examiner]
    return TtsTicket(
        token=token,
        url=f"/api/v1/interview/tts/{token}.mp3",
        cached=speech.is_cached(payload),
        examiner=body.examiner,
        voice_name=examiner["voice_name"],
        chars=len(payload.text),
    )


@router.get("/tts/{token}.mp3")
async def stream_tts(token: str, request: Request) -> StreamingResponse:
    """把导师语音以 MP3 流吐给浏览器；缓存命中时是本地文件直读。"""
    speech = request.app.state.container.speech
    payload = speech.resolve(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="语音 token 已过期，请重新生成")
    try:
        stream = speech.stream(payload)
        first = await anext(stream)
    except SpeechUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except StopAsyncIteration as exc:  # 上游返回 200 但没有任何字节
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="语音合成没有返回音频") from exc

    async def body():
        yield first
        async for chunk in stream:
            yield chunk

    return StreamingResponse(
        body(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400", "X-Accel-Buffering": "no"},
    )


@router.post("/asr", response_model=AsrTicket)
async def transcribe(body: AsrBody, request: Request) -> AsrTicket:
    """把一段考生语音转成文字。

    前端按"说完一句就切"的方式送块，每块 2–8 秒；块太短（<2s）会丢字甚至幻觉，
    所以切分逻辑放在前端用能量谷做，这里只负责转发与错误归一化。
    """
    service = request.app.state.container.asr
    if not service.available:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="未配置 ZHQ_MIMO_API_KEY，语音识别不可用")
    try:
        audio = base64.b64decode(body.audio, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="音频 base64 解码失败") from exc
    try:
        result = await service.transcribe(audio, body.format)
    except AsrUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return AsrTicket(text=result.text, elapsed_ms=result.elapsed_ms, model=result.model)


@router.get("/opening")
async def get_opening(request: Request, minutes: int = 15) -> dict[str, object]:
    """开场白：组长先说明规则，两位考官各自我介绍一句。"""
    speech = request.app.state.container.speech
    lines: list[dict[str, object]] = []
    for examiner_id in ("host", "major", "english"):
        template = GREETINGS[examiner_id]
        text = template.format(n=minutes) if "{n}" in template else template
        payload = SpeechRequest(text=text, **speech_profile(examiner_id, text, "zh"))
        token = speech.register(payload)
        examiner = EXAMINER_INDEX[examiner_id]
        lines.append(
            {
                "examiner": examiner_id,
                "examiner_name": examiner["name"],
                "examiner_title": examiner["title"],
                "text": text,
                "url": f"/api/v1/interview/tts/{token}.mp3",
                "cached": speech.is_cached(payload),
            }
        )
    return {"minutes": minutes, "lines": lines}


@router.post("/turn", response_model=TurnResponse)
async def next_turn(body: TurnRequest, request: Request) -> TurnResponse:
    """按固定节奏请下一位考官提问；大模型只负责把措辞说得更自然。"""
    container = request.app.state.container
    director = InterviewDirector(container.ai_provider)
    return await director.next_turn(body)


@router.post("/report", response_model=InterviewReport)
async def create_report(body: ReportRequest) -> InterviewReport:
    """把前端实测的语速、停顿、音量等指标换算成五维评分。

    这条接口是纯函数式的换算，不写库、不读会话，因此不需要身份头；
    前端用普通 fetch 调用即可，避免因为缺 X-User-Id 而 401。
    """
    return build_report(body)
