#!/usr/bin/env python3
"""
按歌曲调性合成所有乐器音效 → public/sfx/*.wav
用法: python tools/synth_sfx.py src/beats.json public/sfx
每种乐器生成 1~10 级音（大调/小调音阶），打击乐/环境音只生成一个
"""
import json, os, sys, wave
import numpy as np

SR = 44100
rng = np.random.default_rng(7)

MAJOR = [0, 2, 4, 5, 7, 9, 11]
MINOR = [0, 2, 3, 5, 7, 8, 10]


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tvec(sec):
    return np.arange(int(SR * sec)) / SR


def env_ad(t, a=0.003, d=1.0):
    e = np.exp(-t / d)
    if a > 0:
        e *= np.clip(t / a, 0, 1)
    return e


def reverb(x, sec=1.6, mix=0.22, damp=3.5):
    n = int(SR * sec)
    t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-t * damp)
    # 简单低通，让混响更暖
    ir = np.convolve(ir, np.ones(6) / 6, mode="same")
    ir /= np.sqrt((ir ** 2).sum())
    from scipy.signal import fftconvolve
    wet = np.concatenate([fftconvolve(x, ir), [0.0]])[: len(x) + n]
    dry = np.concatenate([x, np.zeros(n)])
    return dry * (1 - mix) + wet * mix * 3


def finish(x, peak=0.8, rev=True, **kw):
    if rev:
        x = reverb(x, **kw)
    # 去掉尾部静音
    thr = np.abs(x).max() * 4e-3
    idx = np.where(np.abs(x) > thr)[0]
    x = x[: idx[-1] + 1] if len(idx) else x
    fade = min(len(x), int(SR * 0.05))
    x[-fade:] *= np.linspace(1, 0, fade)
    return x / (np.abs(x).max() + 1e-9) * peak


# ---------- 乐器 ----------
def additive(f, partials, dur, attack=0.002):
    """partials: [(比例, 振幅, 衰减秒)]"""
    t = tvec(dur)
    x = np.zeros_like(t)
    for r, a, d in partials:
        if f * r < SR / 2.2:
            x += a * np.sin(2 * np.pi * f * r * t + rng.uniform(0, 6)) * env_ad(t, attack, d)
    return x


def karplus(f, dur, damp=0.996, bright=0.5, pick=0.5, body=None):
    n = int(SR * dur)
    p = int(SR / f)
    buf = rng.uniform(-1, 1, p)
    # 拨弦位置梳状滤波 + 亮度
    k = max(1, int(p * pick * 0.3))
    buf = buf - np.roll(buf, k) * 0.5
    buf = bright * buf + (1 - bright) * np.convolve(buf, np.ones(3) / 3, mode="same")
    out = np.zeros(n)
    frac_f = SR / f
    for i in range(n):
        j = i % p
        out[i] = buf[j]
        buf[j] = damp * 0.5 * (buf[j] + buf[(j + 1) % p])
    # 整数延迟会让音偏高，按真实周期重采样修正音高
    ratio = (SR / f) / (p + 0.5)  # 平均滤波器额外带来半个采样的延迟
    src = np.arange(n) / ratio
    out = np.interp(np.arange(n), src, out) if ratio != 1 else out
    if body:
        out = out + body * np.convolve(out, np.exp(-np.arange(200) / 30) * np.sin(np.arange(200) * 0.3), mode="same") * 0.02
    return out


