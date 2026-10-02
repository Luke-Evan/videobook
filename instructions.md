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
python src/dump_transcript.py "<VIDEO_URL>"
```

- 脚本会自动检测平台，抓取字幕并保存为 `output/<video_id>/transcript.json`。
- **B 站登录态自动获取**：B 站视频在专用配置 `.capture-profile/` 存在登录态时，脚本会自动导出 cookies（系统临时目录、用完即删，不会落入仓库）。该过程启动无头 Chrome，**需沙箱外执行**（Codex 中申请 require_escalated）。
- 若提示专用配置无登录态：请用户先运行 `python src/capture_frames.py --setup-profile` 登录一次（扫码即可），再重试。
- 可选参数：`--cookies-from-profile <dir>`（指定配置导出）、`--cookies-file <path>`（Netscape cookies 文件）、`--cookies-from <browser>`（旧方式；Windows 主 Chrome 因新版加密通常不可用，勿默认使用）。
- **覆盖率自检**：成功时脚本打印"字幕覆盖率"（末段结束时间 / 视频时长）。覆盖率低于 50% 会以退出码 3 结束并打印修复提示——此时不得进入第二步，先按提示解决（通常是登录态问题）。
- **transcript.json 结构**：除 `segments` 外，现含 `duration`（总时长秒）与 `chapters`（平台官方章节切分，可能为空数组）。第二步必须利用这两个字段。
- **区分两类失败**：
  - *登录态 / 代理问题*（覆盖率过低、超时、地区限制）：按上面提示修复后重跑本步。
  - *平台确实没有字幕*：`--list-subs` 只有 `danmaku`、播放器接口 `subtitle.subtitles` 为 `[]`（新上传视频常见，B 站 AI 字幕尚未生成）。此时**不要停止流程**，转入下面的本地 ASR 兜底。
- 如果失败且无法兜底，请告知用户可能的原因（无字幕、需要代理、需要登录等），并停止流程。海外视频终端需走代理。

#### 兜底：本地 ASR 转写（平台无任何字幕时）

```bash
python src/asr_transcript.py <video_id>
```

- 脚本自行完成：只下载音频轨（`output/<id>/audio.m4a`，不下载视频流）→ faster-whisper `large-v3` 转写 → 按标点/时长切成接近平台字幕粒度的短段 → 写出 `transcript.json`（字段与 `scraper.get_transcript` 完全同构：`video_url / title / video_id / duration / chapters / segments`）与 `transcript.txt`。因此第二步之后的所有步骤无需任何改动。
- **先试跑再全量**：`--sample-start 900 --sample-dur 180` 转写 3 分钟抽样，确认质量与速度后再跑全量。
- **领域术语提示**：在 `output/<id>/_asr_prompt.txt` 写入本讲主题与术语（一两百字即可，Whisper 的 prompt 上限约 224 token，过长会被截断）。它能显著压制同音错词，并让中文输出自带标点。**PowerShell 下不要用命令行传含中文引号的长 prompt**（弯引号会被当成字符串定界符），一律走文件。
- **算力**：有 NVIDIA 显卡自动用 CUDA，显存 ≤4GB 用 `--compute-type int8_float16`；无卡自动退 CPU int8。Windows 报 `Library cublas64_12.dll is not found` 时装 `nvidia-cublas-cu12 nvidia-cudnn-cu12`，脚本已自动注册这些 DLL 目录。
- **断点续跑**：进度实时写入 `output/<id>/_asr_progress.jsonl`，中断后重跑自动从末尾续接；`--restart` 强制从头（试跑后跑全量务必带上，否则会漏掉试跑区间之前的内容）。
- **耗时预期**：100 分钟课程在 RTX 3050 (4GB) 上约 35 分钟；期间可并行准备第三步的截帧环境与术语表。
- 转写完成后，仍要执行覆盖率自检（脚本已内置），低于 50% 说明没跑完，重跑续写。

### 第 1.5 步（增强）：抓取课程官方资料（若视频属于有公开主页的课程）

不少课程在录像之外还维护自己的课程主页（讲义 + 幻灯片课件，如 `https://jyywiki.cn/GSE/2026/`）：
讲义是讲师本人的书面描述（权威术语、章节骨架、参考链接），幻灯片则可渲染成 4K 图片，比任何视频帧都清晰。
先确认该课程是否有主页（用户给出或自行搜索课程名），有则执行：

