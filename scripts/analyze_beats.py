#!/usr/bin/env python3
"""
节拍分析：BPM、每一拍、重拍(小节第一拍)、段落、调性
用法: node tools/decode_mp3.mjs && python tools/analyze_beats.py public/music.f32 src/beats.json

改动：本机没有 ffmpeg / scipy，所以
  1) 音频从 decode_mp3.mjs 产出的单声道 float32 裸数据 + sidecar(json) 读取；
  2) 用 numpy 自己实现了 find_peaks，不再依赖 scipy。
只依赖 numpy。
"""
import json, os, subprocess, sys
import numpy as np

SR = 22050
HOP = 256          # ~11.6ms
NFFT = 2048
LATENCY = 0.03     # 实测补偿：起音检测比真实击打早约 30ms


def load(path):
    """优先读 decode_mp3.mjs 产出的 .f32 裸数据（同名 .json 里有采样率）；否则退回 ffmpeg。"""
    global SR
    for c in (path + '.f32', os.path.splitext(path)[0] + '.f32', path):
        meta = c + '.json'
        if c.endswith('.f32') and os.path.exists(c) and os.path.exists(meta):
            with open(meta) as f:
                SR = int(json.load(f)['sampleRate'])
            return np.fromfile(c, dtype='<f4').astype(np.float32)
    raw = subprocess.run(
        ["ffmpeg", "-v", "quiet", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def find_peaks(x, distance=4, height=None):
    """numpy 版 find_peaks：比左右邻居大的点，按 distance 取局部最高"""
    n = len(x)
    if n == 0:
        return np.array([], dtype=int)
    thr = -np.inf if height is None else float(height)
    cand = [i for i in range(1, n - 1) if x[i] > x[i - 1] and x[i] >= x[i + 1] and x[i] >= thr]
    if x[0] >= thr:
        cand.insert(0, 0)
    picked = []
    for i in cand:
        if picked and i - picked[-1] < distance:
            if x[i] > x[picked[-1]]:
                picked[-1] = i
        else:
            picked.append(i)
    return np.array(picked, dtype=int)


def stft_mag(y):
    win = np.hanning(NFFT).astype(np.float32)
    n = 1 + (len(y) - NFFT) // HOP
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n)[:, None]
    frames = y[idx] * win
    return np.abs(np.fft.rfft(frames, axis=1)).T  # (freq, time)


def mel_fb(n_mels=64):
    fmax = SR / 2
    def hz2mel(f): return 2595 * np.log10(1 + f / 700)
    def mel2hz(m): return 700 * (10 ** (m / 2595) - 1)
    mels = np.linspace(hz2mel(30), hz2mel(fmax), n_mels + 2)
    hz = mel2hz(mels)
    bins = np.fft.rfftfreq(NFFT, 1 / SR)
    fb = np.zeros((n_mels, len(bins)))
    for i in range(n_mels):
        l, c, r = hz[i], hz[i + 1], hz[i + 2]
        fb[i] = np.clip(np.minimum((bins - l) / (c - l), (r - bins) / (r - c)), 0, None)
    return fb, bins


def onset_envelope(S):
    fb, bins = mel_fb()
    M = np.log1p(100 * fb @ S)
    flux = np.maximum(0, np.diff(M, axis=1, prepend=M[:, :1]))
    env = flux.mean(axis=0)
    # 低频(底鼓/贝斯)单独一条，用来判断重拍
    low = np.log1p(100 * S[(bins > 30) & (bins < 180)].sum(axis=0))
    low_flux = np.maximum(0, np.diff(low, prepend=low[:1]))
    def norm(x):
        x = x - np.convolve(x, np.ones(16) / 16, mode="same")
        x = np.maximum(0, x)
        return x / (x.std() + 1e-9)
    return norm(env), norm(low_flux), M


def estimate_tempo(env, fps):
    ac = np.correlate(env, env, mode="full")[len(env) - 1:]
    ac /= ac[0] + 1e-9
    bpms = np.arange(60, 181, 0.25)
    lags = 60 * fps / bpms
    score = np.interp(lags, np.arange(len(ac)), ac)
    # 加上二倍/一半节拍的支持，并偏好 ~100 BPM 附近
    score2 = score + 0.5 * np.interp(lags * 2, np.arange(len(ac)), ac)
    prior = np.exp(-0.5 * (np.log2(bpms / 100) / 0.9) ** 2)
    total = score2 * prior
    return float(bpms[np.argmax(total)])


def track_beats(env, fps, bpm, tightness=100):
    """Ellis 2007 动态规划节拍跟踪"""
    period = 60 * fps / bpm
    n = len(env)
    score = env.copy()
    back = -np.ones(n, dtype=int)
    lo, hi = int(round(period / 2)), int(round(period * 2))
    prev = np.arange(-hi, -lo + 1)
    pen = -tightness * (np.log(-prev / period)) ** 2
    for t in range(hi, n):
        cand = score[t + prev] + pen
        k = np.argmax(cand)
        score[t] = env[t] + cand[k]
        back[t] = t + prev[k]
    # 从末尾附近最高分回溯
    tail = int(period)
    t = n - tail + int(np.argmax(score[n - tail:]))
    beats = []
    while t >= 0:
        beats.append(t)
        t = back[t]
    beats = np.array(beats[::-1])
    # 补齐开头被漏掉的拍
    while beats[0] - period > 0:
        beats = np.insert(beats, 0, int(round(beats[0] - period)))
    return beats


def downbeat_phase(beats, env, low, beats_per_bar=4):
    """找出每 4 拍中哪一拍是重拍：低频冲击 + 总体冲击 + 和声变化最强的那个相位"""
    strength = []
    for b in beats:
        w = slice(max(0, b - 2), b + 3)
        strength.append(1.5 * low[w].max() + env[w].max())
    strength = np.array(strength)
    best, best_s = 0, -1
    for ph in range(beats_per_bar):
        s = strength[ph::beats_per_bar].mean()
        if s > best_s:
            best, best_s = ph, s
    return best, strength


def chroma_key(S, bins):
    freqs = bins[1:]
    pitch = np.round(12 * np.log2(freqs / 440) + 69).astype(int) % 12
    chroma = np.zeros(12)
    energy = S[1:].mean(axis=1)
    for p in range(12):
        chroma[p] = energy[pitch == p].sum()
    major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    best = None
    for t in range(12):
        for mode, prof in (("major", major), ("minor", minor)):
            r = np.corrcoef(np.roll(prof, t), chroma)[0, 1]
            if best is None or r > best[0]:
                best = (r, t, mode)
    return {"tonic": names[best[1]], "tonicPc": int(best[1]), "mode": best[2]}


def sections(M, fps, bar_times, duration):
    """按小节算特征，用自相似矩阵的新奇度切段，并给每段一个能量等级"""
    feats, rms = [], []
    frames = (np.array(bar_times + [duration]) * fps).astype(int)
    for a, b in zip(frames[:-1], frames[1:]):
        b = max(b, a + 1)
        seg = M[:, a:b]
        feats.append(seg.mean(axis=1))
        rms.append(seg.mean())
    F = np.array(feats)
    F = (F - F.mean(0)) / (F.std(0) + 1e-9)
    F /= np.linalg.norm(F, axis=1, keepdims=True) + 1e-9
    SSM = F @ F.T
    L = 4  # 4 小节核
    k = np.kron(np.array([[1, -1], [-1, 1]]), np.ones((L, L)))
    nov = np.zeros(len(F))
    for i in range(L, len(F) - L):
        nov[i] = (SSM[i - L:i + L, i - L:i + L] * k).sum()
    # 只在 4 小节边界上找峰（流行歌曲的乐句都是 4/8 小节）
    peaks = find_peaks(nov, distance=4, height=np.percentile(nov, 70))
    bounds = sorted(set([0] + [int(round(p / 4) * 4) for p in peaks] + [len(F)]))
    bounds = [b for i, b in enumerate(bounds) if i == 0 or b - bounds[i - 1] >= 4 or b == len(F)]
    rms = np.array(rms)
    lo, hi = np.percentile(rms, 20), np.percentile(rms, 90)
    out = []
    for a, b in zip(bounds[:-1], bounds[1:]):
        e = float(np.clip((rms[a:b].mean() - lo) / (hi - lo + 1e-9), 0, 1))
        out.append({"startBar": a, "endBar": b, "start": bar_times[a],
                    "end": bar_times[b] if b < len(bar_times) else duration, "energy": round(e, 3)})
    # 打标签：第一段低能量=前奏，能量最高的若干段=副歌
    es = [s["energy"] for s in out]
    thr = np.percentile(es, 60) if len(es) > 2 else 1
    for i, s in enumerate(out):
        if i == 0 and s["energy"] < 0.5:
            s["label"] = "intro"
        elif i == len(out) - 1 and s["energy"] < 0.5:
            s["label"] = "outro"
        elif s["energy"] >= thr:
            s["label"] = "chorus"
        else:
            s["label"] = "verse"
    return out


def main(path, out):
    y = load(path)
    duration = len(y) / SR
    S = stft_mag(y)
    fps = SR / HOP
    env, low, M = onset_envelope(S)
    bpm = estimate_tempo(env, fps)
    bf = track_beats(env, fps, bpm)
    beat_times = (bf * HOP + NFFT / 2) / SR + LATENCY
    beat_times = beat_times[(beat_times >= 0) & (beat_times < duration)]
    bf = ((beat_times - LATENCY) * SR - NFFT / 2) / HOP
    bf = np.clip(np.round(bf).astype(int), 0, len(env) - 1)
    # 用实际拍间隔修正 BPM
    bpm_refined = 60 / np.median(np.diff(beat_times))
    phase, strength = downbeat_phase(bf, env, low)
    downbeats = beat_times[phase::4]
    bar_times = [float(t) for t in downbeats]
    secs = sections(M, fps, bar_times, duration)
    # 每拍的冲击强度(0-1)，可用来挑"最重"的重拍做大转场
    s = strength / (strength.max() + 1e-9)
    data = {
        "source": os.path.basename(path),
        "duration": round(duration, 3),
        "sampleRate": SR,
        "bpm": round(float(bpm_refined), 2),
        "beatsPerBar": 4,
        "firstDownbeatIndex": int(phase),
        "key": chroma_key(S, np.fft.rfftfreq(NFFT, 1 / SR)),
        "beats": [round(float(t), 3) for t in beat_times],
        "beatStrength": [round(float(v), 3) for v in s],
        "downbeats": [round(t, 3) for t in bar_times],
        "sections": secs,
    }
    with open(out, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"时长 {duration:.1f}s | BPM {bpm_refined:.1f} | 拍数 {len(beat_times)} | 小节 {len(bar_times)} | "
          f"调性 {data['key']['tonic']} {data['key']['mode']}")
    print("重拍(前16个):", ", ".join(f"{t:.2f}" for t in bar_times[:16]))
    for sct in secs:
        print(f"  {sct['label']:7s} 小节 {sct['startBar']:3d}-{sct['endBar']:3d}  "
              f"{sct['start']:6.2f}s-{sct['end']:6.2f}s  能量 {sct['energy']:.2f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "src/beats.json")