def inst(name, f):
    t3 = tvec(3)
    if name == "marimba":
        x = additive(f, [(1, 1, 0.45), (3.93, 0.35, 0.08), (9.2, 0.12, 0.03)], 2.0)
        return finish(x, rev=True, mix=0.15)
    if name == "kalimba":
        x = additive(f, [(1, 1, 0.7), (5.4, 0.25, 0.05), (8.9, 0.15, 0.03), (2, 0.1, 0.3)], 2.0)
        return finish(x, mix=0.25)
    if name == "glock":
        x = additive(f, [(1, 1, 1.2), (2.76, 0.45, 0.35), (5.4, 0.25, 0.12), (8.93, 0.1, 0.06)], 2.5)
        return finish(x, mix=0.25)
    if name == "celesta":
        x = additive(f, [(1, 1, 0.9), (2, 0.35, 0.4), (3, 0.12, 0.2), (4.2, 0.08, 0.08)], 2.2, attack=0.004)
        return finish(x, mix=0.3)
    if name == "bell":  # 管钟 / Risset 钟
        ratios = [(1, 1, 3.0), (2.0, 0.6, 2.0), (3.0, 0.4, 1.4), (4.16, 0.3, 1.0), (5.43, 0.2, 0.7), (6.79, 0.1, 0.5)]
        x = additive(f, ratios, 4.0)
        x += rng.standard_normal(len(x)) * env_ad(tvec(4.0), 0, 0.003) * 0.2
        return finish(x, mix=0.3, sec=2.5)
    if name == "vibes":
        t = tvec(3)
        x = additive(f, [(1, 1, 1.5), (4, 0.25, 0.3), (10, 0.06, 0.08)], 3)
        x *= 1 - 0.35 * (0.5 + 0.5 * np.sin(2 * np.pi * 5.5 * t))  # 颤音电机
        return finish(x, mix=0.3)
    if name == "glass":
        t = tvec(3.5)
        x = additive(f, [(1, 1, 2.0), (2.32, 0.3, 1.0), (4.25, 0.15, 0.5), (1.003, 0.6, 2.0)], 3.5, attack=0.03)
        return finish(x, mix=0.4, sec=2.5)
    if name == "piano":
        B = 0.0004
        parts = []
        for n in range(1, 12):
            r = n * np.sqrt(1 + B * n * n)
            parts.append((r, 1 / n ** 1.1, 1.8 / (1 + 0.35 * n)))
        x = additive(f, parts, 3.0, attack=0.002)
        t = tvec(3.0)
        x += rng.standard_normal(len(t)) * np.exp(-t * 120) * 0.08  # 琴槌
        return finish(x, mix=0.25)
    if name == "lyre":
        x = karplus(f, 2.5, damp=0.998, bright=0.6, pick=0.4)
        return finish(x, mix=0.3)
    if name == "zheng":
        t = tvec(2.5)
        x = karplus(f, 2.5, damp=0.997, bright=0.85, pick=0.2)
        # 古筝的按弦微微滑音：用轻微变速实现
        warp = t + 0.0025 * np.sin(2 * np.pi * 5 * t) * np.clip(t - 0.25, 0, None)
        x = np.interp(warp * SR, np.arange(len(x)), x)
        return finish(x, mix=0.3)
    if name == "oud":
        x = karplus(f, 2.0, damp=0.993, bright=0.35, pick=0.6)
        x += 0.4 * karplus(f * 1.002, 2.0, damp=0.993, bright=0.35, pick=0.55)  # 双弦
        return finish(x, mix=0.25)
    if name == "sitar":
        x = karplus(f, 2.5, damp=0.997, bright=0.9, pick=0.15)
        x = np.tanh(3 * x) * 0.6 + x * 0.4  # 琴码的“嗡嗡”声
        t = tvec(2.5)
        x += 0.15 * np.sin(2 * np.pi * f * 4 * t) * np.exp(-t * 2) * np.sin(2 * np.pi * 7 * t)
        return finish(x, mix=0.3)
    if name == "pizz":
        x = karplus(f, 1.2, damp=0.985, bright=0.4, pick=0.5)
        x += 0.5 * karplus(f * 2, 1.2, damp=0.98, bright=0.3)
        return finish(x, mix=0.3)
    if name == "blip":
        t = tvec(0.35)
        ph = np.cumsum(f * (1 + 0.5 * np.exp(-t * 60))) / SR
        sq = np.sign(np.sin(2 * np.pi * ph))
        x = sq * env_ad(t, 0.001, 0.08) * 0.6 + np.sin(2 * np.pi * f * 2 * t) * env_ad(t, 0.001, 0.05) * 0.3
        x = np.convolve(x, np.ones(4) / 4, mode="same")
        return finish(x, mix=0.15, sec=0.8)
    raise ValueError(name)


