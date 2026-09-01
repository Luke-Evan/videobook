# VideoBook Agent 工作流指令

> 本文件是 AI 助手（Antigravity / Claude Code）的操作手册。
> 当用户发来一个视频链接时，请严格按照以下步骤执行。

## 触发条件

用户发来一条包含 YouTube (`youtube.com`, `youtu.be`) 或 B站 (`bilibili.com`) 视频链接的消息，
并表示希望将其生成为电子书/教程/指南。

## 完整工作流

### 第一步：提取字幕

在终端执行以下命令（将 `<VIDEO_URL>` 替换为用户提供的链接）：

```bash
python dump_transcript.py "<VIDEO_URL>"
```

- 脚本会自动检测平台，抓取字幕并保存为 `output/<video_id>/transcript.json`。
- 如果失败，请告知用户可能的原因（无字幕、需要代理、需要 Cookie 等），并停止流程。

### 第二步：阅读字幕 + 生成电子书

1. 阅读生成的 `output/<video_id>/transcript.json` 文件。
2. 阅读 `prompts/stitcher_system.md` 获取排版指令。
3. 按照 Stitcher Prompt 的要求，将字幕重构为结构化的 Markdown 技术指南。
4. 将生成的内容写入 `output/<video_id>/book.md`。

**关键要求：**
- 必须将口语化内容转为书面化技术语言
- 必须分章节组织，使用 Markdown 标题
- 必须在关键界面/操作步骤处插入截图占位符：`![场景描述](SCREENSHOT:HH:MM:SS)`
- 如果原始语言不是中文，必须翻译为中文

### 第三步：截帧并将截图占位符替换为图片

画面必须直接来自平台播放器、使用已登录账号的高画质；本步任何方式都不得下载视频/音频文件。按以下优先级执行，**上一级全部失败才进入下一级**。

#### 优先级 0（桌面环境首选）：Chrome 扩展（@Chrome）

仅当运行在 Codex/ChatGPT 桌面应用内、且 ChatGPT 浏览器扩展已安装并连接时使用（在 设置 > Computer Use 中确认）：

- 通过扩展控制用户真实、已登录的 Chrome：逐个 `SCREENSHOT:` 时间戳（取自 `book.md` 或 `book.tagged.md`），在 Chrome 中打开对应平台播放器页面，等待视频画面渲染后对该标签页截图，保存为 `output/<video_id>/images/shot_HH_MM_SS.png`。
  - B 站播放器地址：`https://player.bilibili.com/player.html?bvid=<video_id>&t=<秒>&autoplay=1&high_quality=1&danmaku=0`
  - YouTube 播放器地址：`https://www.youtube.com/embed/<video_id>?start=<秒>&autoplay=1`
- 特点：使用登录态画质、后台运行、不接管用户屏幕。
- 全部时间戳截完后执行物化：`python capture_frames.py <video_id> --materialize-only`。
- 扩展未连接、截图失败、或运行环境不是 Codex/ChatGPT 桌面应用时，进入优先级 1。

#### 优先级 1：专用截帧配置（独立 Chrome 数据目录 + 一次性登录，所有 Agent 环境通用）

Chrome 136+ 的安全策略禁止对**默认**用户数据目录做任何远程调试（调试端口与 Playwright 管道均被禁止），因此脚本改用专用数据目录（默认仓库根目录下 `.capture-profile/`）：不与主 Chrome 冲突（两者可同时运行），也不受调试禁令限制。

**一次性初始化（登录一次，长期复用，已完成）：**

```bash
python capture_frames.py --setup-profile
```

- 脚本会用专用配置启动一个 Chrome 窗口：在其中登录你需要的平台（B 站 / YouTube），然后关闭窗口。Cookie 持久化在 `.capture-profile/`，此后截帧自动携带登录态画质。

**日常截帧：**

```bash
python capture_frames.py <video_id> "<VIDEO_URL>"
```

- Playwright 以有头模式启动专用配置，逐个时间戳打开平台播放器页面并截图到 `images/`；截取期间会临时弹出 Chrome 窗口，任务结束自动关闭，不影响你日常使用的主 Chrome。
- 更换配置目录：`--profile-dir <path>`。
- 若发现截图变成未登录状态（Cookie 过期、平台要求重新验证），重新执行 `--setup-profile` 登录一次即可。

#### 兜底：下载视频源 + ffmpeg 抽帧

仅当上述所有浏览器方式全部失败（`capture_frames.py` 以非零码退出并提示 "All browser capture methods failed"），或环境无浏览器/无界面时：

```bash
python extract_frames.py <video_id> "<VIDEO_URL>"
```

- 若 `output/<video_id>/video_source.mp4` 不存在，脚本会自动用 yt-dlp 下载未登录可用的最高 avc1 档；注意这是未登录画质，仅作兜底。需要更高清晰度时，先自行下载（如带登录 cookies）同名文件，脚本会跳过下载。
- 兜底产生的 `video_source.mp4` 属于大媒体文件：流程中途可保留，流程结束时按第五步询问用户是否删除。

#### 明确排除的方式（不要使用）

- 内置浏览器（@Browser）：独立配置文件，默认没有平台登录态，不满足高画质要求。
- Playwright 自带的干净 Chromium：无登录态。
- 对主 Chrome 默认数据目录的任何远程调试（CDP 端口 / Playwright 管道）：Chrome 136+ 安全策略禁止，永不生效。
- win32 屏幕截取：接管用户屏幕，已从脚本中移除。

#### 完成标志

- `images/` 下每个时间戳都有对应的 `shot_HH_MM_SS.png`，`book.md` 中不再有 `SCREENSHOT:` 占位符。
- 第四步生成的 HTML 中，截图卡片内置点击放大（lightbox）：点击图片查看大图，点击空白处或按 Esc 关闭。

### 第四步：转换 HTML + 启动预览

在终端依次执行以下命令：

```bash
python post_process.py "<VIDEO_URL>" output/<video_id>/book.md
python -m http.server 8080 --directory output/<video_id>
```

### 第五步：告知用户

将以下信息回复给用户：

1. ✅ 电子书 Markdown 文件位置：`output/<video_id>/book.md`
2. ✅ HTML 电子书预览地址：**http://localhost:8080/book.html**
3. 提醒用户：
   - 如果是 YouTube 视频，请确保浏览器可以访问 YouTube（需要代理）
   - 如果是 B 站视频，可以直接访问
   - 关闭预览服务器：在终端按 `Ctrl+C`
4. 若流程中产生过大媒体文件（如 `output/<video_id>/video_source.mp4`、`audio.m4a`），询问用户是否需要删除，得到确认后再删。

## 注意事项

- 工作目录始终为本仓库根目录（即本文件所在目录），所有相对路径（如 `output/<video_id>/...`）均相对于它解析
- 所有 Python 命令使用 `python` 执行（不要用 `pip`，用 `python -m pip`）
- 所有外部工具（yt-dlp）通过 `sys.executable -m yt_dlp` 调用
- 如果用户提供的是 YouTube 链接且终端无代理，字幕抓取可能会失败
- 在生成或修改 HTML 时，请确保文本颜色与背景颜色的对比度符合 WCAG AA 标准（对比度至少 4.5:1）。
