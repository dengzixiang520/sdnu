"""用真实 Chrome 跑一遍沉浸式面试，重点盯"导师语音加载失败"有没有误报。

思路：
  1. 先向后端要一段 TTS，转成 16k 单声道 WAV，喂给 Chrome 的假麦克风；
  2. 用 Playwright 起 Chrome，允许媒体权限、免手势自动播放；
  3. 进 /#/academic/interview，点"进入教室，开始面试"；
  4. 每 200ms 采样一次页面状态，记录 toast 文本、问题文本、等待态、字幕；
  5. 只要 toast 出现过"失败"，就判定这次修复没到位。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
APP = "http://localhost:5173/#/academic/interview"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
FFMPEG = r"D:\install\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe"

SENTENCE = (
    "同学你好，请先做一个两分钟的自我介绍。"
    "我叫邓子祥，是山东师范大学人工智能专业的学生，做过一个叫智慧启录的校园助手项目。"
    "这个项目用到了大模型和语音识别，我主要负责后端接口和语音链路的设计。"
)


def make_fake_mic(tmp: Path) -> Path:
    """把一段 TTS 转成 Chrome 假麦克风能吃的 WAV。"""
    with httpx.Client(base_url=BASE, timeout=180.0) as client:
        ticket = client.post("/api/v1/interview/tts", json={"text": SENTENCE, "examiner": "host"}).json()
        mp3 = client.get(ticket["url"])
        mp3.raise_for_status()
    src = tmp / "seed.mp3"
    dst = tmp / "fake-mic.wav"
    src.write_bytes(mp3.content)
    subprocess.run(
        [FFMPEG, "-y", "-loglevel", "error", "-i", str(src),
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)],
        check=True,
    )
    return dst


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="iv-ui-"))
    wav = make_fake_mic(tmp)
    print(f"[seed] 假麦克风音频 {wav.stat().st_size} 字节")

    failures: list[str] = []
    samples: list[dict[str, object]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=CHROME,
            headless=False,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-audio-capture={wav}",
                "--autoplay-policy=no-user-gesture-required",
                "--window-size=1440,900",
                "--lang=zh-CN",
            ],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        console_errors: list[str] = []
        page.on(
            "console",
            lambda m: console_errors.append(m.text) if m.type == "error" else None,
        )
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))
        page.goto(APP, wait_until="domcontentloaded")
        page.wait_for_selector(".iv-lobby-card", timeout=30000)
        print("[ui] 大厅已加载")

        # 关掉全屏请求，免得无头环境卡住
        page.evaluate(
            "() => { Element.prototype.requestFullscreen = () => Promise.resolve(); }"
        )

        page.fill(".iv-field input", "人工智能")
        page.click("button[type=submit].iv-primary")
        print("[ui] 已点击进入教室")

        deadline = time.time() + 70
        last_note = ""
        started = time.time()
        while time.time() < deadline:
            snapshot = page.evaluate(
                """() => {
                    const pick = (sel) => document.querySelector(sel)?.textContent?.trim() ?? '';
                    const said = pick('.iv-transcript p');
                    return {
                        toast: pick('.iv-toast'),
                        question: pick('.iv-question'),
                        loading: Boolean(document.querySelector('.iv-speech-loading')),
                        speaking: Boolean(document.querySelector('.iv-wave.active')),
                        transcript: said.startsWith('开口说话') ? '' : said,
                        stageLive: Boolean(document.querySelector('.iv-subtitle')),
                        recording: Boolean(document.querySelector('.iv-primary.danger')),
                    };
                }"""
            )
            samples.append({"t": round(time.time() - started, 1), **snapshot})
            if snapshot["toast"] and snapshot["toast"] != last_note:
                print(f"  [toast {samples[-1]['t']:>5.1f}s] {snapshot['toast']}")
                last_note = snapshot["toast"]
                if "失败" in snapshot["toast"]:
                    failures.append(f"{samples[-1]['t']}s: {snapshot['toast']}")
            if snapshot["question"] and snapshot["question"] != "正在请考官提问…":
                # 问题已经出现，再给语音和转写一点时间
                if len(snapshot["transcript"]) > 8 and not snapshot["loading"]:
                    break
            time.sleep(0.2)

        # 收尾：等字幕出来
        try:
            page.wait_for_function(
                """() => {
                    const t = document.querySelector('.iv-transcript p')?.textContent ?? '';
                    return t.length > 8 && !t.startsWith('开口说话');
                }""",
                timeout=30000,
            )
        except Exception:
            pass

        final = page.evaluate(
            """() => ({
                transcript: document.querySelector('.iv-transcript p')?.textContent?.trim() ?? '',
                question: document.querySelector('.iv-question')?.textContent?.trim() ?? '',
                toast: document.querySelector('.iv-toast')?.textContent?.trim() ?? '',
                audio: performance.getEntriesByType('resource')
                    .filter((e) => e.name.includes('/interview/tts/'))
                    .map((e) => ({ name: e.name.split('/').pop(), ms: Math.round(e.duration) })),
            })"""
        )
        page.screenshot(path=str(Path("data") / "interview-ui-check.png"), full_page=False)
        browser.close()

    print("\n[最终]")
    print(f"  问题 : {final['question'][:80]}")
    print(f"  字幕 : {final['transcript'][:120] or '（空）'}")
    print(f"  toast: {final['toast'] or '（无）'}")
    for item in final.get("audio") or []:
        print(f"  音频 : {item['name']} 用时 {item['ms']} ms")
    if console_errors:
        print("  控制台错误:")
        for line in console_errors[:8]:
            print(f"    - {line[:180]}")

    loading_seen = sum(1 for s in samples if s["loading"])
    speaking_seen = sum(1 for s in samples if s["speaking"])
    print(f"\n[统计] 采样 {len(samples)} 次，等待态出现 {loading_seen} 次，播放态出现 {speaking_seen} 次")

    ok = True
    if failures:
        print("\n!! 出现误报的失败提示：")
        for item in failures:
            print(f"   - {item}")
        ok = False
    else:
        print("\n[OK] 全程没有出现“导师语音加载失败”的误报")

    if not final["transcript"]:
        print("!! 字幕仍然是空的，语音转写没走通")
        ok = False
    if loading_seen == 0:
        slow = [i for i in (final.get("audio") or []) if i["ms"] > 400]
        if slow:
            print(f"!! 音频取了 {slow[0]['ms']}ms 却没显示过等待态")
            ok = False
        else:
            print("[说明] 音频命中缓存、秒回，所以没有等待态——这是期望行为")

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
