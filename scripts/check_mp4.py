#!/usr/bin/env python3
"""没有 ffprobe 的情况下自检 mp4：解析 box，读时长 / 轨道 / 分辨率 / 音频参数。
用法: python tools/check_mp4.py out/songxin_1080p.mp4
"""
import struct
import sys


def boxes(buf, start, end):
    i = start
    while i + 8 <= end:
        size = struct.unpack('>I', buf[i:i + 4])[0]
        typ = buf[i + 4:i + 8].decode('latin1')
        if size == 1:
            size = struct.unpack('>Q', buf[i + 8:i + 16])[0]
        if size < 8:
            break
        yield typ, i + 8, i + size
        i += size


def find(buf, start, end, path):
    """按路径找第一个匹配的 box，返回 (payload_start, payload_end)"""
    want = path[0]
    for typ, s, e in boxes(buf, start, end):
        if typ == want:
            return (s, e) if len(path) == 1 else find(buf, s, e, path[1:])
    return None


def main(path):
    buf = open(path, 'rb').read()
    print(f'文件: {path}  {len(buf) / 1048576:.1f} MB')

    mvhd = find(buf, 0, len(buf), ['moov', 'mvhd'])
    if mvhd:
        s, _ = mvhd
        ver = buf[s]
        if ver == 0:
            timescale, duration = struct.unpack('>II', buf[s + 12:s + 20])
        else:
            timescale, duration = struct.unpack('>IQ', buf[s + 20:s + 32])
        print(f'时长: {duration / timescale:.2f} 秒  (timescale={timescale})')

    traks = []
    for typ, s, e in boxes(buf, 0, len(buf)):
        if typ == 'moov':
            for t2, s2, e2 in boxes(buf, s, e):
                if t2 == 'trak':
                    traks.append((s2, e2))
    print(f'轨道数: {len(traks)}')
    for idx, (s, e) in enumerate(traks, 1):
        hdlr = find(buf, s, e, ['mdia', 'hdlr'])
        kind = '?'
        if hdlr:
            p, _ = hdlr
            kind = buf[p + 8:p + 12].decode('latin1')
        tkhd = find(buf, s, e, ['tkhd'])
        w = h = 0
        if tkhd:
            p, _ = tkhd
            ver = buf[p]
            base = p + (76 if ver == 0 else 88)
            w, h = struct.unpack('>II', buf[base:base + 8])
            w, h = w / 65536, h / 65536
        info = ''
        if kind == 'soun':
            stsd = find(buf, s, e, ['mdia', 'minf', 'stbl', 'stsd'])
            if stsd:
                p, _ = stsd
                # stsd: version/flags(4) + entry_count(4) + 第一个 sample entry
                entry = p + 8
                fmt = buf[entry + 4:entry + 8].decode('latin1')
                ch = struct.unpack('>H', buf[entry + 24:entry + 26])[0]
                sr = struct.unpack('>I', buf[entry + 32:entry + 36])[0] >> 16
                info = f'  编码 {fmt}  {ch} 声道  {sr} Hz'
        print(f'  轨道 {idx}: {kind}{"  %dx%d" % (w, h) if w else ""}{info}')
    ok = any(buf[s:s + 4] for s, _ in traks)
    print('结论: ' + ('含音频轨 + 视频轨 ✔' if ok else '异常'))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'out/songxin_1080p.mp4')
