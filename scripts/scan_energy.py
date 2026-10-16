#!/usr/bin/env python3
"""扫能量：给一首歌画出逐小节能量图，并推荐一个"时长合适 + 结构好"的剪辑窗口。
用法:
  python scripts/scan_energy.py src/beats.json public/music.f32 --bars 42 --top 8
  python scripts/scan_energy.py src/beats.json public/music.f32 --seconds 89

输出三样东西：
  1) 逐小节 RMS 图（找静音坎 / 高潮块）
  2) 目标小节数下平均能量最高的若干窗口
  3) 推荐窗口 + 窗口内静音坎落在百分之几处（用来放"反转/顿悟"那一屏）
只依赖 numpy。
"""
import argparse
import json
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('beats_json')
    ap.add_argument('f32')
    ap.add_argument('--bars', type=int, default=0, help='窗口小节数（优先于 --seconds）')
    ap.add_argument('--seconds', type=float, default=0, help='窗口秒数（自动换算成小节）')
    ap.add_argument('--top', type=int, default=8)
    a = ap.parse_args()

    d = json.load(open(a.beats_json))
    sr = d['sampleRate']
    y = np.fromfile(a.f32, dtype='<f4')
    db, dur, bpm = d['downbeats'], d['duration'], d['bpm']
    bar_sec = 60 / bpm * 4

    W = a.bars or (round(a.seconds / bar_sec) if a.seconds else 42)
    rms = []
    for i, t in enumerate(db):
        end = db[i + 1] if i + 1 < len(db) else dur
        s = y[int(t * sr):int(end * sr)]
        rms.append(float(np.sqrt((s ** 2).mean() + 1e-12)))
    rms_arr = np.array(rms)
    mx = rms_arr.max()

    print(f'BPM {bpm:.1f} · 每小节 {bar_sec:.3f}s · 共 {len(db)} 小节 · 总长 {dur:.1f}s')
    print(f'目标窗口 {W} 小节 = {W * bar_sec:.2f} 秒\n')
    print('bar   起始     RMS      dB   |能量|')
    for i, (t, r) in enumerate(zip(db, rms)):
        print(f'{i:3d} {t:7.2f} {r:8.4f} {20 * np.log10(r + 1e-12):6.1f} ' + '#' * int(round(46 * r / mx)))

    # 窗口排名
    cand = []
    for s in range(0, max(1, len(db) - W)):
        seg = rms_arr[s:s + W]
        cand.append((float(seg.mean()), s, db[s], db[s + W] if s + W < len(db) else dur))
    cand.sort(reverse=True)

    def dip_of(s):
        """窗口内侧最安静的那一小节 → (小节号, 在窗口里的百分比)"""
        inner = rms_arr[s + 2:s + W - 2]
        if not len(inner):
            return s + W // 2, 50.0
        rel = int(np.argmin(inner)) + 2
        return s + rel, rel / W * 100

    print(f'\n平均能量最高的 {a.top} 个 {W} 小节窗口（含"静音坎"位置）：')
    for m, s, t0, t1 in cand[:a.top]:
        dbar, dpos = dip_of(s)
        print(f'  小节 {s:3d}-{s + W:3d}  {t0:7.2f}s → {t1:7.2f}s  平均RMS {m:.4f}   坎在第 {dbar} 小节（{dpos:4.0f}%）')

    # 推荐：反转点（静音坎）最好落在窗口 36%–46% 处；在这个前提下取能量最高的
    ideal = [(m, s, t0, t1, *dip_of(s)) for (m, s, t0, t1) in cand if 36 <= dip_of(s)[1] <= 46]
    if ideal:
        pick = max(ideal, key=lambda x: x[0])
    else:
        m, s, t0, t1 = cand[0]
        pick = (m, s, t0, t1, *dip_of(s))

    m, s, t0, t1, dbar, dpos = pick
    print(f'\n★ 推荐：START_BAR={s}  END_BAR={s + W}   （{t0:.2f}s → {t1:.2f}s，{t1 - t0:.2f}s，平均RMS {m:.4f}）')
    print(f'  静音坎在第 {dbar} 小节（{db[dbar]:.2f}s，RMS {rms_arr[dbar]:.4f}），落在窗口 {dpos:.0f}% 处')
    print('  → 把"反转/顿悟"那一屏放在这个坎之后的第一记重拍上')
    top_m, top_s, *_ = cand[0]
    if top_s != s:
        print(f'  （纯按能量最高会选 {top_s}-{top_s + W}，但那个窗口的坎落在 {dip_of(top_s)[1]:.0f}% 处；')
        print('    坎太靠前会让反转来得太早，所以这里优先了坎位）')
    print('\n把 START_BAR / END_BAR 填进 src/script.ts 即可。')


if __name__ == '__main__':
    main()
