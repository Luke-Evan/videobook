# VideoBook Agent

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

给一段 YouTube 或 Bilibili 的视频链接，AI 助手会整理内容逻辑、把演示操作的时间锚点转成内嵌视频卡片与高画质截图，产出一本可在线阅读的技术图文电子书。

## 环境准备

1. `Python >= 3.10`，克隆本仓库
2. 安装依赖：`pip install -r requirements.txt`（或 `uv sync`）
3. 一次性登录：`python src/capture_frames.py --setup-profile`，在弹出的 Chrome 里扫码登录 B 站 / YouTube。登录态长期复用，账号档位决定截图清晰度上限。

处理海外视频时，终端与浏览器都需要走代理。

## 两种用法（效果完全一样）

两种方式跑的是同一套 `src/*.py`，产出相同，区别只在于「助手怎么知道该怎么做」。

**① 直接用本仓库**：在仓库根目录唤醒你的 AI 助手（Codex / Claude Code / Antigravity 等），发一句话即可：

> 请接管帮我把这个视频做成电子书：`https://www.bilibili.com/video/BVxxx/`

助手会按 [`instructions.md`](instructions.md) 执行整条流水线。

**② 作为 Skill 使用**：仓库自带 [`skills/videobook/`](skills/videobook/SKILL.md)，装上后助手会**自动识别**这类请求，不必每次提醒它去读指令文档。

- 在 Codex 里说一句：用 skill-installer 从 GitHub 仓库 `Luke-Evan/videobook` 的 `skills/videobook` 路径安装
- 或把 `skills/videobook/` 复制 / 软链到 `~/.codex/skills/`（仅 Codex）或 `~/.agents/skills/`（跨 agent）
- 装好后新开任务发同一句话即可，也可以显式调用 `$videobook`

完成后你会拿到 `output/<视频ID>/book.md`，以及本地预览地址 `http://localhost:8080/book.html`（助手会自动起服务）。

## 原理

五步流水线，**完整指令与全部细节见 [`instructions.md`](instructions.md)**：

1. **抓字幕**：`src/dump_transcript.py`。平台没有任何字幕时自动用本地 faster-whisper 转写兜底（`src/asr_transcript.py`），产出与平台字幕同构的文件，后续步骤零改动。
2. **课程官方资料增强（默认流程）**：`src/course_assets.py` 抓取课程主页的讲义与幻灯片。讲义用于术语、章节骨架与参考链接校准；幻灯片渲染成 4K 官方图，比任何视频帧都清晰。每讲都会先确认课程是否有主页，只有确认没有才跳过本步。
3. **改写成书**：大模型按 `prompts/stitcher_system.md` 把字幕重构成结构化 Markdown，并在关键处插入 `SCREENSHOT:` / `SLIDE:` 占位。
4. **截帧**：`src/capture_frames.py` 用已登录的浏览器直接截取平台播放器画面（不下载任何媒体文件），把占位符物化为图片。
5. **渲染与预览**：`src/post_process.py` 把时间锚点换成 B 站 / YouTube 原生轻量 iframe、注入暗色主题，生成 `book.html` 并起本地服务。

## 测试

```bash
python -m pytest tests -q
```

覆盖视频卡片渲染（B 站分 P `page=`、回链 query 保留、截图/幻灯片卡片）与字幕校订校验层（源哈希锁定、原文逐字匹配、禁删段/多行/大幅修改等）。

## 成品在哪里看

- 在线阅读：<https://luke-evan.github.io/videobook/>（`pages` 分支，需在 Settings → Pages 一次性启用）
- 发布：`python src/publish.py <video_id>`（或 `--all`），然后 `git push origin pages`
- `main` = 代码，`pages` = 成品（orphan 分支）；`output/` 是本地工作区，不进 git

## 开源许可

Apache License 2.0，见 [LICENSE](LICENSE)。生成的电子书中所含课程视频画面、字幕、讲义与幻灯片，版权归各自权利人所有，不在本许可授予范围内。