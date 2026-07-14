from pathlib import Path
import argparse
import json

from workflow_state import load_job, save_job


def relative(root, value):
  if not value:
    return ""
  path = Path(value)
  try:
    return str(path.relative_to(root))
  except ValueError:
    return str(path)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--date", required=True)
  parser.add_argument("--output")
  args = parser.parse_args()

  root = Path.cwd()
  job = load_job(root, args.date)
  output_path = Path(args.output) if args.output else root / "04_videos" / args.date / "REVIEW.md"
  if not output_path.is_absolute():
    output_path = root / output_path

  artifacts = job.get("artifacts", {})
  quality = job.get("quality", {})
  content = job.get("content", {})
  requests = job.get("requests", {})
  confidence = quality.get("transcriptConfidence", {})

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
  save_job(root, args.date, job)

  print(f"review_pack={output_path}")
  print(f"status={job['status']}")


if __name__ == "__main__":
  main()
