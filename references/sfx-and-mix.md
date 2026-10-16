# 音效与混音

## 一、音效合成（按 BGM 的调性）

```bash
python scripts/synth_sfx.py src/beats.json public/sfx
```
读 `beats.json` 里的 `key`，按大/小调音阶生成：

- **旋律类**（各 10 个音级）：`marimba kalimba glock celesta bell vibes glass piano lyre zheng oud sitar pizz blip`
- **打击/环境**：`woodblock taiko gong bowl timpani boom swish swell`
- 一共 148 个（14×10 + 8）

**关键**：音效是**定调生成**的。BGM 是 F# 大调，就必须用 F# 的 `beats.json` 生成；
换歌不重新生成，音效会和音乐打架（差半音也听得出来）。

**没有 ffmpeg 时**：脚本自动跳过 FLAC 转换、保留 WAV；此时 `src/Main.tsx` 里的
`const SFX_EXT = 'wav'`（有 ffmpeg 就改成 `'flac'`）。

**体积**：148 个约 66MB，而 `public/` 每次渲染会被整体拷贝 —— **只保留用到的**。
实测一条片只用 16 个（4.5MB），其余挪到 `tools/sfx_full/`。

## 二、音效选型表（实测好用）

| 用途 | 音效 | 备注 |
|---|---|---|
| 开场/大转折低频冲击 | `boom` | 配 `impact:'big'` |
| 心跳/压迫 | `timpani` | 也可做高潮段垫底 |
| 重物落下、关门 | `taiko` | 中频，比 boom 清晰 |
| 金属砸落、片名 | `gong` | 尾巴长，别连用 |
| 提示/金属轻响 | `bowl` | 神秘感 |
| 逐条清单落点 | `bell_1/3/5` | 一条一个音 |
| 编号/数字跳变 | `blip_3/5/7` | 短促 |
| 玻璃感/揭开 | `glass_3/10` | |
| 转场前的风 | `swish` | 用在硬切前 0.3s |
| 弦乐渐强 | `swell` | 用在段首铺底 |
| 咔哒/点击（最关键的动作） | `woodblock`（`vol:0.85` + `impact:'big'`） | 本例"双锁咔哒"用的就是它 |

## 三、写 cue 的规范

```ts
cues: [
  {id: 'open', beat: 0, sfx: 'boom', vol: 0.6, impact: 'big'},   // 场景开场
  {id: 't1', beat: 2, sfx: 'woodblock', vol: 0.5},
  {id: 'click', beat: 9, sfx: 'woodblock', vol: 0.85, impact: 'big'},  // ★ 全片最重一击
  {id: 'sting', beat: 14, sfx: 'gong', vol: 0.5},
]
```
- 场景开场必给一记（`boom`/`gong`/`timpani`）。
- **每个场景 3–6 个 cue**：多了吵，少了空。
- `impact:'big'` 全片 5–8 次；`'small'` 可以多些。
- 关键动作落在**正拍**，装饰性音效可以落半拍（`beat: 9.25`）。

## 四、混音

```ts
const MUSIC_VOL = 0.62;   // 音乐为主
const SFX_VOL   = 0.6;    // 音效只点关键节点
```

**侧链让位**（大冲击时音乐自动退 40 帧，冲击更实）：
```ts
const BIG_HITS = PLACED.flatMap(sc => sc.def.cues.map((c,i)=> c.impact==='big' ? sc.from+cueFrame(sc,i) : -1).filter(x=>x>=0));
const duck = (f:number) => { let d=1; for (const at of BIG_HITS) if (f>=at && f<at+40) d=Math.min(d, 1-0.5*Math.exp(-(f-at)/10)); return d; };
```

**高潮段垫底**：在第 42–52 小节这类最响的段，每隔一个重拍加一记 `timpani`（`vol:0.2`），把能量顶住：
```ts
for (let bar = 42; bar < 52; bar += 2) ACCENTS.push({frame: down(bar), sfx: 'timpani', vol: 0.2});
```

**收尾淡出**：`interpolate(f, [TOTAL-70, TOTAL], [1, 0])`。

## 五、验收（你听不到声音，所以要"看"）

1. 成片轨道数 ≥ 2（`check_mp4.py` 会报 `soun ... 48000 Hz`）。
2. 想确认某段有没有声音：把音乐/音效波形画出来看，或渲染该段的短 mp4 检查文件体积（静音段会明显偏小）。
3. 混音前先看峰值：`synth_sfx.py` 每个音效自带归一化（peak 0.8），叠三个以上同类要手动降 `vol`。
