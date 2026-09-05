# VideoBook Agent 工作流指令

> 本文件是 AI 助手（Codex / Antigravity / Claude Code）的操作手册。
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
- **B 站登录态自动获取**：B 站视频在专用配置 `.capture-profile/` 存在登录态时，脚本会自动导出 cookies（系统临时目录、用完即删，不会落入仓库）。该过程启动无头 Chrome，**需沙箱外执行**（Codex 中申请 require_escalated）。
- 若提示专用配置无登录态：请用户先运行 `python capture_frames.py --setup-profile` 登录一次（扫码即可），再重试。
- 可选参数：`--cookies-from-profile <dir>`（指定配置导出）、`--cookies-file <path>`（Netscape cookies 文件）、`--cookies-from <browser>`（旧方式；Windows 主 Chrome 因新版加密通常不可用，勿默认使用）。
- **覆盖率自检**：成功时脚本打印"字幕覆盖率"（末段结束时间 / 视频时长）。覆盖率低于 50% 会以退出码 3 结束并打印修复提示——此时不得进入第二步，先按提示解决（通常是登录态问题）。
- **transcript.json 结构**：除 `segments` 外，现含 `duration`（总时长秒）与 `chapters`（平台官方章节切分，可能为空数组）。第二步必须利用这两个字段。
- 如果失败，请告知用户可能的原因（无字幕、需要代理、需要登录等），并停止流程。海外视频终端需走代理。

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
- **官方章节仅供参考**：`chapters` 字段往往较粗糙，只用于辅助定位内容与选择截图时间戳；顶层分章请按内容自身逻辑组织，**不要求**与官方章节一一对应；`SCREENSHOT:` 时间戳落在其所属内容的时间区间内即可。
- **容忍 ASR 噪声**：AI 字幕含同音错词（如"深圳市软件工程"→生成式、"威尔法/WIFI"→verifier、"KIMIK3"→Kimi K3、"chain of salt"→chain of thought、"舔狗/做题家"等口语梗保留原意）。动笔前先结合标题与 chapters 建立术语表，改写时统一规范化。
- **产出修正版字幕对照稿**：运行 `python make_corrected.py <video_id>`（或 `--all`）生成 `output/<video_id>/transcript.corrected.txt`——与 transcript.txt 同格式（`[MM:SS] 原文`、逐段不合并），**保留讲师原始字词与顺序**，仅做两类修改：ASR 错词替换（脚本内 MAP，按视频扩充）与口癖清理（纯语气词段删除、句尾语气词剥离、单字口吃折叠）；不改写为书面语、不概括；随后由 AI 通读全文做一轮行级订正（仅修明显错词/截断词/不通顺处，保留逐段结构与讲师原词，可委派子代理产出 old->new 清单后脚本应用）；生成后抽查若干行确认无过改；该文件随发布上传 pages 供人工对照视频。
- **截图时间戳选择**：优先章节边界、新幻灯片出现时刻、演示画面时刻；结合前后字幕语义定位，格式 `HH:MM:SS`。

### 第三步：截帧并将截图占位符替换为图片

画面必须直接来自平台播放器、使用已登录账号的高画质；本步任何方式都不得下载视频/音频文件。按以下优先级执行，**上一级全部失败才进入下一级**。

#### 优先级 0（桌面环境首选）：Chrome 扩展（@Chrome）

仅当运行在 Codex/ChatGPT 桌面应用内、且 ChatGPT 浏览器扩展已安装并连接时使用（在 设置 > Computer Use 中确认）：

- 通过扩展控制用户真实、已登录的 Chrome：逐个 `SCREENSHOT:` 时间戳（取自 `book.md` 或 `book.tagged.md`），在 Chrome 中打开对应平台播放器页面，等待视频画面渲染后对该标签页截图，保存为 `output/<video_id>/images/shot_HH_MM_SS.png`。
  - B 站播放器地址：`https://player.bilibili.com/player.html?bvid=<video_id>&t=<秒>&autoplay=1&high_quality=1&danmaku=0`
  - YouTube 播放器地址：`https://www.youtube.com/embed/<video_id>?start=<秒>&autoplay=1&high_quality=1`
- 特点：使用登录态画质、后台运行、不接管用户屏幕。
- 全部时间戳截完后执行物化：`python capture_frames.py <video_id> --materialize-only`。
- 扩展未连接、截图失败、或运行环境不是 Codex/ChatGPT 桌面应用时，进入优先级 1。

#### 优先级 1：专用截帧配置（v2 管线，所有 Agent 环境通用）

Chrome 136+ 的安全策略禁止对**默认**用户数据目录做任何远程调试，因此脚本改用专用数据目录（默认仓库根目录下 `.capture-profile/`）：不与主 Chrome 冲突，也不受调试禁令限制。

**一次性初始化（登录一次，长期复用）：**

```bash
python capture_frames.py --setup-profile
```

