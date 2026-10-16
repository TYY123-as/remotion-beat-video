# AGENTS.md — remotion-beat-video 通用 Agent 指令

> 本文件是给 AI 编程助手（Claude Code / Codex / Cursor / Trae 等）看的入口指令，自动读取并遵守。

## 你拿到了什么

一套**把选题拍成 Remotion 卡点短视频**的流水线 skill：从 BGM 到成片、封面、发布包、事实核实，
全部是可执行脚本 + 明确的版式与剧本规范。已经用两条真实片子验证过。

## 收到"做一条视频"类请求时，你必须这样做

1. **先读 `SKILL.md`**（八步流程 + 12 条铁律），再读 `references/pipeline.md`（环境与坑）。
2. **选题没定就先给 3 个候选**，每个写清：一句话内核 / 第 1 秒钩子 / 凭什么能画 / 收藏点 / 风险。
   **候选必须先验证存在性**（虚构 IP 要查到章节名或条目），让用户点单，不要自己替他选。
3. **选题定了先做音轨与节拍**（`extract_audio.py` → `analyze_beats.py` → `scan_energy.py`），
   拿到 `START_BAR / END_BAR` 和静音坎位置，**再动笔写剧本**。
4. **剧本写 `src/script.ts` 的 `subs`/`cues`**；所有场景 `bars` 之和必须等于 `END_BAR − START_BAR`。
5. **渲染全片前必须先渲静帧自检**（每场景一张），重点看：字幕压元素、元素互相重叠、安全区 y ≤ 850。
6. **出片后跑 `check_mp4.py`**，确认双轨、时长、分辨率，再交付封面三版与发布包。

## 不可违反的硬约束

- **第 1 秒 = 一句完整冲突句 + 一个具体物**（不是片头动画）。
- **场景元素 y ≤ 850**；字幕在 y≈870–1000；左上抬头区 y 50–95。
- **一句字幕 ≤22 字、停留 ≥2.2 秒**，中文主句 + 英文对照。
- **结尾必须是可截图清单**（收藏点）+ 一句提问 + 出处；只给感慨不算结尾。
- **虚构 IP 三层标注**（原著原文 / 读者复述 / 推测），片子只写前两层的共识，其余进待核清单；
  片尾必须标"图示为示意"；不写死数字与章节号。
- **不要用旧文案裁出来的子集字体**；直接写系统字体栈。
- **第二支及以后的片子必须有独立的 `timeline.ts` + `fx.tsx`**（冲击点依赖各自的 beats.json）。

## 环境（本机实测，务必照抄）

```powershell
$node="C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe"
$py="C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$pnpm="C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\pnpm\bin\pnpm.mjs"
# Remotion CLI 入口是 remotion-cli.js（不是 dist/index.js）
& $node node_modules\@remotion\cli\remotion-cli.js render <Comp> out/x.mp4 --codec=h264 --crf=18 --concurrency=6
```

- **没有系统 ffmpeg** → `pip install imageio-ffmpeg`；`extract_audio.py` 会自己找。
- **没有 scipy** → `analyze_beats.py` 已改纯 numpy。
- **没有 npm** → 用 pnpm；装完必须 `pnpm rebuild esbuild`。
- 渲染并发 6x，**~1.35 帧/秒**；Remotion 早期 ETA 虚高，别被吓到。

## 能力边界（对用户诚实）

- 本流程**无配音**；要旁白需另配 TTS 并重新对齐。
- 网络受限时（多数域名被 DNS 拦）只能靠 `web_search` 标题 + B 站接口，**取不到原著正文就必须走待核清单**。
- 不要承诺"几分钟出片"：一条 89 秒 1080p 约 35 分钟。

## 语言

与用户交流用中文；代码注释用中文；字幕为**中文主句 + 英文对照**（本账号风格）。
