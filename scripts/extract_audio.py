#!/usr/bin/env python3
"""从 mp4/mov/mp3 里抽音轨，产出给节拍分析用的 .f32（单声道 float32）+ sidecar，另存一份 mp3 当 BGM。
本机没有系统 ffmpeg 时，自动用 pip 版 imageio-ffmpeg 自带的二进制。

用法:
  python scripts/extract_audio.py 输入.mp4 输出目录
  python scripts/extract_audio.py 输入.mp3 输出目录 --sr 48000

产出:
  输出目录/audio.f32        单声道 float32（analyze_beats.py 直接读它）
  输出目录/audio.f32.json   采样率等元信息
  输出目录/music.mp3        48k 立体声 192kbps，可直接放进 Remotion 的 public/
"""
import argparse
import json
import os
import shutil
import subprocess
import sys


def find_ffmpeg():
    p = shutil.which('ffmpeg')
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    sys.exit('找不到 ffmpeg：pip install imageio-ffmpeg 或把 ffmpeg 放进 PATH')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('outdir')
    ap.add_argument('--sr', type=int, default=48000)
    ap.add_argument('--mp3-bitrate', default='192k')
    a = ap.parse_args()

    ff = find_ffmpeg()
    os.makedirs(a.outdir, exist_ok=True)
    f32 = os.path.join(a.outdir, 'audio.f32')
    mp3 = os.path.join(a.outdir, 'music.mp3')

    print(f'ffmpeg: {ff}')
    subprocess.run([ff, '-v', 'error', '-y', '-i', a.input, '-vn', '-ac', '1', '-ar', str(a.sr), '-f', 'f32le', f32], check=True)
    subprocess.run([ff, '-v', 'error', '-y', '-i', a.input, '-vn', '-ac', '2', '-ar', str(a.sr), '-b:a', a.mp3_bitrate, mp3], check=True)

    n = os.path.getsize(f32) // 4
    meta = {'sampleRate': a.sr, 'channels': 1, 'samples': n, 'duration': round(n / a.sr, 3)}
    json.dump(meta, open(f32 + '.json', 'w'))
    print(f'单声道 f32: {f32}  {meta["duration"]}s')
    print(f'BGM mp3   : {mp3}  {os.path.getsize(mp3) / 1048576:.1f} MB')
    print('\n下一步：python scripts/analyze_beats.py ' + f32 + ' src/beats.json')
    print('再下一步：python scripts/scan_energy.py src/beats.json ' + f32 + ' --seconds 89')


if __name__ == '__main__':
    main()
