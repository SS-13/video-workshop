#!/usr/bin/env python3
"""Initialize one date-first content item without overwriting local content."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import csv
import json
import os
import re
import tempfile

from video_production_core.content_layout import (
  CONTENT_TYPES,
  ContentRef,
  ensure_content_directories,
  next_sequence,
)


LEDGER_FIELDS = [
  "content_id", "date", "column", "day_label", "title", "status",
  "inbox_ref", "script_ref", "recording_ref", "workspace_ref",
  "export_ref", "cover_ref", "published_at", "douyin_url", "notes",
]
DAY_RE = re.compile(r"Day\s*(\d+)", re.IGNORECASE)


def atomic_write(path: Path, content: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  descriptor, temporary_name = tempfile.mkstemp(prefix=f"{path.name}-", dir=str(path.parent))
  try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
      file.write(content)
    os.replace(temporary_name, path)
  finally:
    if os.path.exists(temporary_name):
      os.unlink(temporary_name)


def write_if_absent(path: Path, content: str) -> str:
  path.parent.mkdir(parents=True, exist_ok=True)
  try:
    with path.open("x", encoding="utf-8") as file:
      file.write(content)
    return "created"
  except FileExistsError:
    return "exists"


def read_rows(path: Path) -> list[dict[str, str]]:
  if not path.is_file():
    return []
  with path.open(encoding="utf-8", newline="") as file:
    return list(csv.DictReader(file))


def known_day_number(root: Path, date: str) -> int | None:
  rows = read_rows(root / "00_state" / "content-ledger.csv")
  values = []
  for row in rows:
    if row.get("date") != date or row.get("column") != "video-diary":
      continue
    match = DAY_RE.search(row.get("day_label", ""))
    if match:
      values.append(int(match.group(1)))
  return max(values) if values else None


def next_day_number(root: Path, date: str, explicit: int | None, sequence: str = "001") -> int:
  if explicit:
    return explicit
  existing = known_day_number(root, date)
  if existing and sequence == "001":
    return existing
  counter_path = root / "00_state" / "day-counter.json"
  counter = json.loads(counter_path.read_text(encoding="utf-8")) if counter_path.is_file() else {}
  start = int(os.environ.get("VIDEO_DIARY_START_DAY", "1"))
  ledger_days = []
  for row in read_rows(root / "00_state" / "content-ledger.csv"):
    match = DAY_RE.search(row.get("day_label", ""))
    if match:
      ledger_days.append(int(match.group(1)))
  return max(start - 1, int(counter.get("lastDay", 0)), *ledger_days) + 1


def templates(ref: ContentRef, day_number: int | None) -> dict[str, str]:
  display = {
    "video-diary": "视频日记",
    "suisuinian": "碎碎念",
    "reading-note": "读书笔记",
  }.get(ref.content_type, ref.content_type)
  day_label = f"Day {day_number}" if day_number else ""
  inbox = (
    f"# {ref.date} {display} {ref.sequence}\n\n"
    "## 原始输入\n\n"
    "- 时间：\n"
    "- 原始口述：\n\n"
    "## 输入合规检视\n\n"
    "- 状态：待检视\n"
    "- 风险点：\n"
    "- 修改建议：\n"
  )
  script = (
    f"# {ref.date} {display}脚本 {ref.sequence}\n\n"
    "## 基本信息\n\n"
    f"- 日期：{ref.date}\n"
    f"- 内容类型：{ref.content_type}\n"
    f"- 内容序号：{ref.sequence}\n"
    f"- 视频编号：{day_label}\n"
    "- 标题：\n"
    "- 预计时长：\n\n"
    "## 提词器文案\n\n```text\n\n```\n\n"
    "## 制作路径\n\n"
    f"- 原始视频：`{ref.relative_stage_path('03_recordings')}/`\n"
    f"- 剪辑工程：`{ref.relative_stage_path('04_videos')}/`\n"
    f"- 发布包：`{ref.relative_stage_path('05_exports')}/`\n"
  )
  log = (
    f"# {ref.date} {display}运行日志 {ref.sequence}\n\n"
    "## 结果\n\n"
    "- 状态：\n"
    f"- 内容类型：{ref.content_type}\n"
    f"- 内容序号：{ref.sequence}\n"
    f"- 视频编号：{day_label}\n"
    "- 最终视频：\n"
    "- 视频时长：\n\n"
    "## 时间记录\n\n"
    "- 想法记录：\n"
    "- 脚本整理：\n"
    "- 自动剪辑：\n"
    "- 总耗时：\n\n"
    "## Agent 记录\n\n"
    "- Compliance Agent：\n"
    "- Text Agent：\n"
    "- Video Agent：\n"
  )
  return {"01_inbox": inbox, "02_scripts": script, "06_logs": log}


def update_ledger(root: Path, ref: ContentRef, day_number: int | None) -> tuple[str, str]:
  path = root / "00_state" / "content-ledger.csv"
  rows = read_rows(path)
  generic_id = ref.generic_content_id
  content_id = f"{ref.date}_Day{day_number}" if ref.content_type == "video-diary" else generic_id
  for row in rows:
    if row.get("content_id") == content_id or (
      row.get("date") == ref.date
      and row.get("column") == ref.content_type
      and row.get("inbox_ref") == ref.relative_stage_path("01_inbox")
    ):
      return "exists", row.get("content_id", content_id)
  rows.append({
    "content_id": content_id,
    "date": ref.date,
    "column": ref.content_type,
    "day_label": f"Day {day_number}" if day_number else "",
    "title": "",
    "status": "initialized",
    "inbox_ref": ref.relative_stage_path("01_inbox"),
    "script_ref": ref.relative_stage_path("02_scripts"),
    "recording_ref": f"{ref.relative_stage_path('03_recordings')}/",
    "workspace_ref": f"{ref.relative_stage_path('04_videos')}/",
    "export_ref": "",
    "cover_ref": "",
    "published_at": "",
    "douyin_url": "",
    "notes": "Initialized by date-first new-day.",
  })
  path.parent.mkdir(parents=True, exist_ok=True)
  temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
  with temporary.open("w", encoding="utf-8", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=LEDGER_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
  os.replace(temporary, path)
  return "created", content_id


def update_day_counter(root: Path, ref: ContentRef, day_number: int | None, content_id: str) -> str:
  if ref.content_type != "video-diary" or day_number is None:
    return "not-applicable"
  path = root / "00_state" / "day-counter.json"
  current = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
  if int(current.get("lastDay", 0)) > day_number:
    return "newer-state-kept"
  current.update({
    "schemaVersion": 1,
    "series": "video-diary",
    "lastDay": day_number,
    "lastContentId": content_id,
    "updatedAt": ref.date,
    "rules": {
      "videoDiaryIncrementsDay": True,
      "suisuinianIncrementsDay": False,
      "readingNoteIncrementsDay": False,
    },
  })
  atomic_write(path, json.dumps(current, ensure_ascii=False, indent=2) + "\n")
  return "updated"


def main() -> int:
  parser = argparse.ArgumentParser(description="Initialize a date-first content workspace.")
  parser.add_argument("date", nargs="?", default=datetime.now().astimezone().strftime("%Y-%m-%d"))
  parser.add_argument("--content-type", "--column", choices=CONTENT_TYPES, default="video-diary")
  parser.add_argument("--sequence", default="001")
  parser.add_argument("--next", action="store_true", dest="use_next")
  parser.add_argument("--day", type=int)
  parser.add_argument("--root", default=".")
  args = parser.parse_args()

  root = Path(args.root).expanduser().resolve()
  sequence = next_sequence(root, args.date, args.content_type) if args.use_next else args.sequence
  ref = ContentRef(args.date, args.content_type, sequence)
  day_number = next_day_number(root, ref.date, args.day, ref.sequence) if ref.content_type == "video-diary" else None
  ensure_content_directories(root, ref)
  statuses = {
    stage: write_if_absent(ref.text_path(root, stage), content)
    for stage, content in templates(ref, day_number).items()
  }
  ledger_status, content_id = update_ledger(root, ref, day_number)
  counter_status = update_day_counter(root, ref, day_number, content_id)

  print(f"content_key={ref.content_key}")
  print(f"content_id={content_id}")
  print(f"day_label={'Day ' + str(day_number) if day_number else ''}")
  for stage in ("01_inbox", "02_scripts", "06_logs"):
    print(f"{stage}={ref.relative_stage_path(stage)} ({statuses[stage]})")
  for stage in ("03_recordings", "04_videos", "05_exports", "15_cover_gallery"):
    print(f"{stage}={ref.relative_stage_path(stage)}/")
  print(f"ledger={ledger_status}")
  print(f"day_counter={counter_status}")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