- 脚本会用专用配置启动一个 Chrome 窗口：在其中登录你需要的平台（B 站 / YouTube），然后关闭窗口。Cookies 持久化在 `.capture-profile/`，此后截帧自动携带登录态画质。**登录账号的会员等级决定截图清晰度上限**（需要更高档位时用大会员账号登录）。

**日常截帧：**

```bash
python capture_frames.py <video_id> "<VIDEO_URL>"
```

v2 管线自动完成以下事情，Agent 无需也不应手工干预：

- **无头运行**：默认 headless 不弹窗打扰用户，失败自动回退有头模式；
- **权益探针**：抓前查询该账号/该视频的顶档原生分辨率，viewport 按 1:1 设置（不放大、不糊；换账号/换视频自动适配）；
- **流锁定**：路由拦截 playurl 响应，强制首帧即拉顶档最高码率流（根除"自动档从 360P 起播、暂停冻结升档"造成的糊图）；
- **纯净帧**：visibility CSS 隐藏全部播放器 UI（顶栏/控制栏/引流条/暂停推荐层），仅对 `<video>` 元素截图，无黑边；嵌入播放器优先，失败自动降级主站观看页；
- **精确帧**：`seek(目标秒) → 等 seeked → pause` 后截图，时间戳精确且为静止帧；
- **QA 自检**：截图文件过小判为黑帧，自动偏移重试；**只截缺失帧**，全部存在时直接跳过；
- **增量友好**：占位符清单始终读自 `book.tagged.md`（若存在），因此物化后重跑也能正确补帧。

本步启动 Chrome，**需沙箱外执行**。更换配置目录：`--profile-dir <path>`。若截图变回未登录态（Cookie 过期），重新执行 `--setup-profile` 登录一次。

**Agent QA 习惯**：截帧后抽查 1–2 张图（一张幻灯片帧、一张演示帧）确认清晰无遮挡。若整体发糊，通常是账号档位问题——请用户在专用配置里登录大会员账号后重跑本命令（管线会自动按新档位原生分辨率重截）。

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
- `--cookies-from chrome` 读取主 Chrome：Windows 上 Chrome 新版 App-Bound 加密使 yt-dlp 无法解密，不要默认使用。

#### 完成标志

- `images/` 下每个时间戳都有对应的 `shot_HH_MM_SS.png`，`book.md` 中不再有 `SCREENSHOT:` 占位符。
- 第四步生成的 HTML 中，截图卡片内置点击放大（lightbox）：点击图片查看大图，点击空白处或按 Esc 关闭。

### 第四步：转换 HTML + 启动预览

在终端依次执行以下命令（纯本地步骤，沙箱内即可）：

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
5. 截图清晰度说明：截图为当前账号顶档的纯视频帧（非大会员通常为 720P）；如需更高清晰度，在专用配置窗口登录大会员账号后重跑 `capture_frames.py <video_id> <url>` 即可自动升级。

## 注意事项

- 工作目录始终为本仓库根目录（即本文件所在目录），所有相对路径（如 `output/<video_id>/...`）均相对于它解析
- 所有 Python 命令使用 `python` 执行（不要用 `pip`，用 `python -m pip`）
- 所有外部工具（yt-dlp）通过 `sys.executable -m yt_dlp` 调用
- 如果用户提供的是 YouTube 链接且终端无代理，字幕抓取可能会失败
- **沙箱/提权**：启动 Chrome / 读取浏览器 cookie 库的命令必须沙箱外执行：`dump_transcript.py`（B 站）、`capture_frames.py`、`capture_frames.py --setup-profile`；`post_process.py`、`http.server` 沙箱内即可。在 Codex 中对应 require_escalated 审批。
- **cookies 安全**：自动导出的 cookies 写入系统临时目录、用完即删；不要在仓库里手放 cookies.txt（已被 .gitignore 忽略，但仍应避免）。
- **可重跑性**：流水线各步幂等。若 `output/<video_id>` 被意外清理：重跑第一步恢复字幕；只要 `book.tagged.md` 还在，重跑第三步即可恢复截图（占位符清单读自 tagged 稿）。
- 在生成或修改 HTML 时，请确保文本颜色与背景颜色的对比度符合 WCAG AA 标准（对比度至少 4.5:1）。

### 第六步（可选）：发布成品到 pages 分支

`ash
python publish.py <video_id>   # 或 python publish.py --all
git push origin pages
`

- 将 book.html / book.md / images/ 以及（若存在）transcript.corrected.txt（AI 修正版字幕对照稿）提交到独立 orphan 分支 `pages`，目录名 = 视频标题；落地页卡片对含对照稿的书自动附"字幕对照"入口；不触碰 `output/` 与 main 工作区；内容无变化时自动跳过提交。
- 纯本地 git 操作，沙箱内可跑；push 需网络。
- 首次推送后需在 GitHub 仓库 Settings → Pages 一次性启用（分支 `pages`、目录 `/ (root)`），之后每次 push 自动部署。
