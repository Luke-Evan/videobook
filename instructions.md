# VideoBook Agent 工作流指令

> **权威操作手册已迁移到 Codex Skill：[`skills/videobook/SKILL.md`](skills/videobook/SKILL.md)。**
> 本文件只保留触发条件与流程概览，供人以及不支持 skill 机制的 AI 助手（Antigravity / Claude Code 等）快速上手。
> 细节一律以 skill 目录为准，两处不要同时维护。下表的 `references/*` 均指 `skills/videobook/references/*`。

## 触发条件

用户发来一条包含 YouTube (`youtube.com`, `youtu.be`) 或 B站 (`bilibili.com`) 视频链接的消息，
并表示希望将其生成为电子书 / 教程 / 指南。

## 一分钟概览

工作目录始终为本仓库根目录（本文件所在目录），所有相对路径都相对它解析。
Python 命令用仓库环境执行：`uv run python src/xxx.py` 或 `.venv\Scripts\python.exe src/xxx.py`。

| 步 | 做什么 | 命令 | 细节 | 提权 |
|---|---|---|---|---|
| 0 | 首次：专用配置扫码登录一次 | `python src/capture_frames.py --setup-profile` | `references/capture.md` | 是 |
| 1 | 提取字幕（无字幕时本地 ASR 兜底） | `python src/dump_transcript.py "<URL>"` / `python src/asr_transcript.py <video_id>` | `references/transcript.md` | B 站需 |
| 1.5 | 可选：课程官方讲义 + 4K 幻灯片 | `python src/course_assets.py <video_id> --course-url <课程主页>` | `references/course-assets.md` | 渲染需 |
| 2 | 按 stitcher prompt 改写出 `book.md` | 读 `prompts/stitcher_system.md` 后自行生成 | `references/writing.md` | 否 |
| 2b | 可选：字幕校订对照稿 | `python src/make_corrected.py <video_id>` | `references/correction.md` | 否 |
| 3 | 截帧并物化截图占位符 | `python src/capture_frames.py <video_id> "<URL>"` | `references/capture.md` | 是 |
| 4 | 渲染 HTML + 起本地预览 | `python src/post_process.py "<URL>" output/<id>/book.md`，再 `python -m http.server 8080 --directory output/<id>` | — | 否 |
| 5 | 告知结果、提示代理与清晰度、询问是否删大文件 | — | SKILL.md「交付」 | — |
| 6 | 可选：发布到 `pages` 分支 | `python src/publish.py <video_id>`，再 `git push origin pages` | `references/publish.md` | 否 |

## 三条最容易踩的红线

1. **字幕覆盖率 < 50%（退出码 3）不得进入第二步**：先修登录态 / 代理，或转 ASR 兜底。
2. **截图必须来自已登录浏览器里的平台播放器**，第三步不得下载视频 / 音频文件（ffmpeg 抽帧只是最后兜底）。
3. **cookies 只写系统临时目录、用完即删，绝不落仓库**；`output/` 不受任何 git 操作影响，成品只发布到 `pages` orphan 分支。

完整铁律（11 条）、沙箱提权清单、交付话术见 `skills/videobook/SKILL.md`；报错与画质问题见
`skills/videobook/references/troubleshooting.md`。

## 作为 Codex Skill 使用

- 本机：把 `skills/videobook/` 复制或软链到 `~/.codex/skills/`（仅 Codex）或 `~/.agents/skills/`（跨 agent）。
- 别人：用 `skill-installer` 从 `Luke-Evan/videobook` 仓库的 `skills/videobook` 路径安装。
- 装好后新开一个任务，直接发「帮我把这个视频做成电子书：<链接>」即可自动触发，也可以显式调用 `$videobook`。