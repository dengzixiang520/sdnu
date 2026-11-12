"""语音适配器：Breeze Blue 流式合成 + 小米 MiMo 语音识别。

**合成**（导师说话）用 Breeze Blue 流式 TTS。
为什么不用浏览器自带的 ``speechSynthesis``：
    1. 中文音色在 Chrome/Edge 上基本是逐字拼接的机械音，投屏到答辩现场听感很差；
    2. 无法指定语气、情绪和语速细节，三位导师会变成同一个声音；
    3. 无法在服务端做缓存，同一句开场白每次都要重新合成。

实测数据（同一段约 120 字中文，breeze-tts-2）：
    同步接口 ``/v1/text-to-speech/{voice_id}``      13.08s 才拿到完整音频
    流式接口 ``/v1/text-to-speech/{voice_id}/stream``  首字节 2.00s，6.54s 播完
因此现场只走流式；完整音频写入磁盘缓存，重复提问（例如"再讲一遍"）零延迟。

**识别**（考生说话）用小米 MiMo-ASR。
为什么不用浏览器 Web Speech API：它把音频送到 Google 的在线识别服务，
国内网络基本连不上，表现就是"麦克风有信号但一个字都不出"。
MiMo 的接口形态比较特别，不是 Whisper 风格的 ``/v1/audio/transcriptions``（实测 404），
而是复用 ``/v1/chat/completions``，用一个 ``input_audio`` part 送音频；
网关有两条硬约束：必须恰好一个 input_audio，且不能带任何 text part。

实测（Breeze 生成已知中文文本再喂回来，字级命中）：
    13.1s 整段 → 2.57s，100%
    5s 分块   → 1.84s
    2s 以下   → 丢字甚至幻觉（0.6s 会被识别成 "Yeah."）
固定开销约 1.3–1.5s 且与音频长短无关，所以分块不会更快；
前端因此按"停顿处切句"而不是固定时长切，保证每块是完整句子。
"""

from __future__ import annotations

import base64
import hashlib
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx

from zhihui_qilu.config import Settings

_CHUNK = 64 * 1024


class SpeechUnavailableError(RuntimeError):
    """语音通道不可用：未配置密钥、上游报错或网络中断。"""


