# 第三步：截帧并把占位符物化为图片

画面必须**直接来自平台播放器、使用已登录账号的高画质**；本步任何方式都不得下载视频 / 音频文件（铁律 2）。
按优先级执行，**上一级全部失败才进入下一级**。

## 优先级 0（桌面环境首选）：Chrome 扩展 @Chrome

仅当运行在 Codex / ChatGPT 桌面应用内、且 ChatGPT 浏览器扩展已安装并连接时使用（在 设置 > Computer Use 中确认）。

- 通过扩展控制用户真实、已登录的 Chrome：对 `book.md`（或 `book.tagged.md`）里每个 `SCREENSHOT:` 时间戳，
  打开对应平台播放器页面，等视频画面渲染后对该标签页截图，保存为 `output/<video_id>/images/shot_HH_MM_SS.png`。
  - B 站播放器地址：`https://player.bilibili.com/player.html?bvid=<video_id>&t=<秒>&autoplay=1&high_quality=1&danmaku=0`
  - YouTube 播放器地址：`https://www.youtube.com/embed/<video_id>?start=<秒>&autoplay=1&high_quality=1`
- 特点：使用登录态画质、后台运行、不接管用户屏幕。
- 全部时间戳截完后执行物化：`python src/capture_frames.py <video_id> --materialize-only`。
- 扩展未连接、截图失败、或运行环境不是桌面应用时 → 进入优先级 1。

## 优先级 1：专用截帧配置（v2 管线，所有 agent 环境通用）

Chrome 136+ 的安全策略禁止对**默认**用户数据目录做任何远程调试，所以脚本改用专用数据目录
（默认仓库根目录下的 `.capture-profile/`）：既不与主 Chrome 冲突，也不受调试禁令限制。

一次性初始化（登录一次，长期复用）：

```bash
python src/capture_frames.py --setup-profile
```

在弹出的 Chrome 窗口里登录需要的平台（B 站 / YouTube），然后关闭窗口。cookies 持久化在 `.capture-profile/`，
此后截帧自动携带登录态画质。**登录账号的会员等级决定截图清晰度上限。**

日常截帧（启动 Chrome，**需沙箱外执行**）：

```bash
python src/capture_frames.py <video_id> "<VIDEO_URL>"
```

v2 管线自动完成下面这些，agent 无需也不应手工干预：

- **无头运行**：默认 headless 不弹窗打扰用户，失败自动回退有头模式；
- **权益探针**：抓前查询该账号 / 该视频的顶档原生分辨率，viewport 按 1:1 设置（不放大、不糊，换账号换视频自动适配）；
- **流锁定**：路由拦截 playurl 响应，强制首帧即拉顶档最高码率流（根除「自动档从 360P 起播、暂停冻结升档」造成的糊图）；
- **纯净帧**：用 visibility CSS 隐藏全部播放器 UI（顶栏 / 控制栏 / 引流条 / 暂停推荐层），只对 `<video>` 元素截图，无黑边；
  嵌入播放器优先，失败自动降级到主站观看页；
- **精确帧**：`seek(目标秒)` → 等 `seeked` → `pause` 后截图，时间戳精确且为静止帧；
- **QA 自检**：截图文件过小判为黑帧，自动偏移重试；**只截缺失帧**，全部存在时直接跳过；
- **增量友好**：占位符清单始终读自 `book.tagged.md`（若存在），因此物化后重跑也能正确补帧。

其他：更换配置目录用 `--profile-dir <path>`；截图变回未登录态（cookie 过期）就重新执行 `--setup-profile` 登录一次。

**Agent QA 习惯**：截帧后抽查 1–2 张图（一张幻灯片帧、一张演示帧）确认清晰、无 UI 遮挡。
若整体发糊，通常是账号档位问题 —— 请用户在专用配置里登录大会员账号后重跑本命令，管线会自动按新档位原生分辨率重截。

## 优先级 2（兜底）：下载视频源 + ffmpeg 抽帧

仅当上述所有浏览器方式全部失败（`capture_frames.py` 以非零码退出并提示 "All browser capture methods failed"），
或环境无浏览器 / 无界面时：

```bash
python src/extract_frames.py <video_id> "<VIDEO_URL>"
```

- `output/<video_id>/video_source.mp4` 不存在时，脚本自动用 yt-dlp 下载**未登录可用的最高 avc1 档**；
  注意这是未登录画质，仅作兜底。需要更高清晰度时，先自行下载（如带登录 cookies）同名文件放进去，脚本会跳过下载。
- 兜底产生的 `video_source.mp4` 属于大媒体文件：流程中途可保留，流程结束时按铁律 9 询问用户是否删除。

## 明确排除的方式（不要用）

- 内置浏览器（@Browser）：独立配置文件，默认没有平台登录态，不满足高画质要求。
- Playwright 自带的干净 Chromium：无登录态。
- 对主 Chrome 默认数据目录的任何远程调试（CDP 端口 / Playwright 管道）：Chrome 136+ 安全策略禁止，永不生效。
- win32 屏幕截取：会接管用户屏幕，已从脚本中移除。
- `--cookies-from chrome` 读主 Chrome：Windows 上 Chrome 新版 App-Bound 加密使 yt-dlp 无法解密，不要默认使用。

## 有 course/ 时：把糊帧升级为官方 4K 幻灯片

截帧之后执行，见 `course-assets.md` 的「截帧后升级」一节（`--match-shots` → 抽查 → `--apply-map`）。

## 完成标志

- `images/` 下每个时间戳都有对应的 `shot_HH_MM_SS.png`，`book.md` 中不再有 `SCREENSHOT:` 占位符
  （原标签稿已自动备份为 `book.tagged.md`）。
- 第四步生成的 HTML 中，截图卡片内置点击放大（lightbox）：点击图片看大图，点空白处或按 Esc 关闭。