```bash
python src/course_assets.py <video_id> --course-url <课程主页> [--lecture N]
```

- 按视频标题自动匹配讲次（不匹配时用 `--list` 查看讲次表、`--lecture N` 手工指定）；
- 产出 `output/<video_id>/course/`：`*.notes.md`（讲义 Markdown）、`slides_text.md`（每页幻灯片标题+要点）、
  `slides/slide_NNN.png`（4K 渲染图），并把 `book.md` 里的 `![...](SLIDE:n@HH:MM:SS)` 占位符物化为官方图；
- 渲染幻灯片要启动 headless Chrome，**需沙箱外执行**；只抓取不渲染（`--no-render`）沙箱内即可；
- **幻灯片覆盖铁律**：官方幻灯片的 **每一页** 都必须在 `book.md` 中 **恰好出现一次**。交稿前自检：

  ```bash
  python src/course_assets.py <video_id> --audit            # 有重复/遗漏即以退出码 1 结束
  python src/course_assets.py <video_id> --locate-slides    # 抽样视频，定位每页幻灯片的首次出现时间（截帧，需沙箱外）
  python src/course_assets.py <video_id> --weave            # 自动修复：重复图去重保留首次、缺失页按首现时间插入对应小节、课堂未展示的页进附录；修复后自动复审
  ```

- 课程没有主页就跳过本步，后续流程完全不变。

本步建议在**第二步生成 book.md 之后、第三步截帧之前**执行：SLIDE 占位符先被物化，
`capture_frames.py` 只会补拍剩下的 SCREENSHOT 帧（它本来就只截缺失帧）。

### 第二步：阅读字幕 + 生成电子书

1. 阅读生成的 `output/<video_id>/transcript.json` 文件。
2. 若 `output/<video_id>/course/` 存在，先读 `course/*.notes.md` 与 `course/slides_text.md`：
   术语校准、章节骨架对齐、参考链接收集，规则见 `prompts/stitcher_system.md` 的"课程官方资料"一节。
3. 阅读 `prompts/stitcher_system.md` 获取排版指令。
4. 按照 Stitcher Prompt 的要求，将字幕重构为结构化的 Markdown 技术指南。
5. 将生成的内容写入 `output/<video_id>/book.md`。
6. 若 `course/` 存在：交稿前跑 `python src/course_assets.py <video_id> --audit`，必须 PASS（见第 1.5 步"幻灯片覆盖铁律"）。

**关键要求：**
- 必须将口语化内容转为书面化技术语言
- 必须分章节组织，使用 Markdown 标题
- 必须在关键界面/操作步骤处插入截图占位符：`![场景描述](SCREENSHOT:HH:MM:SS)`
- 如果原始语言不是中文，必须翻译为中文
- **官方章节仅供参考**：`chapters` 字段往往较粗糙，只用于辅助定位内容与选择截图时间戳；顶层分章请按内容自身逻辑组织，**不要求**与官方章节一一对应；`SCREENSHOT:` 时间戳落在其所属内容的时间区间内即可。
- **容忍 ASR 噪声**：AI 字幕含同音错词（如"深圳市软件工程"→生成式、"威尔法/WIFI"→verifier、"KIMIK3"→Kimi K3、"chain of salt"→chain of thought、"舔狗/做题家"等口语梗保留原意）。动笔前先结合标题与 chapters 建立术语表，改写时统一规范化。
- **产出修正版字幕对照稿**：运行 `python src/make_corrected.py <video_id>`（或 `--all`）生成 `output/<video_id>/transcript.corrected.txt`；**重跑保护**：该文件已存在时脚本会拒绝覆盖（防止抹掉后续的人工/AI 行级订正），确需重跑加 `--force`，叠加新校订用 `--edits <corrections.json>`——与 transcript.txt 同格式（`[HH:MM:SS] 原文`、逐段不合并），**保留讲师原始字词与顺序**，仅做两类修改：ASR 错词替换（脚本内 MAP，按视频扩充）与口癖清理（纯语气词段删除、句尾语气词剥离、单字口吃折叠）；不改写为书面语、不概括；随后由 AI 通读全文做一轮行级订正（仅修明显错词/截断词/不通顺处，保留逐段结构与讲师原词，可委派子代理产出 old->new 清单后脚本应用；订正原则：少识别字词类错误（如“车轱话”→“车轱辘话”）必修，讲师有意为之的强调式重复（如“工作工作工作工作”“点点点点点点点了十层”）原样保留、不得折叠）；生成后抽查若干行确认无过改；该文件随发布上传 pages 供人工对照视频。
- **截图时间戳选择**：优先章节边界、新幻灯片出现时刻、演示画面时刻；结合前后字幕语义定位，格式 `HH:MM:SS`。

