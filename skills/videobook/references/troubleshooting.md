# 排错速查

## YouTube 字幕抓不到 / 页面里 iframe 报「视频配置错误 (153)」

不是脚本问题，是网络审查与封锁。处理海外视频必须两头都代理：

- **终端走代理**：底层基于第三方库爬取时，才能拿到字幕和源信息。
- **浏览器走全局代理**：生成的 HTML 里 YouTube iframe 是读者本机直连发出的请求；
  读者不挂梯打开这本电子书，依旧是一片黑块裂图。发布前把这点写进交付说明。

## 为什么必须起 `python -m http.server`，不能双击打开 .html

跨域安全与 Cookie 隐私协议：地址栏是 `file:///...` 的纯静态环境下，带交互控制器的内嵌播放组件会被视频源强制拒载。
必须通过本地 HTTP 服务访问 `http://localhost:8080/book.html`。

## 大会员 / 登录限制视频抓不到

给提取命令挂 cookies 参数，优先用专用配置（先 `--setup-profile` 登录一次）：`--cookies-from-profile <dir>`，
或 `--cookies-file <path>`（Netscape 格式）。**不要用 `--cookies-from chrome`**：Windows 上 Chrome 新版
App-Bound 加密使 yt-dlp 无法解密。截图清晰度同理 —— 在 `--setup-profile` 窗口登录大会员账号，
截帧管线会自动按顶档原生分辨率截取。

## 在 AI 沙箱里报「拒绝访问」

启动 Chrome / Playwright、读取浏览器 cookie 库的命令属于沙箱外权限，需申请提权（Codex 中即 require_escalated）：
`capture_frames.py <video_id> <url>`、`capture_frames.py --setup-profile`、
`dump_transcript.py <url>`（B 站需登录态时会起无头 Chrome 导出 cookies）、`course_assets.py` 的幻灯片渲染与 `--locate-slides`。
纯本地步骤（`post_process.py`、`make_corrected.py`、`publish.py`、`python -m http.server`）沙箱内即可。

## 视频完全没有字幕

`--list-subs` 只有 `danmaku`、播放器接口 `subtitle.subtitles` 为 `[]`（新上传视频常见，B 站 AI 字幕尚未生成）
→ 走本地 ASR 兜底，见 `transcript.md` 第 3 节。**不要因此停止流程。**

## 字幕覆盖率过低（退出码 3）

先分清是登录态 / 代理问题，还是平台真没字幕（`transcript.md` 第 2 节的表格）。
覆盖率不足 50% 时**不得进入第二步**，否则成书会缺内容。

## 截图发糊 / 有黑边 / 带播放器 UI

- 发糊通常是账号档位问题：请用户在 `.capture-profile/` 里登录大会员后重跑 `capture_frames.py`。
- 画面其实是幻灯片却没升级成官方图：用 `course_assets.py --match-shots` + `--apply-map`（见 `course-assets.md`）。
- v2 管线本身已做流锁定、隐藏播放器 UI、只对 `<video>` 元素截图；不要手工改 viewport，更不要改用屏幕截图。

## 截图变回未登录态

`.capture-profile/` 里的 cookie 过期，重跑 `python src/capture_frames.py --setup-profile` 登录一次。

## ASR 相关

- `Library cublas64_12.dll is not found`：装 `nvidia-cublas-cu12 nvidia-cudnn-cu12`，脚本会自动注册 DLL 目录。
- 显存 <= 4GB：加 `--compute-type int8_float16`；无 NVIDIA 卡自动退 CPU int8（更慢）。
- 中途中断：直接重跑，进度从 `_asr_progress.jsonl` 续接；抽样试跑之后转全量**必须加 `--restart`**。
- 中文错词多、输出没标点：写 `output/<id>/_asr_prompt.txt`（一两百字术语表，Whisper prompt 上限约 224 token）。
- PowerShell 里用命令行传含中文引号的长 prompt 会被弯引号当成定界符截断 → 一律走文件。

## 校订稿相关

- `--edits` 报 `source_sha256 不匹配`：transcript 已变，基于当前版本重新生成提案。
- 报「大幅修改」：确认改动合理后加 `--allow-large-edits`，否则拆成更小的行级订正。
- 想重建对照稿：脚本默认拒绝覆盖已有文件，加 `--force`（会丢掉此前的人工订正，先备份）。

## cookies 会泄露吗

不会落仓库：`dump_transcript.py` / `login_utils.py` 导出的 cookies 写入系统临时目录、用完即删；
`cookies.txt`、`.capture-profile/`、`output/` 都已在 `.gitignore` 中。仍不要手工把 cookies 文件放进工作区。