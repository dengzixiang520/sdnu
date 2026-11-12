"""端到端校验面试语音链路：TTS 出音 -> 转成 16k 单声道 WAV -> 送 /asr 转写。

这不是单元测试，是给演示前自检用的。跑通说明"导师能说话 + 考生能被转写"两段都活着。
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
FFMPEG = r"D:\install\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe"

SENTENCE = "同学你好，请先做一个两分钟的自我介绍，重点说说你做过的项目。"


def main() -> int:
    ok = True
    with httpx.Client(base_url=BASE, timeout=180.0) as client:
        # 1) 面板：三位考官 + 语音 + 转写能力都在
        panel = client.get("/api/v1/interview/panel")
        print(f"[panel] HTTP {panel.status_code}")
        if panel.status_code != 200:
            print(panel.text[:400])
            return 1
        data = panel.json()
        print(f"[panel] examiners={len(data.get('examiners', []))}")
        for item in data.get("examiners", []):
            print(f"         - {item.get('name')} / {item.get('role')} / voice={item.get('voice_id')}")
        print(f"[panel] speech={json.dumps(data.get('speech'), ensure_ascii=False)}")
        print(f"[panel] asr={json.dumps(data.get('asr'), ensure_ascii=False)}")
        if not (data.get("asr") or {}).get("ready"):
            print("[panel] !! 服务端转写未就绪，后面必然失败")
            ok = False

        # 2) TTS：拿到 mp3
        tts = client.post(
            "/api/v1/interview/tts",
            json={"text": SENTENCE, "examiner": "host"},
        )
        print(f"[tts] HTTP {tts.status_code}")
        if tts.status_code != 200:
            print(tts.text[:400])
            return 1
        ticket = tts.json()
        token = ticket.get("token")
        print(f"[tts] token={token} url={ticket.get('url')}")
        audio = client.get(f"/api/v1/interview/tts/{token}.mp3")
        print(f"[tts] mp3 HTTP {audio.status_code} bytes={len(audio.content)}")
        if audio.status_code != 200 or len(audio.content) < 2000:
            ok = False

        # 3) mp3 -> 16k mono wav（和浏览器采集侧一致的格式）
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "tts.mp3"
            dst = Path(tmp) / "tts.wav"
            src.write_bytes(audio.content)
            proc = subprocess.run(
                [FFMPEG, "-y", "-loglevel", "error", "-i", str(src),
                 "-ac", "1", "-ar", "16000", "-f", "wav", str(dst)],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                print(f"[ffmpeg] 失败: {proc.stderr[:400]}")
                return 1
            wav = dst.read_bytes()
            print(f"[wav] bytes={len(wav)} 时长约 {len(wav) / 32000:.1f}s")

        # 4) 送 /asr
        started = time.perf_counter()
        asr = client.post(
            "/api/v1/interview/asr",
            json={"audio": base64.b64encode(wav).decode("ascii"), "format": "wav"},
        )
        wall = (time.perf_counter() - started) * 1000
        print(f"[asr] HTTP {asr.status_code} wall={wall:.0f}ms")
        if asr.status_code != 200:
            print(asr.text[:600])
            return 1
        result = asr.json()
        print(f"[asr] elapsed_ms={result.get('elapsed_ms')} model={result.get('model')}")
        print(f"[asr] text={result.get('text')}")
        hit = _similarity(SENTENCE, result.get("text") or "")
        print(f"[asr] 与原句相似度 {hit:.2f}")
        if hit < 0.6:
            print("[asr] !! 转写结果和原句差太多")
            ok = False

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def _similarity(a: str, b: str) -> float:
    """粗粒度的字符级重合率，够判断"是不是同一句话"就行。"""
    keep = lambda s: [c for c in s if c.strip() and c not in "，。、！？；：""''（）()《》…—"]
    left, right = keep(a), keep(b)
    if not left or not right:
        return 0.0
    pool = list(right)
    hit = 0
    for ch in left:
        if ch in pool:
            pool.remove(ch)
            hit += 1
    return hit / len(left)


if __name__ == "__main__":
    sys.exit(main())
