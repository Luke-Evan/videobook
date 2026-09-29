---
name: videobook
description: 用 videobook 流水线把一个 YouTube / Bilibili 视频（尤其是课程录像）做成图文并茂的 Markdown + HTML 技术电子书：提取字幕（平台无字幕时用本地 faster-whisper ASR 兜底）、由大模型改写并插入 SCREENSHOT/SLIDE 占位、用已登录浏览器直接截取播放器高画质帧、渲染暗色主题 HTML 并起本地预览、可选抓取课程官方讲义与 4K 幻灯片增强、生成字幕校订对照稿、最后发布到 GitHub Pages 的 pages 分支。当用户给出视频链接或 BV 号并要求做成电子书/教程/图文/文档、要字幕纠错对照稿、要给文章配视频截图、或要发布已生成的 output 时使用。不负责单纯下载视频或字幕、视频剪辑，以及与本流水线无关的网页爬取。
metadata:
  short-description: 视频转图文电子书流水线
---

# VideoBook：把一个视频做成一本图文电子书

用户给一个 YouTube / Bilibili 链接，产出一本可在线阅读的技术电子书：
`output/<video_id>/book.md` + `book.html`（内嵌播放器卡片、截图点击放大、Mermaid 图），
可选 `transcript.corrected.txt` 字幕校订对照稿，并可发布到 GitHub Pages 供他人阅读。

本 skill 是**编排层**：真正的逻辑都在仓库的 `src/*.py` 里，命令与参数一律以脚本 `--help` 为准。
不要重写脚本逻辑，也不要把脚本内容（尤其是错词 MAP、stitcher prompt）复制进 skill —— 那会立刻腐化。

## 前置条件（首次运行必读）

1. **工作目录 = 仓库根目录**，所有相对路径（`output/<video_id>/...`）都相对它解析。
   仓库不在本地时先 clone 到用户的项目目录，不要在临时目录里跑。
2. Python >= 3.10（推荐 3.12）。装依赖：`uv sync`（用 uv 时）或 `pip install -r requirements.txt`。
   执行统一走仓库环境的解释器：`uv run python src/xxx.py` 或 `.venv/Scripts/python.exe src/xxx.py`。
3. **一次性登录**：`python src/capture_frames.py --setup-profile` 弹出专用 Chrome（数据目录 `.capture-profile/`），
   扫码登录 B 站 / YouTube 后关窗即可，登录态长期复用。登录账号的会员档位 = 截图清晰度上限。
4. 海外视频：**终端要代理**（抓字幕），**浏览器也要全局代理**（否则生成页面里的 YouTube iframe 是一片黑块）。
5. 需要沙箱外/提权的命令见总览表最后一列；纯本地步骤沙箱内即可。

## 流水线总览

| 步 | 做什么 | 命令 | 细节 | 提权 |
|---|---|---|---|---|
| 1 | 提取字幕 | `python src/dump_transcript.py "<URL>"` | `references/transcript.md` | B 站需 |
| 1b | 平台无字幕时本地 ASR 兜底 | `python src/asr_transcript.py <video_id>` | `references/transcript.md` | 否（耗时长） |
| 1.5 | 课程官方讲义 + 4K 幻灯片（可选） | `python src/course_assets.py <video_id> --course-url <课程主页>` | `references/course-assets.md` | 渲染需 |
| 2 | 大模型把字幕改写成 `book.md` | 读 `prompts/stitcher_system.md` 后自行生成 | `references/writing.md` | 否 |
| 2b | 字幕校订对照稿（可选） | `python src/make_corrected.py <video_id>` | `references/correction.md` | 否 |
| 3 | 截帧并把占位符物化为图片 | `python src/capture_frames.py <video_id> "<URL>"` | `references/capture.md` | 是 |
| 4 | 渲染 HTML + 起本地预览 | `python src/post_process.py "<URL>" output/<id>/book.md` 然后 `python -m http.server 8080 --directory output/<id>` | — | 否 |
| 5 | 告知用户结果、询问大文件清理 | — | 见下方「交付」 | — |
| 6 | 发布成品到 `pages` 分支（可选） | `python src/publish.py <video_id>` 然后 `git push origin pages` | `references/publish.md` | 否（push 需网络） |

报错、画质不对、字幕抓不到、ASR 中断等问题先查 `references/troubleshooting.md`。

## 铁律（不可协商）

1. **字幕覆盖率 < 50%（退出码 3）不得进入第二步**：先修登录态/代理，或转 ASR 兜底。
2. **截图画面必须来自已登录浏览器里的平台播放器**，第三步任何方式都不得下载视频/音频文件（ffmpeg 抽帧只是最后兜底）。禁用方式清单见 `references/capture.md`。
3. **cookies 只写系统临时目录、用完即删**，绝不落仓库，也不要在工作区手放 `cookies.txt`。
4. **`output/` 不受任何 git 操作影响**；成品只发布到 orphan 分支 `pages`，`main` 只放代码。
5. **校订稿保真**：逐段保留讲师原词与顺序，只做 ASR 错词替换 + 口癖清理；禁删段、禁多行、禁大幅改写（校验层会直接拒绝）。
6. **写书保真底线**：书面化不等于摘要化；保留类比、案例、推导链；编者补充必须标注「编者说明」。
7. **课程资料版权**：讲义与幻灯片归讲师（常见 CC BY-NC），书首信息块与文末必须保留出处链接、作者署名与许可名。
8. **幻灯片覆盖铁律**：`slides_text.md` 里每一页在书中恰好出现一次，交稿前 `--audit` 必须 PASS。
9. **删除大文件（`audio.m4a`、`video_source.mp4` 等）前必须问用户**，得到确认再删。
10. 生成或修改 HTML 时，文本与背景对比度不低于 WCAG AA 的 4.5:1。
11. 各步幂等可重跑：占位符物化前脚本自动备份 `book.tagged.md`，只要它还在，重跑第三步即可恢复截图。

## 交付（第五步要一次性说清）

1. `output/<video_id>/book.md` 的位置；
2. 预览地址 `http://localhost:8080/book.html`，关闭服务在终端按 `Ctrl+C`；
3. YouTube 视频需浏览器能访问 YouTube（代理），B 站视频可直接看；
4. 截图清晰度取决于 `.capture-profile/` 里登录账号的档位；要更清晰就换账号登录后重跑第三步；
5. 用了课程官方资料时，说明书中幻灯片插图是官方 4K 渲染图（书首已注明来源与 CC 许可），演示帧仍是视频帧，`course/` 目录可整体删除不影响阅读；
6. 询问是否删除流程中产生的大媒体文件（铁律 9）。

## 维护约定

- 本 skill 与流水线代码同仓库版本化：**改了 `src/*.py` 的参数、步骤顺序或铁律，必须同步改这里**。
- 仓库根的 `instructions.md` 是给人和不支持 skill 的 agent 看的概览与指针，权威细节在本目录。
- 他人安装：`skill-installer` 用 `--repo Luke-Evan/videobook --path skills/videobook`；
  或 clone 后把本目录复制/软链到 `~/.codex/skills/`（仅 Codex）或 `~/.agents/skills/`（跨 agent）。