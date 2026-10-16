# 流水线：环境、命令、这台机器的全部坑

> 全部内容都在本机实测过（Windows 10 / 4 物理核 / 8GB / 中文路径）。换机器时先跑一遍"环境自检"。

## 一、环境自检（先跑这个）

```powershell
$node="C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
$py="C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $node --version          # v24.x
& $py --version            # 3.12.x
& $py -c "import numpy,scipy;print('ok')"
& $py -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"
Test-Path "node_modules\@remotion\cli\remotion-cli.js"
```

**注意**：`node` / `npm` / `python` **都不在 PATH 里**，必须用上面两个绝对路径。`npm` 不存在，用 DSH 自带的 pnpm：
```powershell
$pnpm="C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\pnpm\bin\pnpm.mjs"
& $node $pnpm install --registry=https://registry.npmmirror.com
& $node $pnpm rebuild esbuild      # ★ 必做：pnpm 默认忽略 esbuild 的构建脚本，不 rebuild 就打包失败
```

## 二、这套机器上**没有**的三样东西，以及替代方案

| 缺什么 | 症状 | 替代方案（已内置到 scripts/） |
|---|---|---|
| **ffmpeg** | `analyze_beats.py` 报 `FileNotFoundError: ffmpeg`；音效转 FLAC 失败 | ① `pip install imageio-ffmpeg`，`scripts/extract_audio.py` 会自动用它；② `decode_mp3.mjs` 用**纯 WASM** 解码 mp3（mpg123-decoder）；③ `synth_sfx.py` 检测不到 ffmpeg 就**保留 WAV**，Remotion 直接读 `.wav` |
| **scipy** | `from scipy import signal` 失败 | `analyze_beats.py` 已改成**纯 numpy**（自己实现 find_peaks）；要用 scipy 就 `pip install scipy`（能装） |
| **npm** | `npm i` 不存在 | 用 pnpm（见上）；注意 `esbuild` 要 rebuild |

另外：`www.bilibili.com` 等**很多域名**在 `web_fetch` 侧被 DNS 拦（解析到非公网 IP），只有 `api.bilibili.com`、`comment.bilibili.com` 这类接口通 —— 见 `fact-check.md`。

## 三、Remotion 工程的关键事实

1. **CLI 入口不是 `dist/index.js`**（那只是导出 internals）：
   ```powershell
   & $node node_modules\@remotion\cli\remotion-cli.js still <Comp> out/x.png --frame=100
   & $node node_modules\@remotion\cli\remotion-cli.js render <Comp> out/x.mp4 --codec=h264 --crf=18 --concurrency=6
   & $node node_modules\@remotion\cli\remotion-cli.js compositions
   ```
2. **必须自己写 `src/index.ts`**（否则报 `entry point ... does not exist`）：
   ```ts
   import {registerRoot} from 'remotion';
   import {RemotionRoot} from './Root';
   registerRoot(RemotionRoot);
   ```
   且 `remotion.config.ts` 里 `Config.setEntryPoint('./src/index.ts')`。
3. **`useCurrentFrame()` 在 `<Sequence>` 内是相对帧** —— 场景组件里 `f` 从 0 开始，直接当场景内时间用。
4. **多支片共用一个工程**时，第二支必须有**自己的 timeline/fx**：`fx.tsx` 里的 `Shell`/`ImpactFlash` 写死了 `cueFrame`（用 `beats.json`），直接复用会把冲击点对到第一首歌的拍子上。
5. **音频偏移**：`<Audio src={staticFile('music2.mp3')} startFrom={OFF} />` + `<Sequence from={-OFF}>`，`OFF = round(downbeats[START_BAR] * 30)`。
6. **`public/` 每次渲染整体拷贝**：音效只留用到的（本例 148 → 16 个，省 60MB/次）。

## 四、性能（4 核笔记本实测）

| 项 | 实测值 |
|---|---|
| 打包（首次） | ~25 s；之后有缓存 |
| 单帧渲染 | 稳定 **~1.35 帧/秒**（并发 6x） |
| 89 秒片（2681 帧） | **约 35 分钟** |
| 静帧（still） | 约 15–25 秒/张（含打包则更久） |
| Remotion 早期 ETA | **虚高**（会显示 2–3 小时），用基准测试校准：`render --frames=120-139` 计 20 帧耗时 |

**提速经验**：并发 6x 已接近这台机的上限（4 物理核）；全屏 `filter: blur(40px)` 这类逐帧重栅格化的效果是性能杀手，能用渐变替代就别用 blur。

## 五、字体

- **不要**复用别的视频的 `public/fonts/*.woff`：那类文件是**按旧文案裁的子集**，新文案会缺字（渲染出来是豆腐块）。
- 直接用系统字体栈：
  ```ts
  export const SANS = '"Noto Sans SC","Noto Sans","Microsoft YaHei",sans-serif';
  export const SERIF = 'Georgia,"Times New Roman","Noto Sans SC",serif';
  ```
  本机装有 `NotoSansSC-VF.ttf`、`msyh.ttc`（微软雅黑）、`simhei.ttf`，中文覆盖没问题。
- 数字用 `Consolas, monospace`（倒计时、编号要等宽）。

## 六、成片自检

```bash
python scripts/check_mp4.py out/xxx.mp4
# 输出示例：
# 时长: 89.43 秒  (timescale=1000)
# 轨道 1: vide  1920x1080
# 轨道 2: soun  编码 mp4a  2 声道  48000 Hz
```
它直接解析 mp4 的 `moov/mvhd/trak/hdlr/stsd`，**不需要 ffprobe**。重点确认：双轨在、时长对、分辨率对。

## 七、常见报错 → 处置

| 报错 | 原因 | 处置 |
|---|---|---|
| `entry point ... does not exist` | 没写 `src/index.ts` | 见上 |
| `Cannot read properties of undefined (reading 'len')`（mpg123） | 没 `await dec.ready` | WASM 要先 await ready |
| `ERR_PNPM_IGNORED_BUILDS: esbuild` | pnpm 忽略构建脚本 | `pnpm rebuild esbuild` |
| 渲染出来是方块/问号 | 字体子集缺字 | 换系统字体栈 |
| 冲击点全部错位 | 第二支复用了第一支的 fx | 给第二支写自己的 Shell/Flash |
| `still` 出来的图很灰/有色散 | 正好落在 `impact:'big'` 的那一帧 | 换一帧再看（不是 bug） |