### 第三步：截帧并将截图占位符替换为图片

画面必须直接来自平台播放器、使用已登录账号的高画质；本步任何方式都不得下载视频/音频文件。按以下优先级执行，**上一级全部失败才进入下一级**。

#### 优先级 0（桌面环境首选）：Chrome 扩展（@Chrome）

仅当运行在 Codex/ChatGPT 桌面应用内、且 ChatGPT 浏览器扩展已安装并连接时使用（在 设置 > Computer Use 中确认）：

- 通过扩展控制用户真实、已登录的 Chrome：逐个 `SCREENSHOT:` 时间戳（取自 `book.md` 或 `book.tagged.md`），在 Chrome 中打开对应平台播放器页面，等待视频画面渲染后对该标签页截图，保存为 `output/<video_id>/images/shot_HH_MM_SS.png`。
  - B 站播放器地址：`https://player.bilibili.com/player.html?bvid=<video_id>&t=<秒>&autoplay=1&high_quality=1&danmaku=0`
  - YouTube 播放器地址：`https://www.youtube.com/embed/<video_id>?start=<秒>&autoplay=1&high_quality=1`
- 特点：使用登录态画质、后台运行、不接管用户屏幕。
- 全部时间戳截完后执行物化：`python src/capture_frames.py <video_id> --materialize-only`。
- 扩展未连接、截图失败、或运行环境不是 Codex/ChatGPT 桌面应用时，进入优先级 1。

#### 优先级 1：专用截帧配置（v2 管线，所有 Agent 环境通用）

Chrome 136+ 的安全策略禁止对**默认**用户数据目录做任何远程调试，因此脚本改用专用数据目录（默认仓库根目录下 `.capture-profile/`）：不与主 Chrome 冲突，也不受调试禁令限制。

**一次性初始化（登录一次，长期复用）：**

```bash
python src/capture_frames.py --setup-profile
```

- 脚本会用专用配置启动一个 Chrome 窗口：在其中登录你需要的平台（B 站 / YouTube），然后关闭窗口。Cookies 持久化在 `.capture-profile/`，此后截帧自动携带登录态画质。**登录账号的会员等级决定截图清晰度上限**（需要更高档位时用大会员账号登录）。

**日常截帧：**

```bash
python src/capture_frames.py <video_id> "<VIDEO_URL>"
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
python src/extract_frames.py <video_id> "<VIDEO_URL>"
```

- 若 `output/<video_id>/video_source.mp4` 不存在，脚本会自动用 yt-dlp 下载未登录可用的最高 avc1 档；注意这是未登录画质，仅作兜底。需要更高清晰度时，先自行下载（如带登录 cookies）同名文件，脚本会跳过下载。
- 兜底产生的 `video_source.mp4` 属于大媒体文件：流程中途可保留，流程结束时按第五步询问用户是否删除。

#### 明确排除的方式（不要使用）

- 内置浏览器（@Browser）：独立配置文件，默认没有平台登录态，不满足高画质要求。
- Playwright 自带的干净 Chromium：无登录态。
- 对主 Chrome 默认数据目录的任何远程调试（CDP 端口 / Playwright 管道）：Chrome 136+ 安全策略禁止，永不生效。
- win32 屏幕截取：接管用户屏幕，已从脚本中移除。
- `--cookies-from chrome` 读取主 Chrome：Windows 上 Chrome 新版 App-Bound 加密使 yt-dlp 无法解密，不要默认使用。

#### 官方幻灯片升级（course/ 存在时，截帧后执行）

```bash
python src/course_assets.py <video_id> --course-url <课程主页> --match-shots --no-render
```

脚本把每张 `images/shot_*.png` 与官方幻灯片渲染图做感知哈希比对，打印候选（distance 越小越像，
≤55 通常是"画面即幻灯片"，>60 基本是演示/板书帧）。Agent 抽查确认后，把确认结果写成
`{"shot_00_00_55": 1, ...}`（值 = 幻灯片编号）的 json，再执行：

```bash
python src/course_assets.py <video_id> --apply-map <json路径>
```

