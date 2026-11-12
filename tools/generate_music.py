"""生成「声音角落」的内置环境音（原创合成，无第三方版权依赖）。

用法：python tools/generate_music.py

产物：web/public/music/{night-glow,rain-window,morning-woods}.mp3

设计要点
- 和弦走 I-V-vi-IV（D 大调），五声音阶挑点缀音，避免不协和。
- 混响用合成脉冲响应做卷积，而不是简单延时——这是「好听」的关键。
- 无缝循环：把超出长度的混响尾巴折回开头，首尾相接听不出接缝。
"""
from __future__ import annotations

import subprocess
import wave
import zlib
from pathlib import Path

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 44100
OUT = Path("web/public/music")
FFMPEG = r"D:\install\ffmpeg\ffmpeg-8.1.1-essentials_build\bin\ffmpeg.exe"

# 音名 → 频率（十二平均律，A4=440）
NOTE = {
    "D2": 73.42, "G2": 98.00, "A2": 110.00, "B2": 123.47,
    "D3": 146.83, "E3": 164.81, "F#3": 185.00, "G3": 196.00, "A3": 220.00, "B3": 246.94,
    "C#4": 277.18, "D4": 293.66, "F#4": 369.99, "A4": 440.00,
    "D5": 587.33, "E5": 659.26, "F#5": 739.99, "A5": 880.00, "B5": 987.77,
}

# I - V - vi - IV in D major
PROGRESSION = [
    ["D2", "A2", "D3", "F#3"],
    ["A2", "E3", "A3", "C#4"],
    ["B2", "F#3", "B3", "D4"],
    ["G2", "D3", "G3", "B3"],
]
PENTA = ["D5", "E5", "F#5", "A5", "B5"]


def lowpass(x: np.ndarray, cutoff: float, order: int = 4) -> np.ndarray:
    sos = butter(order, cutoff / (SR / 2), btype="low", output="sos")
    return sosfilt(sos, x, axis=0)


def bandpass(x: np.ndarray, lo: float, hi: float, order: int = 2) -> np.ndarray:
    sos = butter(order, [lo / (SR / 2), hi / (SR / 2)], btype="band", output="sos")
    return sosfilt(sos, x, axis=0)


def seed_of(*parts: object) -> int:
    """确定性种子：Python 的 hash() 每进程随机，会让产物不可复现。"""
    return zlib.crc32("|".join(map(str, parts)).encode("utf-8")) % (2**31)


def reverb_ir(seconds: float = 2.6, seed: int = 7) -> np.ndarray:
    """指数衰减噪声当作脉冲响应，低通后听感偏暖。"""
    rng = np.random.default_rng(seed)
    n = int(SR * seconds)
    decay = np.exp(-np.linspace(0, 6.5, n))
    ir = rng.standard_normal(n) * decay
    ir = lowpass(ir, 5200)
    ir[: int(SR * 0.012)] *= np.linspace(0, 1, int(SR * 0.012))  # 抹掉硬起头
    return ir / np.abs(ir).sum()


def convolve_wrap(x: np.ndarray, ir: np.ndarray) -> np.ndarray:
    """卷积后把溢出长度的尾巴折回开头，得到可无缝循环的结果。"""
    wet = fftconvolve(x, ir, mode="full")
    head, tail = wet[: x.size], wet[x.size :]
    out = head.copy()
    out[: tail.size] += tail[: out.size]
    return out


def pad_voice(freq: float, dur: float, detune: float, seed: int) -> np.ndarray:
    """一个缓慢起伏的和弦音：三支微失谐正弦 + 慢 LFO 调幅。"""
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    t = np.arange(n) / SR
    phase = rng.uniform(0, 2 * np.pi)
    voice = np.zeros(n)
    for k, mult in enumerate((1.0, 1.0 + detune, 1.0 - detune * 0.7)):
        voice += np.sin(2 * np.pi * freq * mult * t + phase + k)
    voice /= 3
    lfo_rate = rng.uniform(0.03, 0.09)
    lfo = 0.62 + 0.38 * np.sin(2 * np.pi * lfo_rate * t + rng.uniform(0, 6.28))
    return voice * lfo


def bell(freq: float, dur: float, seed: int) -> np.ndarray:
    """FM 钟声：调制指数随时间衰减，尾音自然。"""
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    t = np.arange(n) / SR
    index = 2.6 * np.exp(-t * 3.2)
    mod = np.sin(2 * np.pi * freq * 2.0 * t) * index
    body = np.sin(2 * np.pi * freq * t + mod)
    env = np.exp(-t * 2.4) * (1 - np.exp(-t * 220))
    return body * env * rng.uniform(0.7, 1.0)


