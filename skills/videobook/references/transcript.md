# 第一步：提取字幕（含本地 ASR 兜底）

## 1. 平台字幕

```bash
python src/dump_transcript.py "<VIDEO_URL>"
```

- 自动识别平台，产出 `output/<video_id>/transcript.json` 与 `transcript.txt`。
- `transcript.json` 字段：`video_url / title / video_id / duration / chapters / segments`。
  第二步必须用到 `duration` 与 `chapters`（平台官方章节，可能是空数组）。
- **B 站登录态自动获取**：`.capture-profile/` 里有登录态时，脚本自动把 cookies 导出到系统临时目录、用完即删，
  期间会启动无头 Chrome，因此**需沙箱外执行**（Codex 中申请 require_escalated）。
- 提示专用配置无登录态时：请用户先跑一次 `python src/capture_frames.py --setup-profile` 扫码登录，再重试本步。
- cookies 来源三选一：`--cookies-from-profile <dir>`（默认 `.capture-profile`）、`--cookies-file <path>`（Netscape 格式）、
  `--cookies-from <browser>`（旧方式；Windows 主 Chrome 因 App-Bound 加密通常解不开，**不要默认使用**）。
- **覆盖率自检**：成功时打印「字幕覆盖率」= 末段结束时间 / `duration`。低于 50% 以退出码 3 结束并打印修复提示，
  此时**不得进入第二步**（铁律 1）。

## 2. 区分两类失败（决定是修环境还是转 ASR）

| 现象 | 判断 | 处理 |
|---|---|---|
| 覆盖率过低、超时、地区限制、需要登录 | 环境 / 权限问题 | 修代理或登录态后重跑本步 |
| `--list-subs` 只有 `danmaku`；播放器接口 `subtitle.subtitles` 为 `[]` | 平台确实没有字幕（新上传视频常见，B 站 AI 字幕尚未生成） | **不要停流程**，转下面的 ASR 兜底 |

两类都排除后仍失败，才告知用户可能原因（无字幕 / 需代理 / 需登录）并停止。海外视频终端必须走代理。

## 3. 兜底：本地 ASR 转写

```bash
python src/asr_transcript.py <video_id> [--sample-start 900 --sample-dur 180]
```

- 流程：只下载音频轨到 `output/<id>/audio.m4a`（不下载视频流）→ faster-whisper `large-v3` 转写 →
  按标点/时长切成接近平台字幕粒度的短段 → 写出与平台字幕**完全同构**的 `transcript.json` / `transcript.txt`。
  所以第二步之后的所有步骤零改动。
- **先抽样再全量**：`--sample-start 900 --sample-dur 180` 只转 3 分钟，确认质量与速度后再跑全量；
  跑全量**务必带 `--restart`**，否则会漏掉抽样区间之前的内容。
- **领域术语提示**：把本讲主题与术语（一两百字）写进 `output/<id>/_asr_prompt.txt`，能显著压制同音错词并让中文输出自带标点。
  Whisper prompt 上限约 224 token，过长会被截断。**PowerShell 下不要用命令行传含中文引号的长 prompt**
  （弯引号会被当成字符串定界符），一律走文件，或用 `--initial-prompt-file`。
- **算力**：有 NVIDIA 显卡自动用 CUDA；显存 <= 4GB 加 `--compute-type int8_float16`；无卡自动退 CPU int8。
  Windows 报 `Library cublas64_12.dll is not found` 时装 `nvidia-cublas-cu12 nvidia-cudnn-cu12`（脚本会自动注册 DLL 目录）。
- **断点续跑**：进度实时写入 `output/<id>/_asr_progress.jsonl`，中断后重跑自动从末尾续接。
- **耗时预期**：100 分钟课程在 RTX 3050 (4GB) 上约 35 分钟，会产生约 90MB 的 `audio.m4a`。
  这段时间可以并行准备第三步的截帧环境（`--setup-profile`）和术语表。结束时按铁律 9 询问是否删除大文件。
- 转写完成后仍要过覆盖率自检（脚本已内置）；低于 50% 说明没跑完，重跑续写。

## 4. ASR 稿的后续待遇

ASR 产出**同样算「原始字幕」**：同样要建术语表、同样要容忍同音错词、同样要产出 `transcript.corrected.txt`
（见 `correction.md`）。本地 large-v3 的错词率通常低于平台 AI 字幕，但专有名词仍需人工订正。