糊帧即被替换为 4K 官方渲染图，原视频帧自动备份到 `images/video_frames/`。
**校验技巧**：讲师按顺序翻页，匹配出的幻灯片编号沿时间轴应单调不减；出现乱序的候选基本是误匹配。
最后重跑第四步 `post_process.py` 生成新 HTML。

#### 完成标志

- `images/` 下每个时间戳都有对应的 `shot_HH_MM_SS.png`，`book.md` 中不再有 `SCREENSHOT:` 占位符。
- 第四步生成的 HTML 中，截图卡片内置点击放大（lightbox）：点击图片查看大图，点击空白处或按 Esc 关闭。

### 第四步：转换 HTML + 启动预览

在终端依次执行以下命令（纯本地步骤，沙箱内即可）：

```bash
python src/post_process.py "<VIDEO_URL>" output/<video_id>/book.md
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
6. 若本讲用了课程官方资料：说明书中幻灯片插图为官方 4K 渲染图（书首信息块已注明来源与 CC 许可），演示帧仍为视频帧；`course/` 目录可整体删除不影响阅读。


### 第六步（可选）：发布成品到 pages 分支

```bash
python src/publish.py <video_id>   # 或 python src/publish.py --all
git push origin pages
```

- 将 book.html / book.md / images/ 以及（若存在）transcript.corrected.txt（AI 修正版字幕对照稿）提交到独立 orphan 分支 `pages`，目录名 = 视频标题；落地页卡片对含对照稿的书自动附"字幕对照"入口；不触碰 `output/` 与 main 工作区；内容无变化时自动跳过提交。
- 纯本地 git 操作，沙箱内可跑；push 需网络。
- 首次推送后需在 GitHub 仓库 Settings → Pages 一次性启用（分支 `pages`、目录 `/ (root)`），之后每次 push 自动部署。


## 注意事项

- 工作目录始终为本仓库根目录（即本文件所在目录），所有相对路径（如 `output/<video_id>/...`）均相对于它解析
- 所有 Python 命令使用 `python` 执行（不要用 `pip`，用 `python -m pip`）；本仓库若用 uv 管理则用 `.venv\Scripts\python.exe` 或 `uv run python`
- **ASR 兜底稿同样是"原始字幕"**：`asr_transcript.py` 产出的 `transcript.json` 在后续步骤中与平台字幕完全等价，同样需要建立术语表、容忍同音错词、产出 `transcript.corrected.txt`。本地 large-v3 的错词率通常低于平台 AI 字幕，但仍需人工订正专有名词。
- 所有外部工具（yt-dlp）通过 `sys.executable -m yt_dlp` 调用
- **YouTube 要两头代理**：终端不走代理抓不到字幕与源信息；读者的浏览器不走全局代理，成书里的 YouTube iframe 会黑块裂图并报「视频配置错误 (153)」——这不是脚本问题，交付时要主动提醒用户
- **预览必须走本地 HTTP 服务**：用 `file://` 双击打开 `book.html` 时，跨域与 Cookie 隐私策略会让内嵌播放器拒载报错，所以第四步固定用 `python -m http.server`，不要建议用户直接双击打开文件
- **沙箱/提权**：启动 Chrome / 读取浏览器 cookie 库的命令必须沙箱外执行：`dump_transcript.py`（B 站）、`capture_frames.py`、`capture_frames.py --setup-profile`；`post_process.py`、`http.server` 沙箱内即可。在 Codex 中对应 require_escalated 审批。
- **cookies 安全**：自动导出的 cookies 写入系统临时目录、用完即删；不要在仓库里手放 cookies.txt（已被 .gitignore 忽略，但仍应避免）。
- **课程资料依赖**：`course_assets.py` 的抓取/解析沙箱内可跑；渲染幻灯片启动 headless Chrome，需沙箱外执行；图像哈希匹配依赖 Pillow（已在 requirements.txt）。课程讲义/幻灯片版权归讲师所有（常见 CC BY-NC），生成物必须保留署名与许可说明（stitcher prompt 已强制）。
- **可重跑性**：流水线各步幂等。若 `output/<video_id>` 被意外清理：重跑第一步恢复字幕；只要 `book.tagged.md` 还在，重跑第三步即可恢复截图（占位符清单读自 tagged 稿）。
- 在生成或修改 HTML 时，请确保文本颜色与背景颜色的对比度符合 WCAG AA 标准（对比度至少 4.5:1）。
