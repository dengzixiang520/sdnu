"""网易云音乐接入：搜索、播放地址、歌词。

两条通道，按可用性自动选：

1. **本机解析服务**（可选增强）——AlgerMusicPlayer 打开后会在
   ``127.0.0.1:30488`` 起一个 netease-cloud-music-api，能拿到更高音质、也能解析
   一部分受限曲目。地址由 ``ZHQ_MUSIC_API`` 配置，留空即完全不用。
2. **网易云公开接口**（默认兜底）——``/api/search/get``、``/song/media/outer/url``、
   ``/api/song/lyric``。不需要密钥、不需要登录、不依赖任何本机进程，缺点是高音质
   与部分版权曲目取不到。

前端只跟本服务同源通信，所以端口、重定向、失败降级都收在这里，浏览器不用知道。
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status

router = APIRouter(prefix="/api/v1/music", tags=["music"])

# 网易云会校验 UA/Referer，缺了直接返回 404 页面。
_PUBLIC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://music.163.com/",
    "Cookie": "appver=2.0.2",
}
_PUBLIC_SEARCH = "https://music.163.com/api/search/get"
_PUBLIC_OUTER = "https://music.163.com/song/media/outer/url"
_PUBLIC_LYRIC = "https://music.163.com/api/song/lyric"
_PUBLIC_DETAIL = "https://music.163.com/api/song/detail"
# GD 音乐台：聚合第三方音源的纯 HTTP 接口，无需登录。它拿到的 netease 源是
# 完整音源（实测「夜空中最亮的星」30.8 MB / 1023 kbps），这是免费歌之外
# 唯一还能稳定取到会员曲目的通道。
_GD_BASE = "https://music-api.gdstudio.xyz/api.php"
_LEVELS = ("jymaster", "hires", "lossless", "exhigh", "higher", "standard")

# 本机解析服务的可用性探测结果缓存：每次搜索都探一次太慢，60 秒内复用。
_probe: dict[str, Any] = {"at": 0.0, "ok": False}
_PROBE_TTL = 60.0

# 播放地址缓存。网易云和 GD 返回的都是带时效的 CDN 直链，20 分钟内复用安全，
# 也避免同一首歌反复解析（GD 通道要 6-12 秒）。
_url_cache: dict[int, tuple[float, dict[str, Any]]] = {}
_URL_TTL = 20 * 60.0


def _cache_get(song_id: int) -> dict[str, Any] | None:
    entry = _url_cache.get(song_id)
    if not entry:
        return None
    stored_at, payload = entry
    if time.monotonic() - stored_at > _URL_TTL:
        _url_cache.pop(song_id, None)
        return None
    return payload


def _cache_put(song_id: int, payload: dict[str, Any]) -> None:
    if len(_url_cache) > 200:
        _url_cache.clear()
    _url_cache[song_id] = (time.monotonic(), payload)


def _settings(request: Request) -> Any:
    return request.app.state.container.settings


def _local_base(request: Request) -> str:
    return str(getattr(_settings(request), "music_api_base", "") or "").rstrip("/")


def _timeout(request: Request) -> float:
    return float(getattr(_settings(request), "music_request_timeout_seconds", 12.0))


async def _local_ready(request: Request) -> bool:
    """本机解析服务是否可用；没配地址就直接判定不可用。"""
    base = _local_base(request)
    if not base:
        return False
    now = time.monotonic()
    if now - float(_probe["at"]) < _PROBE_TTL:
        return bool(_probe["ok"])
    ok = False
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            response = await client.get(f"{base}/cloudsearch", params={"keywords": "test", "limit": 1})
            ok = response.status_code < 400
    except httpx.HTTPError:
        ok = False
    _probe.update({"at": now, "ok": ok})
    return ok


async def _local_get(request: Request, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """调本机解析服务；任何故障都返回 None，交给公开接口兜底。"""
    base = _local_base(request)
    if not base:
        return None
    try:
        async with httpx.AsyncClient(timeout=_timeout(request)) as client:
            response = await client.get(f"{base}{path}", params=params, headers={"User-Agent": "zhihui-qilu/1.0"})
    except httpx.HTTPError:
        return None
    if response.status_code >= 400:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


async def _public_get(url: str, params: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=_PUBLIC_HEADERS) as client:
        return await client.get(url, params=params)


def _cookie(request: Request) -> str:
    secret = getattr(_settings(request), "music_cookie", None)
    if secret is None:
        return ""
    value = secret.get_secret_value() if hasattr(secret, "get_secret_value") else str(secret)
    return value.strip()


async def _account_url(request: Request, song_id: int, level: str) -> dict[str, Any] | None:
    """带登录 cookie 取播放地址；会员曲目只有这条通道有真实 url。"""
    cookie = _cookie(request)
    if not cookie:
        return None
    headers = {**_PUBLIC_HEADERS, "Cookie": f"appver=2.0.2; {cookie}"}
    for candidate in _LEVELS[_LEVELS.index(level) :]:
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                response = await client.get(
                    "https://music.163.com/api/song/enhance/player/url/v1",
                    params={"ids": f"[{song_id}]", "level": candidate, "encodeType": "flac"},
                )
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None
        try:
            payload = response.json()
        except ValueError:
            return None
        rows = payload.get("data") or []
        row = rows[0] if rows and isinstance(rows[0], dict) else {}
        if row.get("url"):
            return {
                "id": song_id,
                "url": row["url"],
                "level": candidate,
                "br": row.get("br"),
                "size": row.get("size"),
                "fee": row.get("fee"),
                "channel": "account",
            }
    return None


def _artists(song: dict[str, Any]) -> str:
    """``/cloudsearch`` 用 ``ar``，公开 ``/search/get`` 用 ``artists``，两种都收。"""
    names = song.get("ar") or song.get("artists") or []
    return " / ".join(str(item.get("name", "")) for item in names if isinstance(item, dict)) or "未知歌手"


def _normalise(song: dict[str, Any]) -> dict[str, Any]:
    album = song.get("al") or song.get("album") or {}
    return {
        "id": song.get("id"),
        "name": song.get("name") or "未知曲目",
        "artists": _artists(song),
        "album": album.get("name") or "",
        "cover": album.get("picUrl") or "",
        "duration": song.get("dt") or song.get("duration") or 0,
        "fee": song.get("fee", 0),
    }


_PUNCT = re.compile(r"[\s\-—_·・'\"‘’“”!！?？.,，。&＆+\[\]()（）【】]")


def _norm(text: str) -> str:
    """归一化：去掉括号备注（Live/伴奏/翻唱）、标点与空白，转小写。"""
    lowered = str(text or "").lower()
    stripped = re.sub(r"[（(【\[].*?[)）】\]]", "", lowered)
    return _PUNCT.sub("", stripped) or _PUNCT.sub("", lowered)


def _artist_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item.get("name", "")) if isinstance(item, dict) else str(item) for item in value)
    return str(value or "")


def _name_matched(expected: str, candidate: str) -> bool:
    left, right = _norm(expected), _norm(candidate)
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _pick_candidate(rows: list[Any], name: str, artists: list[str]) -> dict[str, Any] | None:
    """在候选里挑同名同歌手的；宁可解析失败也不返回翻唱或同名异曲。"""
    best: dict[str, Any] | None = None
    best_score = 0
    for row in rows:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        if not _name_matched(name, str(row.get("name") or "")):
            continue
        candidate_artist = _norm(_artist_text(row.get("artist")))
        if not artists:
            score = 2
        elif not candidate_artist:
            score = 1
        else:
            hit = any(
                _norm(item) and (_norm(item) in candidate_artist or candidate_artist in _norm(item))
                for item in artists
            )
            if not hit:
                continue
            score = 3
        if score > best_score:
            best, best_score = row, score
    return best


async def _gd_url(
    request: Request,
    song_id: int,
    br: int = 320,
    name: str = "",
    artists: list[str] | None = None,
) -> dict[str, Any] | None:
    """走 GD 音乐台取完整音源。拿不到就返回 None，交给下一级降级。

    ``br`` 默认 320 kbps：最高档（999）会返回 30-70 MB 的无损文件，网页端加载
    要十几秒，现场演示不划算；320 已经远好于公开外链的 128。
    ``name``/``artists`` 由前端带上来时就不再查一次歌曲详情，省一跳。
    """
    timeout = float(_settings(request).music_request_timeout_seconds)
    payload: dict[str, Any] = {}
    picked: dict[str, Any] = {}
    url = ""
    song_name = name.strip()
    artist_list = [item.strip() for item in (artists or []) if item and item.strip()]
    try:
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": _PUBLIC_HEADERS["User-Agent"]}) as client:
            if not song_name:
                detail = await client.get(_PUBLIC_DETAIL, params={"ids": f"[{song_id}]"}, headers=_PUBLIC_HEADERS)
                songs = (detail.json().get("songs") or []) if detail.status_code < 400 else []
                row = songs[0] if songs and isinstance(songs[0], dict) else {}
                song_name = str(row.get("name") or "")
                artist_list = [str(item.get("name") or "") for item in (row.get("artists") or []) if isinstance(item, dict)]
            if not song_name:
                return None
            query = f"{song_name} {' '.join(artist_list)}".strip()
            search = await client.get(
                _GD_BASE,
                params={"types": "search", "source": "netease", "name": query, "count": 3, "pages": 1},
            )
            if search.status_code >= 400:
                return None
            rows = search.json()
            if not isinstance(rows, list):
                return None
            found = _pick_candidate(rows, song_name, artist_list)
            if not found:
                return None
            picked = found
            source = str(picked.get("source") or "netease")
            resolve = await client.get(
                _GD_BASE,
                params={"types": "url", "source": source, "id": picked.get("id"), "br": br},
            )
            if resolve.status_code >= 400:
                return None
            payload = resolve.json() or {}
            url = str(payload.get("url") or "")
            if not url.startswith("http"):
                return None
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None

    # 这里不再用 Range 探一次真伪：GD 回的都是网易云 CDN 直链，实测 6/6 可用，
    # 而多这一跳要 1-2 秒，直接拖慢点歌响应。真拿到坏链时播放器会立刻报错。
    kbps = int(payload.get("br") or 0)
    return {
        "id": song_id,
        "url": url,
        "level": "lossless" if kbps >= 900 else "exhigh",
        "br": kbps * 1000 if kbps else None,
        "size": payload.get("size"),
        "fee": 0,
        "channel": "gdmusic",
        "matched": f"{picked.get('name')} / {_artist_text(picked.get('artist'))}",
    }


@router.get("/status")
async def music_status(request: Request) -> dict[str, Any]:
    """报告通道可用性，供前端决定是否提示；永不抛错。"""
    local = await _local_ready(request)
    try:
        response = await _public_get(_PUBLIC_SEARCH, {"s": "test", "type": 1, "limit": 1})
        public = response.status_code < 400
    except httpx.HTTPError:
        public = False
    return {
        "available": local or public,
        "channel": "local" if local else ("public" if public else "none"),
        "localBase": _local_base(request),
        "localReady": local,
        "publicReady": public,
        "accountReady": bool(_cookie(request)),
    }


@router.get("/search")
async def music_search(
    request: Request,
    q: str = Query(min_length=1, max_length=60, description="歌名 / 歌手 / 专辑关键词"),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict[str, Any]:
    """按关键词搜单曲，返回前端可直接渲染的扁平结构。"""
    songs: list[dict[str, Any]] = []
    channel = "public"

    if await _local_ready(request):
        data = await _local_get(request, "/cloudsearch", {"keywords": q, "type": 1, "limit": limit, "offset": 0})
        rows = ((data or {}).get("result") or {}).get("songs") or []
        if rows:
            songs, channel = rows, "local"

    if not songs:
        try:
            response = await _public_get(_PUBLIC_SEARCH, {"s": q, "type": 1, "limit": limit, "offset": 0})
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="连不上网易云，请检查网络后重试。",
            ) from exc
        if response.status_code >= 400:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="网易云搜索暂时不可用。")
        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="网易云返回了非 JSON 内容。") from exc
        songs = ((data.get("result") or {}).get("songs")) or []

    items = [_normalise(song) for song in songs if isinstance(song, dict)]
    return {"query": q, "channel": channel, "count": len(items), "items": items}


@router.get("/url/{song_id}")
async def music_url(
    request: Request,
    song_id: int,
    level: str = Query(default="standard"),
    fee: int = Query(default=-1, description="搜索结果里的 fee；=1 表示会员专属，直接走聚合源省一次探测"),
    name: str = Query(default="", max_length=120, description="歌名，带上可省一次详情查询"),
    artists: str = Query(default="", max_length=160, description="歌手，多个用 / 分隔"),
) -> dict[str, Any]:
    """取播放地址，按可用性逐级降级。

    顺序：缓存 → 账号 cookie（配了才有）→ 会员曲目直连聚合源 → 公开外链 → 聚合源兜底。
    ``fee=1`` 时跳过公开外链那一跳：那一步对会员曲目必然失败，白等 1-2 秒。
    """
    wanted = level if level in _LEVELS else "standard"
    hints = [item for item in (part.strip() for part in artists.split("/")) if item]

    cached = _cache_get(song_id)
    if cached:
        return {**cached, "cached": True}

    account = await _account_url(request, song_id, wanted)
    if account:
        _cache_put(song_id, account)
        return account

    if fee == 1:
        vip = await _gd_url(request, song_id, name=name, artists=hints)
        if vip:
            _cache_put(song_id, vip)
            return vip

    if await _local_ready(request):
        for candidate in _LEVELS[_LEVELS.index(wanted) :]:
            data = await _local_get(request, "/song/url/v1", {"id": song_id, "level": candidate})
            rows = (data or {}).get("data") or []
            row = rows[0] if rows and isinstance(rows[0], dict) else {}
            if row.get("url"):
                payload = {
                    "id": song_id,
                    "url": row["url"],
                    "level": candidate,
                    "br": row.get("br"),
                    "size": row.get("size"),
                    "fee": row.get("fee"),
                    "channel": "local",
                }
                _cache_put(song_id, payload)
                return payload

    # 公开外链：可用曲目会 302 到 CDN 并返回 audio/*；受限曲目会跳 404 的 HTML 页。
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers={**_PUBLIC_HEADERS, "Range": "bytes=0-1023"}) as client:
            response = await client.get(_PUBLIC_OUTER, params={"id": f"{song_id}.mp3"})
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="连不上网易云，请检查网络后重试。",
        ) from exc

    content_type = response.headers.get("content-type", "")
    final_url = str(response.url)
    if response.status_code >= 400 or "audio" not in content_type.lower():
        # 公开外链只覆盖免费曲目，会员曲目在这里换第三方聚合源再试一次。
        fallback = await _gd_url(request, song_id, name=name, artists=hints)
        if fallback:
            _cache_put(song_id, fallback)
            return fallback
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="所有音源都没取到这首歌的播放地址。换一首，或在 .env 里填 ZHQ_MUSIC_COOKIE 用自己的会员身份。",
        )

    total = None
    content_range = response.headers.get("content-range") or ""
    if "/" in content_range:
        try:
            total = int(content_range.rsplit("/", 1)[1])
        except ValueError:
            total = None
    payload = {
        "id": song_id,
        "url": final_url,
        "level": "standard",
        "br": 128000,
        "size": total,
        "fee": 0,
        "channel": "public",
    }
    _cache_put(song_id, payload)
    return payload


@router.get("/lyric/{song_id}")
async def music_lyric(request: Request, song_id: int) -> dict[str, Any]:
    """取歌词。本机服务的 ``/lyric/new`` 带逐字时间轴，公开接口只有逐行。"""
    data: dict[str, Any] | None = None
    channel = "public"

    if await _local_ready(request):
        data = await _local_get(request, "/lyric/new", {"id": song_id})
        if data:
            channel = "local"
        else:
            data = await _local_get(request, "/lyric", {"id": song_id})

    if not data:
        try:
            response = await _public_get(_PUBLIC_LYRIC, {"id": song_id, "lv": 1, "tv": 1, "rv": 1})
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="连不上网易云，请检查网络后重试。",
            ) from exc
        if response.status_code >= 400:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="歌词服务暂时不可用。")
        try:
            data = response.json()
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="歌词服务返回了非 JSON 内容。") from exc

    def block(key: str) -> str:
        value = data.get(key)
        return str(value.get("lyric") or "") if isinstance(value, dict) else ""

    lrc = block("lrc")
    translation = block("tlyric")
    yrc = block("yrc")
    return {
        "id": song_id,
        "channel": channel,
        "lrc": lrc,
        "translation": translation,
        "yrc": yrc,
        "hasWordLevel": bool(yrc.strip()),
        "instrumental": not lrc.strip() and not yrc.strip(),
    }
