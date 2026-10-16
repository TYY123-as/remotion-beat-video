#!/usr/bin/env python3
"""封面生成：从已经渲好的静帧里裁一块，配上中文大标题，出 16:9 / 3:4 / 9:16 三版。
只依赖 Pillow + Windows 自带的微软雅黑。

用法:
  python scripts/make_covers.py --src out/j2_950.png --crop 90,320,1830,790 \
      --title 庄家在号码里 --kicker 十日终焉·极乐钱庄 --sub 十二个位置里，有一个是他自己 \
      --out-prefix out/封面_极乐钱庄

参数说明:
  --src        底图（任一静帧）
  --crop       x0,y0,x1,y1；竖版会取这一块贴在上半部分。省略则整图
  --h-mode     horizontal 模式：整图铺满 + 底部一句（默认）
  --title-size 可选，默认按画布宽度自动
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

FONT_B = 'C:/Windows/Fonts/msyhbd.ttc'
FONT_R = 'C:/Windows/Fonts/msyh.ttc'


def font(p, s):
    return ImageFont.truetype(p, s, index=0)


def darken(img, top_frac, strength=250):
    w, h = img.size
    mask = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(mask)
    top = int(h * top_frac)
    for y in range(top, h):
        d.line([(0, y), (w, y)], fill=int(strength * ((y - top) / max(1, h - top)) ** 1.25))
    return Image.composite(Image.new('RGB', (w, h), (2, 2, 3)), img, mask)


def horizontal(src, title, kicker, sub, w=1920, h=1080):
    img = Image.open(src).convert('RGB').resize((w, h), Image.LANCZOS)
    dr = ImageDraw.Draw(img)
    if kicker:
        dr.text((w // 2, h - 150), kicker, font=font(FONT_B, 34), fill=(255, 198, 90), anchor='ma',
                stroke_width=2, stroke_fill=(0, 0, 0))
    if title:
        dr.text((w // 2, h - 96), title, font=font(FONT_B, 62), fill=(255, 255, 255), anchor='ma',
                stroke_width=3, stroke_fill=(0, 0, 0))
    if sub:
        dr.text((w // 2, h - 40), sub, font=font(FONT_R, 40), fill=(232, 226, 214), anchor='ma',
                stroke_width=2, stroke_fill=(0, 0, 0))
    return img


def vertical(src, crop, title, kicker, sub, w, h):
    img = Image.new('RGB', (w, h), (4, 4, 5))
    if crop:
        band = Image.open(src).convert('RGB').crop(crop)
    else:
        band = Image.open(src).convert('RGB')
        band = band.crop((0, int(band.height * 0.25), band.width, int(band.height * 0.75)))
    tw = int(w * 0.98)
    th = int(band.height * tw / band.width)
    if th > int(h * 0.46):  # 太高就等比缩到 46% 画布高
        th = int(h * 0.46)
        tw = int(band.width * th / band.height)
    band = band.resize((tw, th), Image.LANCZOS)
    img.paste(band, ((w - tw) // 2, int(h * 0.10)))
    img = darken(img, 0.44)

    dr = ImageDraw.Draw(img)
    fk, fb, fs = font(FONT_B, int(w * 0.030)), font(FONT_B, int(w * 0.125)), font(FONT_R, int(w * 0.042))
    ky = int(h * 0.45)
    if kicker:
        kw = dr.textbbox((0, 0), kicker, font=fk)[2]
        dr.rectangle([w // 2 - kw // 2 - 26, ky - 16, w // 2 + kw // 2 + 26, ky + fk.size + 18], outline=(255, 198, 90), width=3)
        dr.text((w // 2, ky), kicker, font=fk, fill=(255, 198, 90), anchor='ma')
    if title:
        dr.text((w // 2, ky + int(h * 0.085)), title, font=fb, fill=(255, 255, 255), anchor='ma',
                stroke_width=max(2, fb.size // 40), stroke_fill=(0, 0, 0))
    if sub:
        dr.text((w // 2, ky + int(h * 0.215)), sub, font=fs, fill=(232, 226, 214), anchor='ma',
                stroke_width=2, stroke_fill=(0, 0, 0))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--crop', default='')
    ap.add_argument('--title', default='')
    ap.add_argument('--kicker', default='')
    ap.add_argument('--sub', default='')
    ap.add_argument('--out-prefix', required=True)
    a = ap.parse_args()

    crop = tuple(int(x) for x in a.crop.split(',')) if a.crop else None
    jobs = [
        (a.out_prefix + '_16x9.png', horizontal(a.src, a.title, a.kicker, a.sub)),
        (a.out_prefix + '_3x4.png', vertical(a.src, crop, a.title, a.kicker, a.sub, 1080, 1440)),
        (a.out_prefix + '_9x16.png', vertical(a.src, crop, a.title, a.kicker, a.sub, 1080, 1920)),
    ]
    for path, im in jobs:
        os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
        im.save(path, quality=95)
        print(f'{path}  {im.width}x{im.height}  {os.path.getsize(path) / 1024:.0f} KB')


if __name__ == '__main__':
    main()
