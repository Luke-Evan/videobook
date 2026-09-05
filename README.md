# VideoBook Agent

提供一段 YouTube 或 Bilibili 的视频链接，AI 助手（如 Claude Code / Antigravity）将负责整理内容逻辑，并将视频中带有演示操作的时间锚点直接转为内嵌视频卡片，最终自动全产出生成高质量的技术图文电子书。

## 环境准备

1. `Python >= 3.10`
2. 克隆本仓库到本地环境
3. 安装 Python 依赖:
   ```bash
   pip install -r requirements.txt
   ```

## 🚀 如何使用？(用户视角)

**全自动托管！你唯一要做的就是把视频链接发给 AI。**

1. 将当前的工作目录导入或者在此唤醒你的 AI 助手。
2. 给它下达诸如像这样的一句话口语化自然语言指令：
   > “请接管帮我把这个视频做成电子书：`https://www.bilibili.com/video/BVxxx/`，如果是海外视频，必要的话去使用我的系统代理或者指定带有大会员权限浏览器的 cookie。”
3. 到这步为止你就可以泡杯咖啡休息了。助手内部会自动流转管道。
4. 完事后，它将甩在你的聊天面板里这主要两样东西：
   - 包含着精细化Markdown技术指南文章的文件：**`output/<视频ID>/book.md`**
   - 甚至不用你手动敲起服务，它会贴心地帮你开启本地端口服务然后告诉你：**你现在可以去 `http://localhost:8080/book.html` 边看边互动啦！**

---

## ⚙️ 内部 Pipeline 运作原理 (Agent 侧)

当你向助手发放链接任务时，本工具箱实质为其底层配置了一套五步组合流水线（参考指令文档 `instructions.md`）：

1. **抓取 字幕 (Scraping)**: 调用脚本 `python dump_transcript.py <url>` 剥离得到原始口语字幕 JSON。
2. **重写 编排 (Stitching)**: AI 利用大模型能力将乱七八糟的字幕提取要义改写为 Markdown，并在关键讲解处插入 `![描述](SCREENSHOT:00:15:30)` 时间戳指令占位。
3. **截帧 插图 (Capturing)**：在已登录浏览器中直接截取平台播放器画面（画质直接来自平台，不下载任何媒体文件）：Codex 桌面环境首选 Chrome 扩展（@Chrome）；通用脚本 `python capture_frames.py` 使用专用截帧配置（`.capture-profile/`，一次性登录、长期复用登录态；Chrome 136+ 禁止对默认配置远程调试，故不触碰主 Chrome），失败后才兜底 `python extract_frames.py`（下载视频源用 ffmpeg 抽帧，文件保留至流程结束并询问用户是否删除）。两者都会把 `book.md` 中的占位符物化为真实图片链接（原标签稿自动备份为 `book.tagged.md`）；HTML 中的截图支持点击放大浏览。
4. **渲染 网页 (Rendering)**: 调用 `python post_process.py <url> <md>` 把所有占位的锚点改造成 YouTube/B站原生轻量级 `iframe` 代码，并且注入极简暗色主题，把枯燥的 `.md` 内容最终渲染为可直接在线看的富文本 `.html`。
5. **发服 预览 (Serving)**: 通过 Python 挂起一个简易的本地 HTTP 服务器。


## ⚠️ 常见踩坑指南

1. **为什么 Youtube 无法获取字幕或者在内嵌的 iframe 卡片上显示 "视频配置错误(153)" 之类的错误？**
   这并非脚本代码问题，而是网络审查与封锁。如果你打算处理海外视频，你必须：
   - **终端走代理**：底层基于第三方库爬取时，才能去拿去它的字幕和源信息。
   - **浏览器走全局代理**：如果你生成的页面上有 YouTube 内嵌 iframe 请求，其源来自于你本台机器发去的直连请求。如果没有挂梯打开这篇 HTML 电子书，依旧将会是一片黑块裂图。

2. **为什么最后偏偏多加一步挂本地 HTTP Server 服务（`python -m http.server`）而不是直接用系统双击本地资源打开 .html 文件？**
   由于跨域安全以及 Cookie 隐私保护协议问题，内嵌在线带有交互控制器的播放组件如果是在没有后端协议的本地静态环境（浏览器左上角地址栏为 `file:///...`），视频源将会强制拒载报错加载失败。所以必须通过本地 HTTP 服务解决该隐患缺陷。

3. **专享和会员加密资源抓取受限？**
   对于大会员等登录拦截权限视频，可以通过在内部提取命令后边挂载 `--cookies-from chrome` 的相关指令，向你所在的本地机器的相应常驻浏览器的 Cookie 中调用以通过验证拿到字幕文件！

4. **在 AI 沙箱（如 Codex）里运行为何报"拒绝访问"？哪些命令需要沙箱外执行？**
   本流水线的截帧与字幕抓取需要启动 Chrome / Playwright、读取浏览器 cookie 库，属于沙箱外权限。托管给 AI 助手时，以下命令应申请沙箱外执行（Codex 中即批准 require_escalated）：
   - `python capture_frames.py <video_id> <url>`（启动无头 Chrome 截帧）
   - `python capture_frames.py --setup-profile`（弹出 Chrome 供一次性登录）
   - `python dump_transcript.py <url>`（yt-dlp 网络请求；B 站需登录态时会自动从 .capture-profile 导出 cookies，期间启动无头 Chrome）
   纯本地步骤（`post_process.py`、`python -m http.server`）在沙箱内即可运行。

5. **自动导出的 cookies 会泄露吗？**
   不会落在仓库里：`dump_transcript.py` / `login_utils.py` 导出的 cookies 写入系统临时目录、用完即删；`cookies.txt` 等模式已加入 `.gitignore`。若需更高清晰度（大会员档位），在 `--setup-profile` 窗口登录大会员账号即可，截帧管线会自动按顶档原生分辨率截取。

---

## 📚 成品在哪里看？

- **在线阅读（GitHub Pages）**：`https://luke-evan.github.io/videobook/` —— 落地页列出全部电子书，点击标题即可阅读（含截图放大、Mermaid 交互）。需在仓库 Settings → Pages 一次性选择分支 `pages` + `/ (root)`。
- **分支布局**：`main` = 工具代码；`pages` = 成品（独立 orphan 分支，目录名 = 视频标题，如 `提示词工程 [02-Raw／26生成式软件工程／NJU]`）。
- **发布方式**：`python publish.py <video_id>` 或 `python publish.py --all`，然后 `git push origin pages`。发布 `book.html / book.md / images/` 与（若存在）`transcript.corrected.txt`（AI 修正版字幕对照稿，落地页卡片附"字幕对照"链接）；原始字幕、transcript.json 等中间物不进公开仓库；`output/` 本地工作区不受任何 git 操作影响。