def rain(dur: float, seed: int) -> np.ndarray:
    """雨声：带通噪声 + 极慢的强弱起伏。"""
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    body = bandpass(noise, 700, 9000) * 0.55 + lowpass(noise, 500) * 0.45
    swell = 0.55 + 0.45 * np.sin(2 * np.pi * 0.055 * t + 1.1)
    return body * swell


def birds(dur: float, seed: int) -> np.ndarray:
    """林间鸟鸣：短促上滑的正弦啁啾。"""
    rng = np.random.default_rng(seed)
    n = int(SR * dur)
    out = np.zeros(n)
    pos = 2.0
    while pos < dur - 1.0:
        length = rng.uniform(0.09, 0.2)
        cnt = int(SR * length)
        if cnt < 8:
            break
        tt = np.arange(cnt) / SR
        f0 = rng.uniform(2100, 3400)
        sweep = f0 * (1 + rng.uniform(0.15, 0.5) * tt / length)
        chirp = np.sin(2 * np.pi * sweep * tt) * np.exp(-tt * 14)
        start = int(SR * pos)
        end = min(n, start + cnt)
        out[start:end] += chirp[: end - start] * rng.uniform(0.25, 0.5)
        pos += rng.uniform(1.1, 3.4)
    return bandpass(out, 1500, 6000)


def build(kind: str, dur: float = 96.0) -> np.ndarray:
    n = int(SR * dur)
    rng = np.random.default_rng(seed_of(kind))
    pad = np.zeros(n)
    bar = dur / len(PROGRESSION) / 2  # 每个和弦两小节

    # 和弦铺底：交叉淡化，避免换和弦时有咔哒声
    for i, chord in enumerate(PROGRESSION):
        start = i * bar * 2
        length = bar * 2 + 2.0
        for j, name in enumerate(chord):
            v = pad_voice(NOTE[name], length, detune=0.0016, seed=seed_of(kind, i, j))
            s = int(SR * start)
            e = min(n, s + v.size)
            seg = v[: e - s]
            fade = int(SR * 1.4)
            if seg.size > fade * 2:
                seg = seg.copy()
                seg[:fade] *= np.linspace(0, 1, fade)
                seg[-fade:] *= np.linspace(1, 0, fade)
            pad[s:e] += seg

    mix = pad * 0.5

    # 点缀音
    if kind != "morning-woods":
        pos = 3.0
        while pos < dur - 3.0:
            name = PENTA[rng.integers(len(PENTA))]
            b = bell(NOTE[name], 4.5, seed=seed_of(kind, pos))
            s = int(SR * pos)
            e = min(n, s + b.size)
            mix[s:e] += b[: e - s] * 0.26
            pos += rng.uniform(2.2, 5.0)

    if kind == "rain-window":
        mix += rain(dur, seed=seed_of(kind)) * 0.11
    if kind == "morning-woods":
        mix += birds(dur, seed=seed_of(kind)) * 0.10

    # 混响（湿声）+ 干声
    ir = reverb_ir(2.6 if kind != "morning-woods" else 2.1)
    wet = convolve_wrap(mix, ir)
    out = mix * 0.55 + wet * 2.6

    # 轻微立体声展开：左右各偏一点
    left = out
    right = np.roll(out, int(SR * 0.011)) * 0.94
    stereo = np.stack([left, right], axis=1)

    stereo = lowpass(stereo, 12000)
    stereo /= np.max(np.abs(stereo)) + 1e-9
    stereo = np.tanh(stereo * 1.15) * 0.86  # 软限幅
    return stereo


TRACKS = {
    "night-glow": "夜色微光",
    "rain-window": "雨落窗台",
    "morning-woods": "清晨林间",
}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for slug, title in TRACKS.items():
        audio = build(slug)
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
        wav_path = OUT / f"{slug}.wav"
        with wave.open(str(wav_path), "wb") as handle:
            handle.setnchannels(2)
            handle.setsampwidth(2)
            handle.setframerate(SR)
            handle.writeframes(pcm.tobytes())
        mp3_path = OUT / f"{slug}.mp3"
        subprocess.run(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav_path),
             "-codec:a", "libmp3lame", "-b:a", "96k", "-ar", str(SR), str(mp3_path)],
            check=True,
        )
        wav_path.unlink()
        print(f"{title:8s} -> {mp3_path}  {mp3_path.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
