# Publish Package Contract

Every completed video must produce a human-readable `PUBLISH.md` and a structured `publish-package.json` next to the final MP4 and covers.

## Source Of Truth

- Generate the publish title, description, and chapters from the confirmed corrected SRT and real spoken content.
- Use the script only as background context. Do not use script timestamps.
- Fill duration, file size, and production time from the final export and recorded production stats.
- Run Compliance Agent on the title, description, and chapter labels before marking the package publish-ready.

## Required Markdown Format

```text
# 发布包

## 抖音发布内容

标题：TITLE

描述：DESCRIPTION

## 智能章节

00:00｜CHAPTER TITLE
00:42｜CHAPTER TITLE
01:28｜CHAPTER TITLE

## 制作结果

成片：FINAL_VIDEO_PATH
封面 3:4：COVER_3X4_PATH
封面 4:3：COVER_4X3_PATH
视频时长：DURATION
文件大小：FILE_SIZE
制作耗时：PRODUCTION_TIME
字幕检查：pass|revise
合规检查：pass|revise|block
数据记录：RECORDED_STATE
系统版本：VERSION
发布状态：ready|not-ready
```

## Content Rules

- Provide one Douyin title. Keep it concise and faithful to the video's actual topic.
- Provide one publish description, normally one to three short sentences.
- Do not add download, registration, private-message, group-join, or external-platform calls to action unless the user explicitly requests them and Compliance Agent passes them.
- Provide three to five smart chapters when the video has enough topic changes. Very short videos may use fewer chapters.
- Each chapter timestamp must match the start of a real corrected SRT cue near the topic transition.
- Use `MM:SS｜标题` and start the first chapter at `00:00`.
- Chapter titles should be short topic labels, not full sentences.

## Structured Output

`publish-package.json` must include:

```json
{
  "contentId": "",
  "platform": "douyin",
  "title": "",
  "description": "",
  "chapters": [
    {"startSeconds": 0, "time": "00:00", "title": ""}
  ],
  "artifacts": {
    "video": "",
    "cover3x4": "",
    "cover4x3": ""
  },
  "production": {
    "videoDurationSeconds": 0,
    "fileSizeBytes": 0,
    "productionTotalMinutes": 0,
    "subtitleQc": "pass",
    "compliance": "pass",
    "statsRecorded": true,
    "systemVersion": ""
  },
  "publishReady": true
}
```

The package is incomplete if the final video exists but the title, description, chapters, or production result is missing.
