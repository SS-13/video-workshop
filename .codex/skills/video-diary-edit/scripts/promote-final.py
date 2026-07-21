#!/usr/bin/env python3
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys

from workflow_state import content_media_dir


SCRIPT_DIR = Path(__file__).resolve().parent
LOG_SCRIPT = SCRIPT_DIR.parent.parent / "video-diary-log" / "scripts" / "record-production-stats.py"


def resolve_path(root, value):
  path = Path(value)
  return path if path.is_absolute() else root / path


def relative_to_root(root, path):
  try:
    return str(path.resolve().relative_to(root))
  except ValueError:
    return str(path)


def export_dir(root, date, content_type, sequence):
  return content_media_dir(root, "05_exports", date, content_type, sequence)


def default_name(date, day_label, column):
  if column == "video-diary":
    if not day_label:
      raise SystemExit("--day-label is required for video-diary.")
    compact_day = day_label.replace(" ", "")
    return f"{date}_{compact_day}_video-diary.mp4"
  return f"{date}_{column}.mp4"


def copy_one(source, target):
  if not source.exists():
    raise SystemExit(f"Missing source file: {source}")
  if source.resolve() == target.resolve():
    return
  target.parent.mkdir(parents=True, exist_ok=True)
  shutil.copy2(source, target)


def main():
  parser = argparse.ArgumentParser(description="Promote one edited MP4 into 05_exports and record production stats.")
  parser.add_argument("--date", required=True, help="Content date, not production date.")
  parser.add_argument("--input", required=True, help="Edited MP4 in 04_videos or another explicit path.")
  parser.add_argument("--cover", default="")
  parser.add_argument("--content-type", "--column", dest="content_type", default="video-diary")
  parser.add_argument("--sequence", default="001")
  parser.add_argument("--clip-id", default="")
  parser.add_argument("--day-label", default="")
  parser.add_argument("--title", default="")
  parser.add_argument("--output-name", default="")
  parser.add_argument("--started-at", default="")
  parser.add_argument("--finished-at", default="")
  parser.add_argument("--total-minutes", type=float)
  parser.add_argument("--total-text", default="")
  parser.add_argument("--estimated-tokens", default="")
  parser.add_argument("--notes", default="")
  parser.add_argument("--allow-missing-time", action="store_true")
  parser.add_argument("--dry-run", action="store_true")
  args = parser.parse_args()

  root = Path.cwd().resolve()
  source = resolve_path(root, args.input)
  cover = resolve_path(root, args.cover) if args.cover else None
  target_dir = export_dir(root, args.date, args.content_type, args.sequence)
  target_name = args.output_name or default_name(args.date, args.day_label, args.content_type)
  target_video = target_dir / target_name
  target_cover = target_dir / cover.name if cover else None

  stats_command = [
    sys.executable,
    LOG_SCRIPT,
    "--date",
    args.date,
    "--column",
    args.content_type,
    "--sequence",
    args.sequence,
    "--video-path",
    relative_to_root(root, target_video),
    "--title",
    args.title,
    "--notes",
    args.notes,
    "--update-daily-log",
  ]
  if args.day_label:
    stats_command.extend(["--day-label", args.day_label])
  if target_cover:
    stats_command.extend(["--cover-path", relative_to_root(root, target_cover)])
  if args.started_at:
    stats_command.extend(["--started-at", args.started_at])
  if args.finished_at:
    stats_command.extend(["--finished-at", args.finished_at])
  if args.total_minutes is not None:
    stats_command.extend(["--total-minutes", str(args.total_minutes)])
  if args.total_text:
    stats_command.extend(["--total-text", args.total_text])
  if args.estimated_tokens:
    stats_command.extend(["--estimated-tokens", args.estimated_tokens])
  if args.allow_missing_time:
    stats_command.append("--allow-missing-time")

  if args.dry_run:
    print(f"copy_video={source} -> {target_video}")
    if cover:
      print(f"copy_cover={cover} -> {target_cover}")
    print("record_stats=" + " ".join(str(item) for item in stats_command))
    return

  copy_one(source, target_video)
  if cover:
    copy_one(cover, target_cover)
  subprocess.run([str(item) for item in stats_command], check=True)

  size = target_video.stat().st_size
  result = {
    "video": relative_to_root(root, target_video),
    "cover": relative_to_root(root, target_cover) if target_cover else "",
    "sizeBytes": size,
    "statsRecorded": True,
  }
  print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
  main()
