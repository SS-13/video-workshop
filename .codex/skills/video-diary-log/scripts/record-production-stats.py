#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import fcntl
import json
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable


FIELDNAMES = [
  "content_id",
  "date",
  "column",
  "day_label",
  "title",
  "video_path",
  "cover_path",
  "video_duration_seconds",
  "video_duration_text",
  "production_started_at",
  "production_finished_at",
  "production_total_minutes",
  "production_total_text",
  "estimated_tokens",
  "export_file_size_bytes",
  "notes",
  "updated_at",
]
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def project_root() -> Path:
  return Path.cwd().resolve()


def read_rows(path: Path) -> list[dict[str, str]]:
  if not path.exists():
    return []
  with path.open("r", encoding="utf-8-sig", newline="") as file:
    return list(csv.DictReader(file))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir=path.parent) as file:
    writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)
    temp_path = Path(file.name)
  temp_path.replace(path)


def seconds_to_text(seconds: float) -> str:
  total = int(round(seconds))
  minutes = total // 60
  remain = total % 60
  if minutes:
    return f"{minutes}分{remain}秒"
  return f"{remain}秒"


def minutes_to_text(minutes: float) -> str:
  if minutes >= 60:
    hours = int(minutes // 60)
    remain = int(round(minutes - hours * 60))
    return f"{hours}小时{remain}分钟"
  return f"{int(round(minutes))}分钟"


def parse_minutes(value: str | None) -> float | None:
  if not value:
    return None
  text = value.strip()
  if not text:
    return None
  hour_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|h)", text, flags=re.I)
  minute_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:分钟|分|min|m)", text, flags=re.I)
  if hour_match or minute_match:
    hours = float(hour_match.group(1)) if hour_match else 0.0
    minutes = float(minute_match.group(1)) if minute_match else 0.0
    return hours * 60 + minutes
  plain = re.fullmatch(r"\d+(?:\.\d+)?", text)
  if plain:
    return float(text)
  return None


def parse_datetime(value: str | None) -> datetime | None:
  if not value:
    return None
  text = value.strip()
  if not text:
    return None
  for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
    try:
      return datetime.strptime(text, fmt)
    except ValueError:
      pass
  return None


def infer_date_from_path(path: str) -> str:
  match = DATE_RE.search(path)
  return match.group(0) if match else ""


def duration_from_ffprobe(root: Path, video_path: str) -> float | None:
  if not video_path:
    return None
  full_path = (root / video_path).resolve()
  if not full_path.exists():
    return None
  result = subprocess.run(
    [
      "ffprobe",
      "-v",
      "error",
      "-show_entries",
      "format=duration",
      "-of",
      "json",
      str(full_path),
    ],
    check=False,
    capture_output=True,
    text=True,
  )
  if result.returncode != 0:
    return None
  try:
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])
  except (KeyError, ValueError, TypeError, json.JSONDecodeError):
    return None


def file_size_bytes(root: Path, file_path: str) -> str:
  if not file_path:
    return ""
  full_path = (root / file_path).resolve()
  if not full_path.exists():
    return ""
  return str(full_path.stat().st_size)


def build_content_id(date: str, column: str, day_label: str, video_path: str) -> str:
  if day_label:
    return f"{date}_{day_label.replace(' ', '')}"
  if column and column != "video-diary":
    stem = Path(video_path).stem if video_path else "001"
    return f"{date}_{column}_{stem}"
  return date


def with_file_lock(lock_path: Path, action: Callable[[], None]) -> None:
  lock_path.parent.mkdir(parents=True, exist_ok=True)
  with lock_path.open("w", encoding="utf-8") as lock_file:
    fcntl.flock(lock_file, fcntl.LOCK_EX)
    try:
      action()
    finally:
      fcntl.flock(lock_file, fcntl.LOCK_UN)


def valid_row(row: dict[str, str]) -> bool:
  content_id = row.get("content_id", "")
  date = row.get("date", "")
  return bool(content_id and DATE_RE.fullmatch(date))


def upsert_row(path: Path, row: dict[str, str]) -> None:
  rows = read_rows(path)
  rows_by_id = {
    existing.get("content_id", ""): existing
    for existing in rows
    if valid_row(existing)
  }
  rows_by_id[row["content_id"]] = row
  ordered_rows = sorted(rows_by_id.values(), key=lambda item: (item.get("date", ""), item.get("content_id", "")))
  write_rows(path, ordered_rows)