def drums(name, tonic_pc):
    if name == "woodblock":
        t = tvec(0.4)
        x = np.sin(2 * np.pi * 880 * t) * env_ad(t, 0.0005, 0.03) + np.sin(2 * np.pi * 1320 * t) * env_ad(t, 0.0005, 0.02) * 0.5
        x += rng.standard_normal(len(t)) * env_ad(t, 0, 0.004) * 0.3
        return finish(x, mix=0.2, sec=0.8)
    if name == "taiko":  # 陶鼓：低沉、有泥土感
        t = tvec(1.5)
        f = 65 + 60 * np.exp(-t * 25)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * env_ad(t, 0.001, 0.35)
        n = rng.standard_normal(len(t))
        n = np.convolve(n, np.ones(30) / 30, mode="same")
        x += n * env_ad(t, 0.001, 0.05) * 2
        return finish(x, mix=0.25)
    if name == "gong":
        t = tvec(5)
        f0 = mtof(36 + tonic_pc)
        x = np.zeros_like(t)
        for r, a in [(1, 1), (1.47, 0.6), (2.09, 0.5), (2.56, 0.4), (3.23, 0.3), (4.1, 0.2), (5.3, 0.15)]:
            x += a * np.sin(2 * np.pi * f0 * r * t * (1 + 0.004 * np.exp(-t))) * env_ad(t, 0.02 * r, 2.5 / r ** 0.5)
        return finish(x, mix=0.35, sec=3)
    if name == "bowl":  # 颂钵：两个很近的频率形成"拍"
        t = tvec(6)
        f0 = mtof(60 + tonic_pc)
        x = (np.sin(2 * np.pi * f0 * t) + np.sin(2 * np.pi * f0 * 1.004 * t)) * env_ad(t, 0.01, 3)
        x += 0.5 * (np.sin(2 * np.pi * f0 * 2.71 * t) + np.sin(2 * np.pi * f0 * 2.716 * t)) * env_ad(t, 0.01, 1.5)
        x += 0.2 * np.sin(2 * np.pi * f0 * 5.1 * t) * env_ad(t, 0.005, 0.5)
        return finish(x, mix=0.35, sec=3)
    if name == "timpani":
        t = tvec(2.5)
        f0 = mtof(41 + tonic_pc) if tonic_pc < 7 else mtof(29 + tonic_pc)
        x = np.zeros_like(t)
        for r, a, d in [(1, 1, 0.9), (1.5, 0.6, 0.6), (1.98, 0.4, 0.45), (2.44, 0.25, 0.3)]:
            x += a * np.sin(2 * np.pi * f0 * r * t) * env_ad(t, 0.002, d)
        n = np.convolve(rng.standard_normal(len(t)), np.ones(12) / 12, mode="same")
        x += n * env_ad(t, 0.001, 0.03) * 1.5
        return finish(x, mix=0.3, sec=2)
    if name == "boom":  # 副歌转场的低频冲击
        t = tvec(2.0)
        f = 40 + 70 * np.exp(-t * 18)
        x = np.sin(2 * np.pi * np.cumsum(f) / SR) * env_ad(t, 0.001, 0.6)
        return finish(x, rev=False)
    if name == "swish":  # 转场前的风声（向上扫）
        t = tvec(0.45)
        n = rng.standard_normal(len(t))
        out = np.zeros_like(n)
        # 移动的一阶带通（通过改变平滑窗口）
        for i, w in enumerate(np.linspace(40, 3, 9)):
            seg = slice(i * len(t) // 9, (i + 1) * len(t) // 9)
            out[seg] = np.convolve(n, np.ones(int(w)) / int(w), mode="same")[seg] - np.convolve(n, np.ones(int(w) * 4) / (int(w) * 4), mode="same")[seg]
        x = out * np.sin(np.pi * t / t[-1]) ** 2 * (t / t[-1])
        return finish(x, mix=0.2, sec=0.8)
    if name == "swell":  # 弦乐渐强（主和弦）
        t = tvec(2.6)
        x = np.zeros_like(t)
        for m in [53, 57, 60, 65, 69]:
            f = mtof(m - 5 + tonic_pc) * (1 + 0.003 * np.sin(2 * np.pi * 5 * t + m))
            ph = np.cumsum(f) / SR
            saw = 2 * (ph % 1) - 1
            x += saw
        x = np.convolve(x, np.ones(8) / 8, mode="same")
        e = np.clip(t / 2.0, 0, 1) ** 2 * np.exp(-np.clip(t - 2.0, 0, None) * 6)
        return finish(x * e, mix=0.35, sec=2)
    raise ValueError(name)


MELODIC = {
    # 乐器: 主音的 MIDI 八度（相对 C）
    "marimba": 60, "kalimba": 60, "glock": 72, "celesta": 72, "bell": 72, "vibes": 60,
    "glass": 72, "piano": 60, "lyre": 60, "zheng": 60, "oud": 48, "sitar": 48, "pizz": 48, "blip": 72,
}
PERC = ["woodblock", "taiko", "gong", "bowl", "timpani", "boom", "swish", "swell"]


def write_wav(path, x):
    x = np.clip(x, -1, 1)
    st = x
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((st * 32767).astype("<i2").tobytes())


def main(beats_json, outdir):
    key = json.load(open(beats_json))["key"]
    pc = key["tonicPc"]
    scale = MAJOR if key["mode"] == "major" else MINOR
    os.makedirs(outdir, exist_ok=True)
    # 主音放在 C..B 之间的那个八度；F 以上往下移一个八度，避免太尖
    base_shift = pc if pc <= 6 else pc - 12
    for name, oct_c in MELODIC.items():
        for deg in range(1, 11):
            d = deg - 1
            midi = oct_c + base_shift + 12 * (d // 7) + scale[d % 7]
            write_wav(os.path.join(outdir, f"{name}_{deg}.wav"), inst(name, mtof(midi)))
    for name in PERC:
        write_wav(os.path.join(outdir, f"{name}.wav"), drums(name, pc))
    # 有 ffmpeg 就转成无损 FLAC（体积约为 WAV 的一半，不会像 MP3 那样引入起音延迟）
    # 本机没有 ffmpeg：直接保留 WAV，Remotion 一样能读（src/Main.tsx 里 SFX_EXT='wav'）
    import glob, shutil, subprocess
    if shutil.which("ffmpeg"):
        for w in glob.glob(os.path.join(outdir, "*.wav")):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", w, "-compression_level", "8", w[:-4] + ".flac"], check=True)
            os.remove(w)
    else:
        print("（未检测到 ffmpeg：保留 WAV 输出）")
    print(f"调性 {key['tonic']} {key['mode']}：生成 {len(MELODIC) * 10 + len(PERC)} 个音效 → {outdir}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "src/beats.json", sys.argv[2] if len(sys.argv) > 2 else "public/sfx")
