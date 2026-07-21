#!/usr/bin/env python3
"""Build and validate the publish package for one completed video."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import argparse
import json
import os
import re
import subprocess
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
INSTALL_ROOT = SCRIPT_DIR.parents[3]
TOOLS_DIR = INSTALL_ROOT / "09_tools"
sys.path.insert(0, str(TOOLS_DIR))

from video_production_core.contracts import load_json, validate_value  # noqa: E402
from video_production_core.active_finalization import finalize_active_run  # noqa: E402
from video_production_core.run_store import RunStateError  # noqa: E402


FFPROBE_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffprobe")
TIMING_RE = re.compile(
  r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*"
  r"(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)
CONTENT_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def ffprobe_bin() -> str:
  return os.environ.get("FFPROBE_BIN") or (
    str(FFPROBE_FULL) if FFPROBE_FULL.exists() else "ffprobe"
  )


def parse_srt_timestamp(value: str) -> float:
  hours, minutes, seconds = value.replace(",", ".").split(":")
  return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_chapter_timestamp(value: str) -> float:
  parts = value.strip().split(":")
  if len(parts) == 2:
    minutes, seconds = parts
    return int(minutes) * 60 + float(seconds)
  if len(parts) == 3:
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
  raise ValueError(f"Invalid chapter timestamp: {value}")


def format_chapter_time(seconds: float) -> str:
  total_seconds = max(0, int(round(seconds)))
  return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"


def parse_srt(path: Path) -> List[Dict[str, Any]]:
  blocks: List[Dict[str, Any]] = []
  for raw_block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()):
    lines = [line.strip() for line in raw_block.splitlines() if line.strip()]
    timing_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
    if timing_index is None:
      continue
    match = TIMING_RE.search(lines[timing_index])
    if not match:
      continue
    text = " ".join(lines[timing_index + 1:]).strip()
    if not text:
      continue
    blocks.append({
      "start": parse_srt_timestamp(match.group("start")),
      "end": parse_srt_timestamp(match.group("end")),
      "text": text,
    })
  if not blocks:
    raise ValueError(f"No valid SRT cues found: {path}")
  return blocks


def compact_title(text: str, max_units: int = 16) -> str:
  compact = re.sub(r"\s+", "", text).strip("，。！？、：；,.!?:;")
  return compact[:max_units] or "开始"


def chapter_from_argument(value: str, cues: List[Dict[str, Any]]) -> Dict[str, Any]:
  separator = "｜" if "｜" in value else "|"
  if separator not in value:
    raise ValueError(f"Chapter must use TIME|TITLE: {value}")
  timestamp, title = [item.strip() for item in value.split(separator, 1)]
  if not title:
    raise ValueError(f"Chapter title is empty: {value}")
  requested = parse_chapter_timestamp(timestamp)
  nearest = min(cues, key=lambda cue: abs(cue["start"] - requested))
  if abs(nearest["start"] - requested) > 0.5:
    raise ValueError(
      f"Chapter {timestamp} is not aligned to an SRT cue start; nearest={format_chapter_time(nearest['start'])}"
    )
  start = 0.0 if requested < 0.5 and nearest["start"] < 0.5 else nearest["start"]
  return {
    "startSeconds": round(start, 3),
    "time": format_chapter_time(start),
    "title": title,
  }


def automatic_chapters(cues: List[Dict[str, Any]], limit: int = 3) -> List[Dict[str, Any]]:
  count = min(limit, len(cues))
  if count == 1:
    indexes = [0]
  else:
    indexes = sorted({round(index * (len(cues) - 1) / (count - 1)) for index in range(count)})
  chapters = []
  for position, cue_index in enumerate(indexes):
    cue = cues[cue_index]
    start = 0.0 if position == 0 and cue["start"] < 0.5 else cue["start"]
    chapters.append({
      "startSeconds": round(start, 3),
      "time": format_chapter_time(start),
      "title": compact_title(cue["text"]),
    })
  return chapters


def probe_video(path: Path) -> Dict[str, Any]:
  result = subprocess.run(
    [
      ffprobe_bin(),
      "-v",
      "error",
      "-show_entries",
      "format=duration,size",
      "-of",
      "json",
      str(path),
    ],
    text=True,
    capture_output=True,
    check=True,
  )
  payload = json.loads(result.stdout)["format"]
  return {
    "durationSeconds": round(float(payload["duration"]), 3),
    "sizeBytes": int(payload["size"]),
  }


def relative_path(root: Path, path: Path) -> str:
  try:
    return str(path.resolve().relative_to(root.resolve()))
  except ValueError:
    return str(path.resolve())


def human_duration(seconds: float) -> str:
  rounded = int(round(seconds))
  return f"{rounded // 60}分{rounded % 60}秒"


def human_size(size_bytes: int) -> str:
  return f"{size_bytes / (1024 * 1024):.1f} MB"


def infer_content_date(package: Dict[str, Any], video: Path) -> str:
  values = [package.get("contentId", ""), package.get("runId", ""), *reversed(video.parts)]
  for value in values:
    match = CONTENT_DATE_RE.search(str(value))
    if match:
      return match.group(0)
  return ""


def markdown_content(package: Dict[str, Any]) -> str:
  production = package["production"]
  artifacts = package["artifacts"]
  rows = [
    "# 发布包",
    "",
    "## 抖音发布内容",
    "",
    f"标题：{package['title']}",
    "",
    f"描述：{package['description']}",
    "",
    "## 智能章节",
    "",
  ]
  rows.extend(f"{item['time']}｜{item['title']}" for item in package["chapters"])
  rows.extend([
    "",
    "## 制作结果",
    "",
    f"成片：{artifacts['video']}",
    f"封面 3:4：{artifacts['cover3x4']}",
    f"封面 4:3：{artifacts['cover4x3']}",
    f"视频时长：{human_duration(production['videoDurationSeconds'])}",
    f"文件大小：{human_size(production['fileSizeBytes'])}",
    f"制作耗时：{production['productionTotalMinutes']:.1f} 分钟",
    f"字幕检查：{production['subtitleQc']}",
    f"合规检查：{production['compliance']}",
    f"数据记录：{'recorded' if production['statsRecorded'] else 'not-recorded'}",
    f"系统版本：{production['systemVersion']}",
    f"发布状态：{'ready' if package['publishReady'] else 'not-ready'}",
    "",
  ])
  return "\n".join(rows)


def main() -> None:
  parser = argparse.ArgumentParser(description="Build PUBLISH.md and publish-package.json.")
  parser.add_argument("--run-id", required=True)
  parser.add_argument("--content-id", default="")
  parser.add_argument("--platform", default="douyin")
  parser.add_argument("--video", required=True)
  parser.add_argument("--srt", required=True)
  parser.add_argument("--cover-3x4", required=True)
  parser.add_argument("--cover-4x3", required=True)
  parser.add_argument("--title", required=True)
  parser.add_argument("--description", required=True)
  parser.add_argument("--chapter", action="append", default=[])
  parser.add_argument("--production-total-minutes", type=float, required=True)
  parser.add_argument("--subtitle-qc", choices=["pass", "revise"], default="pass")
  parser.add_argument("--compliance", choices=["pass", "revise", "block"], default="pass")
  parser.add_argument("--stats-recorded", action="store_true")
  parser.add_argument("--system-version", default="")
  parser.add_argument("--date", default="")
  parser.add_argument("--content-type", default="video-diary")
  parser.add_argument("--sequence", default="001")
  parser.add_argument("--output-dir")
  args = parser.parse_args()

  root = Path.cwd().resolve()
  video = Path(args.video).expanduser().resolve()
  srt = Path(args.srt).expanduser().resolve()
  cover_3x4 = Path(args.cover_3x4).expanduser().resolve()
  cover_4x3 = Path(args.cover_4x3).expanduser().resolve()
  for path in [video, srt, cover_3x4, cover_4x3]:
    if not path.exists():
      raise SystemExit(f"Missing publish artifact: {path}")

  cues = parse_srt(srt)
  chapters = (
    [chapter_from_argument(value, cues) for value in args.chapter]
    if args.chapter
    else automatic_chapters(cues)
  )
  if not chapters or chapters[0]["time"] != "00:00":
    raise SystemExit("The first smart chapter must start at 00:00.")

  video_info = probe_video(video)
  if cues[-1]["end"] > video_info["durationSeconds"] + 0.5:
    raise SystemExit("The final SRT cue exceeds the video duration.")

  system_version = args.system_version
  if not system_version:
    package_path = INSTALL_ROOT / "package.json"
    system_version = load_json(package_path).get("version", "unknown")

  package = {
    "schemaVersion": 1,
    "runId": args.run_id,
    "contentId": args.content_id or args.run_id,
    "contentType": args.content_type,
    "sequence": f"{int(args.sequence):03d}",
    "platform": args.platform,
    "title": args.title.strip(),
    "description": args.description.strip(),
    "chapters": chapters,
    "artifacts": {
      "video": relative_path(root, video),
      "cover3x4": relative_path(root, cover_3x4),
      "cover4x3": relative_path(root, cover_4x3),
      "srt": relative_path(root, srt),
    },
    "production": {
      "videoDurationSeconds": video_info["durationSeconds"],
      "fileSizeBytes": video_info["sizeBytes"],
      "productionTotalMinutes": round(args.production_total_minutes, 3),
      "subtitleQc": args.subtitle_qc,
      "compliance": args.compliance,
      "statsRecorded": args.stats_recorded,
      "systemVersion": system_version,
    },
    "publishReady": (
      args.subtitle_qc == "pass"
      and args.compliance == "pass"
      and args.stats_recorded
    ),
    "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
  }

  schema = load_json(
    INSTALL_ROOT / "00_system" / "contracts" / "schemas" / "publish-package.schema.json"
  )
  errors = validate_value(package, schema)
  if errors:
    raise SystemExit("Invalid publish package:\n" + "\n".join(errors))

  output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else video.parent
  output_dir.mkdir(parents=True, exist_ok=True)
  json_path = output_dir / "publish-package.json"
  markdown_path = output_dir / "PUBLISH.md"
  json_path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  markdown_path.write_text(markdown_content(package), encoding="utf-8")

  content_date = args.date or infer_content_date(package, video)
  try:
    active_run = finalize_active_run(
      root,
      date=content_date,
      publish_package_path=str(json_path),
      content_type=args.content_type,
      sequence=args.sequence,
      actor="video-agent",
    )
  except RunStateError as error:
    raise SystemExit(f"Active Run finalization failed: {error}") from error

  print(f"publish_json={json_path}")
  print(f"publish_markdown={markdown_path}")
  print(f"publish_ready={str(package['publishReady']).lower()}")
  print(f"chapters={len(chapters)}")
  print(f"active_run_enabled={str(active_run['enabled']).lower()}")
  print(f"active_run_changed={str(active_run['changed']).lower()}")
  if active_run.get("run"):
    print(f"active_run_id={active_run['run']['id']}")
  if active_run.get("contentLedger"):
    print(f"content_ledger_changed={str(active_run['contentLedger'].get('changed', False)).lower()}")


if __name__ == "__main__":
  main()