def update_daily_log(root: Path, row: dict[str, str]) -> None:
  date = row["date"]
  if not date:
    return
  log_path = root / "06_logs" / f"{date}.md"
  if not log_path.exists():
    return
  text = log_path.read_text(encoding="utf-8")
  replacements = {
    "- 视频时长：": f"- 视频时长：{row['video_duration_text']}（{row['video_duration_seconds']} 秒）",
    "- 总耗时：": f"- 总耗时：{row['production_total_text']}",
  }
  for prefix, new_line in replacements.items():
    text = re.sub(rf"^{re.escape(prefix)}.*$", new_line, text, flags=re.MULTILINE)
  log_path.write_text(text, encoding="utf-8")


def main() -> None:
  parser = argparse.ArgumentParser(description="Record production duration and final video length.")
  parser.add_argument("--date", default="", help="YYYY-MM-DD")
  parser.add_argument("--column", default="video-diary")
  parser.add_argument("--day-label", default="")
  parser.add_argument("--title", default="")
  parser.add_argument("--video-path", required=True)
  parser.add_argument("--cover-path", default="")
  parser.add_argument("--duration-seconds", type=float)
  parser.add_argument("--started-at", default="")
  parser.add_argument("--finished-at", default="")
  parser.add_argument("--total-minutes", type=float)
  parser.add_argument("--total-text", default="")
  parser.add_argument("--estimated-tokens", default="")
  parser.add_argument("--notes", default="")
  parser.add_argument("--allow-missing-time", action="store_true")
  parser.add_argument("--update-daily-log", action="store_true")
  args = parser.parse_args()

  root = project_root()
  date = args.date or infer_date_from_path(args.video_path)
  duration_seconds = args.duration_seconds
  if duration_seconds is None:
    duration_seconds = duration_from_ffprobe(root, args.video_path)
  if duration_seconds is None:
    raise SystemExit("Missing video duration. Provide --duration-seconds or a readable --video-path.")

  total_minutes = args.total_minutes
  if total_minutes is None and args.total_text:
    total_minutes = parse_minutes(args.total_text)
  started_at = parse_datetime(args.started_at)
  finished_at = parse_datetime(args.finished_at)
  if total_minutes is None and started_at and finished_at:
    total_minutes = max(0, (finished_at - started_at).total_seconds() / 60)
  if total_minutes is None and not args.allow_missing_time:
    raise SystemExit("Missing production time. Provide --total-minutes, --total-text, or start/finish times.")

  row = {
    "content_id": build_content_id(date, args.column, args.day_label, args.video_path),
    "date": date,
    "column": args.column,
    "day_label": args.day_label,
    "title": args.title,
    "video_path": args.video_path,
    "cover_path": args.cover_path,
    "video_duration_seconds": f"{duration_seconds:.2f}",
    "video_duration_text": seconds_to_text(duration_seconds),
    "production_started_at": args.started_at,
    "production_finished_at": args.finished_at,
    "production_total_minutes": f"{total_minutes:.2f}" if total_minutes is not None else "",
    "production_total_text": args.total_text or (minutes_to_text(total_minutes) if total_minutes is not None else ""),
    "estimated_tokens": args.estimated_tokens,
    "export_file_size_bytes": file_size_bytes(root, args.video_path),
    "notes": args.notes,
    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
  }

  state_ledger_path = root / "00_state" / "production-stats.csv"
  legacy_ledger_path = root / "06_logs" / "production-stats.csv"
  for ledger_path in (state_ledger_path, legacy_ledger_path):
    with_file_lock(ledger_path.with_suffix(".lock"), lambda path=ledger_path: upsert_row(path, row))
  if args.update_daily_log:
    update_daily_log(root, row)

  print(f"production_stats={state_ledger_path.relative_to(root)}")
  print(f"legacy_mirror={legacy_ledger_path.relative_to(root)}")
  print(f"content_id={row['content_id']}")
  print(f"video_duration={row['video_duration_text']}")
  print(f"production_total={row['production_total_text'] or 'missing'}")


if __name__ == "__main__":
  main()
