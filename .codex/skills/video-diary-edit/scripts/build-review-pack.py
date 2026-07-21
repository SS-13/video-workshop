from pathlib import Path
import argparse
import json
import os

from workflow_state import content_media_dir, load_job, save_job


REVIEW_DIR_NAME = "review"
REVIEW_VIDEO_NAME = "video.mp4"
REVIEW_SUBTITLE_NAME = "subtitles.srt"


def relative(root, value):
  if not value:
    return ""
  path = Path(value)
  try:
    return str(path.relative_to(root))
  except ValueError:
    return str(path)


def link_review_artifact(source, destination):
  """Create an idempotent relative link without overwriting real files."""
  source = Path(source)
  destination = Path(destination)
  if not source.is_file():
    return None

  destination.parent.mkdir(parents=True, exist_ok=True)
  source_resolved = source.resolve()
  if destination.is_symlink():
    if destination.resolve() == source_resolved:
      return destination
    destination.unlink()
  elif destination.exists():
    raise RuntimeError(f"Review asset destination already contains a real file: {destination}")

  destination.symlink_to(os.path.relpath(source_resolved, destination.parent.resolve()))
  return destination


def build_review_assets(root, workspace, video_value, subtitle_value):
  review_dir = Path(workspace) / REVIEW_DIR_NAME
  review_dir.mkdir(parents=True, exist_ok=True)
  video_path = Path(video_value) if video_value else None
  subtitle_path = Path(subtitle_value) if subtitle_value else None
  if video_path and not video_path.is_absolute():
    video_path = Path(root) / video_path
  if subtitle_path and not subtitle_path.is_absolute():
    subtitle_path = Path(root) / subtitle_path
  review_video = link_review_artifact(video_path, review_dir / REVIEW_VIDEO_NAME) if video_path else None
  review_subtitle = link_review_artifact(subtitle_path, review_dir / REVIEW_SUBTITLE_NAME) if subtitle_path else None

  readme = review_dir / "README.md"
  readme.write_text(
    "# 字幕复核素材\n\n"
    "在浏览器字幕工具中选择同一目录下的 `video.mp4` 和 `subtitles.srt`。\n\n"
    "这两个文件是指向规范产物的相对链接，不要在这里修改字幕；确认后的字幕仍以\n"
    "`../subtitles/*_corrected.srt` 为准。\n",
    encoding="utf-8",
  )
  manifest = review_dir / "review-manifest.json"
  manifest.write_text(
    json.dumps({
      "schemaVersion": 1,
      "purpose": "subtitle-review",
      "video": REVIEW_VIDEO_NAME if review_video else "",
      "subtitle": REVIEW_SUBTITLE_NAME if review_subtitle else "",
      "videoSource": os.path.relpath(video_path.resolve(), review_dir.resolve()) if video_path and video_path.is_file() else "",
      "subtitleSource": os.path.relpath(subtitle_path.resolve(), review_dir.resolve()) if subtitle_path and subtitle_path.is_file() else "",
    }, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
  )
  return {
    "directory": review_dir,
    "video": review_video,
    "subtitle": review_subtitle,
  }


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--date", required=True)
  parser.add_argument("--content-type", "--column", dest="content_type", default="video-diary")
  parser.add_argument("--sequence", default="001")
  parser.add_argument("--output")
  args = parser.parse_args()

  root = Path.cwd()
  job = load_job(root, args.date, args.content_type, args.sequence)
  output_path = Path(args.output) if args.output else (
    content_media_dir(root, "04_videos", args.date, args.content_type, args.sequence) / "REVIEW.md"
  )
  if not output_path.is_absolute():
    output_path = root / output_path

  artifacts = job.get("artifacts", {})
  quality = job.get("quality", {})
  content = job.get("content", {})
  requests = job.get("requests", {})
  confidence = quality.get("transcriptConfidence", {})
  review_assets = build_review_assets(
    root,
    content_media_dir(root, "04_videos", args.date, args.content_type, args.sequence),
    artifacts.get("reviewVideo") or artifacts.get("videoInput"),
    artifacts.get("correctedSrt"),
  )

  job.setdefault("artifacts", {})["reviewDirectory"] = str(review_assets["directory"])
  if review_assets["video"]:
    job["artifacts"]["reviewVideoLink"] = str(review_assets["video"])
  if review_assets["subtitle"]:
    job["artifacts"]["reviewSubtitleLink"] = str(review_assets["subtitle"])

  rows = [
    f"# {args.date} 联合确认包",
    "",
    "## 内容",
    "",
    f"- 栏目：{job.get('column', 'video-diary')}",
    f"- 标题：{content.get('title', '')}",
    f"- 副标题：{content.get('subtitle', '')}",
    f"- Day：{content.get('dayLabel', '')}",
    "",
    "## 封面",
    "",
    f"- 3:4：`{relative(root, artifacts.get('cover3x4'))}`",
    f"- 4:3：`{relative(root, artifacts.get('cover4x3'))}`",
    f"- 样式：{job.get('style', {}).get('coverRoute', '')} / {job.get('style', {}).get('coverVersion', '')}",
    "",
    "## 字幕",
    "",
    f"- 检查视频：`{relative(root, artifacts.get('reviewVideo') or artifacts.get('videoInput'))}`",
    f"- 外挂字幕：`{relative(root, artifacts.get('correctedSrt'))}`",
    f"- 统一复核目录：`{relative(root, review_assets['directory'])}/`",
    f"- 浏览器视频入口：`{relative(root, review_assets['video']) if review_assets['video'] else '缺失'}`",
    f"- 浏览器字幕入口：`{relative(root, review_assets['subtitle']) if review_assets['subtitle'] else '缺失'}`",
    f"- 词级时间戳：`{relative(root, artifacts.get('wordJson'))}`",
    f"- 低置信度片段：{confidence.get('uncertainCount', 0)}",
    f"- 文本检查：{quality.get('subtitleText', {}).get('status', 'pending')}",
    f"- 时间轴检查：{quality.get('subtitleTiming', {}).get('status', 'pending')}",
    "",
    "## 插入内容",
    "",
  ]

  insert_plan = requests.get("insertPlan", [])
  if not insert_plan:
    rows.append("无。")
  else:
    rows.extend(["| 时间 | 素材 | 位置/宽度 |", "| --- | --- | --- |"])
    for item in insert_plan:
      rows.append(
        f"| {item.get('start')}-{item.get('end')} | `{item.get('path', '')}` | "
        f"{item.get('position', 'top-right')} / {item.get('widthPercent', 30)}% |"
      )

  rows.extend([
    "",
    "## 确认结果",
    "",
    "- [ ] 封面确认",
    "- [ ] 字幕文字确认",
    "- [ ] 字幕时间轴确认",
    "- [ ] 插入内容确认",
    "",
    "确认完成后从当前 SRT 和视频输入直接进入一次最终渲染，不重新转写。",
  ])

  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text("\n".join(rows).rstrip() + "\n", encoding="utf-8")
  job["status"] = "awaiting_review"
  job.setdefault("artifacts", {})["reviewPack"] = str(output_path)
  save_job(root, args.date, job, args.content_type, args.sequence)

  print(f"review_pack={output_path}")
  print(f"status={job['status']}")


if __name__ == "__main__":
  main()