@dataclass(frozen=True, slots=True)
class SpeechRequest:
    """一次合成的完整参数，也是磁盘缓存的唯一键。"""

    text: str
    voice_id: str
    instructions: str = ""
    speed: float = 1.0
    guidance_scale: float = 4.0
    language: str = "zh"

    @property
    def cache_key(self) -> str:
        """按全部影响音色的参数取哈希，任何一项变化都不会命中旧缓存。"""
        raw = "\x1f".join(
            (
                self.voice_id,
                self.language,
                f"{self.speed:.3f}",
                f"{self.guidance_scale:.3f}",
                self.instructions,
                self.text,
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _iter_file(path: Path) -> AsyncIterator[bytes]:
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                return
            yield chunk


class BreezeSpeechService:
    """把 Breeze TTS 包装成"注册 → 取流"两段式接口。

    浏览器的 ``<audio src>`` 只能发 GET，无法携带长文本；因此先 POST 注册参数换一个
    短 token，再用 ``GET /tts/{token}.mp3`` 拉流。这样既保留真正的边合成边播放，
    也不用把正文塞进 URL。
    """

    _TOKEN_TTL_SECONDS = 900
    _TOKEN_LIMIT = 256

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.breeze_base_url.rstrip("/")
        self._cache_dir = Path(settings.breeze_tts_cache_dir)
        self._pending: OrderedDict[str, tuple[SpeechRequest, float]] = OrderedDict()
        self._client: httpx.AsyncClient | None = None

    # ---------------------------------------------------------------- 状态

    @property
    def available(self) -> bool:
        """是否配置了可用的 Breeze 密钥。"""
        return self._settings.breeze_api_key is not None and bool(
            self._settings.breeze_api_key.get_secret_value().strip()
        )

    @property
    def model_id(self) -> str:
        return self._settings.breeze_tts_model

    # ---------------------------------------------------------------- token

    def register(self, request: SpeechRequest) -> str:
        """登记一次合成请求并返回可放进 URL 的短 token。"""
        token = request.cache_key[:32]
        now = time.monotonic()
        self._pending[token] = (request, now)
        self._pending.move_to_end(token)
        self._evict(now)
        return token

    def resolve(self, token: str) -> SpeechRequest | None:
        """取回 token 对应的请求；过期或不存在返回 ``None``。"""
        entry = self._pending.get(token)
        if entry is None:
            return None
        request, created = entry
        if time.monotonic() - created > self._TOKEN_TTL_SECONDS:
            self._pending.pop(token, None)
            return None
        self._pending.move_to_end(token)
        return request

    def _evict(self, now: float) -> None:
        while len(self._pending) > self._TOKEN_LIMIT:
            self._pending.popitem(last=False)
        stale = [key for key, (_, created) in self._pending.items() if now - created > self._TOKEN_TTL_SECONDS]
        for key in stale:
            self._pending.pop(key, None)

    # ---------------------------------------------------------------- 缓存

    def _cache_path(self, request: SpeechRequest) -> Path:
        return self._cache_dir / f"{request.cache_key}.mp3"

    def is_cached(self, request: SpeechRequest) -> bool:
        path = self._cache_path(request)
        return path.exists() and path.stat().st_size > 0

    def _prune_cache(self) -> None:
        limit = self._settings.breeze_tts_cache_items
        if limit <= 0 or not self._cache_dir.exists():
            return
        files = sorted(
            (item for item in self._cache_dir.glob("*.mp3") if item.is_file()),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for stale in files[limit:]:
            stale.unlink(missing_ok=True)

    # ---------------------------------------------------------------- 上游

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._settings.breeze_timeout_seconds, connect=15.0))
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    def _payload(self, request: SpeechRequest) -> dict[str, object]:
        body: dict[str, object] = {
            "text": request.text,
            "model_id": self._settings.breeze_tts_model,
            "language_code": request.language,
            "voice_settings": {
                "guidance_scale": request.guidance_scale,
                "speed": request.speed,
            },
        }
        if request.instructions.strip():
            body["instructions"] = request.instructions.strip()
        return body

    async def _open_upstream(self, request: SpeechRequest) -> httpx.Response:
        if not self.available:
            raise SpeechUnavailableError("未配置 ZHQ_BREEZE_API_KEY，无法生成导师语音")
        client = self._ensure_client()
        try:
            pending = client.build_request(
                "POST",
                f"{self._base}/v1/text-to-speech/{request.voice_id}/stream",
                json=self._payload(request),
                params={"output_format": "mp3"},
                headers={"xi-api-key": self._settings.breeze_api_key.get_secret_value()},
            )
            response = await client.send(pending, stream=True)
        except httpx.HTTPError as exc:  # 网络层失败
            raise SpeechUnavailableError("语音合成通道连接失败") from exc
        if response.status_code != 200:
            detail = (await response.aread())[:400].decode("utf-8", "replace")
            await response.aclose()
            raise SpeechUnavailableError(f"语音合成失败（HTTP {response.status_code}）：{detail}")
        return response

    # ---------------------------------------------------------------- 取流

    async def stream(self, request: SpeechRequest) -> AsyncIterator[bytes]:
        """优先读缓存；未命中则边转发上游字节边写缓存。"""
        path = self._cache_path(request)
        if path.exists() and path.stat().st_size > 0:
            async for chunk in _iter_file(path):
                yield chunk
            return

        response = await self._open_upstream(request)
        temp = path.with_suffix(".part")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with temp.open("wb") as handle:
                async for chunk in response.aiter_bytes(8192):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    yield chunk
            temp.replace(path)
            self._prune_cache()
        finally:
            await response.aclose()
            if temp.exists() and not path.exists():
                temp.unlink(missing_ok=True)

    async def synthesize(self, request: SpeechRequest) -> bytes:
        """一次性拿完整音频，用于预热与自检。"""
        buffer = bytearray()
        async for chunk in self.stream(request):
            buffer += chunk
        return bytes(buffer)

    async def probe(self) -> dict[str, object]:
        """轻量自检：返回账户余额与本次合成耗时，便于现场排障。"""
        if not self.available:
            return {"available": False, "reason": "未配置 ZHQ_BREEZE_API_KEY"}
        client = self._ensure_client()
        info: dict[str, object] = {"available": True, "model": self.model_id}
        try:
            response = await client.get(
                f"{self._base}/v1/balance",
                headers={"xi-api-key": self._settings.breeze_api_key.get_secret_value()},
            )
            if response.status_code == 200:
                info["balance"] = response.json().get("balance")
            else:
                info["balance_error"] = response.status_code
        except httpx.HTTPError as exc:
            info["balance_error"] = str(exc)[:120]
        return info


# --------------------------------------------------------------------------- 识别


class AsrUnavailableError(RuntimeError):
    """语音识别不可用：未配置密钥、音频不合规或上游报错。"""


@dataclass(frozen=True, slots=True)
class AsrResult:
    """一次识别结果。``elapsed_ms`` 用于在报告里给出真实的端到端延迟。"""

    text: str
    elapsed_ms: int
    model: str


class MimoAsrService:
    """小米 MiMo-ASR 的适配层。

    这个接口不是 OpenAI 的 Whisper 风格端点，而是复用 chat/completions：
    一个 ``input_audio`` part 承载 base64 音频，识别指令由网关自己注入。
    所以这里不要往 content 里塞任何 text part，塞了会直接 400。
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base = settings.mimo_base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    @property
    def available(self) -> bool:
        """是否配置了 MiMo 密钥。"""
        key = self._settings.mimo_api_key
        return key is not None and bool(key.get_secret_value().strip())

    @property
    def model_id(self) -> str:
        return self._settings.mimo_asr_model

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.mimo_asr_timeout_seconds, connect=15.0)
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def transcribe(self, audio: bytes, fmt: str = "wav") -> AsrResult:
        """把一段音频转成文字。音频建议 ≥2 秒，否则会丢字或产生幻觉。"""
        if not self.available:
            raise AsrUnavailableError("未配置 ZHQ_MIMO_API_KEY，无法做语音识别")
        if not audio:
            raise AsrUnavailableError("音频为空")
        if len(audio) > self._settings.mimo_asr_max_bytes:
            raise AsrUnavailableError(f"音频过大：{len(audio)} 字节，上限 {self._settings.mimo_asr_max_bytes}")
        payload = {
            "model": self.model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": base64.b64encode(audio).decode("ascii"), "format": fmt},
                        }
                    ],
                }
            ],
        }
        started = time.monotonic()
        try:
            response = await self._ensure_client().post(
                f"{self._base}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self._settings.mimo_api_key.get_secret_value()}"},
            )
        except httpx.HTTPError as exc:
            raise AsrUnavailableError("语音识别通道连接失败") from exc
        elapsed_ms = round((time.monotonic() - started) * 1000)
        if response.status_code != 200:
            detail = response.text[:300].replace("\n", " ")
            raise AsrUnavailableError(f"语音识别失败（HTTP {response.status_code}）：{detail}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AsrUnavailableError("语音识别返回格式异常") from exc
        return AsrResult(text=str(content or "").strip(), elapsed_ms=elapsed_ms, model=self.model_id)
