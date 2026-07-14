# Codex 每日自动粗剪提示词

```text
今天要处理的视频日记日期是：YYYY-MM-DD。

请读取：
- WORKFLOW.md
- 02_scripts/YYYY-MM-DD.md
- 03_recordings/YYYY-MM-DD/

目标：
把今天用提词器 APP 录好的多段口播，自动粗剪成一个完整视频。

请执行：
1. 读取 02_scripts/YYYY-MM-DD.md，提取有实际内容的 S01/S02/S03/... 段落；空模板段落忽略。
2. 读取 03_recordings/YYYY-MM-DD/ 下的视频文件。
3. 如果文件名包含 S01/S02/...，优先按编号匹配；否则按录制顺序自动匹配脚本段落。
4. 如果当天有多段视频，先对每段独立做片尾黑屏/品牌页检测和裁切副本。
5. 生成 04_videos/YYYY-MM-DD/BRIEF.md。
6. 生成 04_videos/YYYY-MM-DD/EDIT_DECISIONS.md。
7. 生成 04_videos/YYYY-MM-DD/STORYBOARD.md。
8. 优先用 FFmpeg MVP 路线生成字幕和发布包；HyperFrames 只作为后续包装增强。
9. 输出成片到 05_exports/YYYY-MM-DD/YYYY-MM-DD_DayNN_video-diary.mp4，输出封面到 05_exports/YYYY-MM-DD/YYYY-MM-DD_DayNN_cover.jpg。

风格要求：
- 真实、克制、日记感。
- 不做营销片。
- 每段前只加简洁标题卡。
- 字幕清楚，不要花哨。
- BGM 可选，默认不要盖过人声。

如果本机环境缺 FFmpeg、ffprobe 或转写工具，请先生成 BRIEF / EDIT_DECISIONS / STORYBOARD，并明确告诉我缺什么，先不要强行渲染。
```
