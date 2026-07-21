#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
TEXT_ARCHIVE_DIR = "16_monthly_archive"
STATE_DIR = "00_state"
DEFAULT_COLUMN = "unknown"
SCAN_ROOTS = [
  "03_recordings",
  "04_videos",
  "05_exports",
]
DAILY_TEXT_ROOTS = [
  ("01_inbox", "inbox"),
  ("02_scripts", "scripts"),
  ("06_logs", "logs"),
]


@dataclass
class VideoFile:
  path: Path
  relative_path: str
  date: str
  stage: str
  bytes: int
  extension: str


def ensure_month(value: str) -> str:
  if not MONTH_RE.match(value):
    raise SystemExit(f"Month must use YYYY-MM format: {value}")
  return value


def project_root() -> Path:
  return Path.cwd().resolve()


def path_exists(path: Path) -> bool:
  try:
    path.stat()
    return True
  except FileNotFoundError:
    return False


def format_bytes(size: int) -> str:
  units = ["B", "KB", "MB", "GB", "TB"]
  value = float(size)
  unit_index = 0
  while value >= 1024 and unit_index < len(units) - 1:
    value /= 1024
    unit_index += 1
  decimals = 0 if unit_index == 0 else 1
  return f"{value:.{decimals}f} {units[unit_index]}"


def parse_duration_to_seconds(value: str | None) -> float | None:
  if not value:
    return None
  text = str(value).strip()
  if not text:
    return None

  minute_second = re.search(r"(\d+(?:\.\d+)?)\s*分\s*(\d+(?:\.\d+)?)?\s*秒?", text)
  if minute_second:
    minutes = float(minute_second.group(1))
    seconds = float(minute_second.group(2) or 0)
    return minutes * 60 + seconds

  numeric = re.search(r"(\d+(?:\.\d+)?)\s*秒", text)
  if numeric:
    return float(numeric.group(1))

  plain = re.fullmatch(r"\d+(?:\.\d+)?", text)
  if plain:
    return float(text)

  return None


def parse_minutes(value: str | None) -> float | None:
  if not value:
    return None
  text = str(value).strip()
  if not text or text in {"待复盘", "不可精确读取"}:
    return None

  hour = 0.0
  minute = 0.0
  hour_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:小时|h)", text, flags=re.I)
  minute_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:分钟|分|min|m)", text, flags=re.I)
  if hour_match:
    hour = float(hour_match.group(1))
  if minute_match:
    minute = float(minute_match.group(1))
  if hour_match or minute_match:
    return hour * 60 + minute

  plain = re.fullmatch(r"\d+(?:\.\d+)?", text)
  if plain:
    return float(text)

  return None


def parse_int(value: str | None) -> int | None:
  if value is None:
    return None
  text = str(value).strip()
  if not text:
    return None
  try:
    return int(float(text))
  except ValueError:
    return None


def seconds_to_hms(seconds: float) -> str:
  seconds = int(round(seconds))
  hours = seconds // 3600
  minutes = (seconds % 3600) // 60
  remain = seconds % 60
  if hours:
    return f"{hours}小时{minutes}分{remain}秒"
  return f"{minutes}分{remain}秒"


def minutes_to_text(minutes: float) -> str:
  hours = int(minutes // 60)
  remain = int(round(minutes - hours * 60))
  if hours:
    return f"{hours}小时{remain}分钟"
  return f"{remain}分钟"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
  if not path.exists():
    return []
  with path.open("r", encoding="utf-8-sig", newline="") as file:
    return list(csv.DictReader(file))


def write_csv_rows(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  with path.open("w", encoding="utf-8", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)


def first_existing_path(root: Path, paths: list[str]) -> Path:
  for raw_path in paths:
    candidate = root / raw_path
    if candidate.exists():
      return candidate
  return root / paths[0]


def list_daily_files(root: Path, source_dir: str, month: str) -> list[Path]:
  directory = root / source_dir
  if not directory.exists():
    return []
  return sorted(
    path for path in directory.iterdir()
    if (
      path.is_file()
      and path.name.startswith(month)
      and path.suffix == ".md"
      and DATE_RE.fullmatch(path.stem)
    )
  )


def list_archived_daily_files(archive_dir: Path, source_dir: str, month: str) -> list[Path]:
  directory = archive_dir / "text-assets" / "files" / source_dir
  if not directory.exists():
    return []
  return sorted(
    path for path in directory.iterdir()
    if (
      path.is_file()
      and path.name.startswith(month)
      and path.suffix == ".md"
      and DATE_RE.fullmatch(path.stem)
    )
  )


def combine_markdown(files: Iterable[Path], title: str, target: Path, root: Path) -> int:
  files = list(files)
  lines = [f"# {title}", ""]
  for file_path in files:
    lines.extend([
      f"## {file_path.stem}",
      "",
      f"> Source: `{file_path.relative_to(root)}`",
      "",
      file_path.read_text(encoding="utf-8").strip(),
      "",
    ])
  target.parent.mkdir(parents=True, exist_ok=True)
  target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
  return len(files)


def write_source_month_bundle(root: Path, source_dir: str, month: str, suffix: str, files: list[Path] | None = None) -> int:
  files = files if files is not None else list_daily_files(root, source_dir, month)
  target = root / source_dir / f"{month}_{suffix}.md"
  return combine_markdown(files, f"{month} {suffix}", target, root)


def copy_monthly_ledger(root: Path, archive_dir: Path, month: str) -> tuple[int, list[dict[str, str]]]:
  ledger_path = first_existing_path(root, [
    f"{STATE_DIR}/publish-ledger.csv",
    "06_logs/publish-ledger.csv",
  ])
  rows = read_csv_rows(ledger_path)
  monthly_rows = [row for row in rows if row.get("date", "").startswith(month)]
  if rows:
    write_csv_rows(archive_dir / f"publish-ledger-{month}.csv", monthly_rows, list(rows[0].keys()))
  return len(monthly_rows), monthly_rows


def copy_monthly_production_stats(root: Path, archive_dir: Path, month: str) -> tuple[int, list[dict[str, str]]]:
  stats_path = first_existing_path(root, [
    f"{STATE_DIR}/production-stats.csv",
    "06_logs/production-stats.csv",
  ])
  rows = read_csv_rows(stats_path)
  monthly_rows = [row for row in rows if row.get("date", "").startswith(month)]
  if rows:
    write_csv_rows(archive_dir / f"production-stats-{month}.csv", monthly_rows, list(rows[0].keys()))
  return len(monthly_rows), monthly_rows


def stage_from_relative_path(relative_path: str) -> str:
  if relative_path.startswith("03_recordings/"):
    return "recordings"
  if relative_path.startswith("04_videos/"):
    return "videos"
  if relative_path.startswith("05_exports/"):
    return "exports"
  return "other"


def extract_date_from_path(path: Path) -> str | None:
  for part in path.parts:
    if DATE_RE.match(part):
      return part
  match = re.search(r"\d{4}-\d{2}-\d{2}", path.name)
  return match.group(0) if match else None


def walk_files(directory: Path) -> Iterable[Path]:
  if not directory.exists():
    return []
  for path in directory.rglob("*"):
    if path.is_file():
      yield path


def scan_video_files(root: Path, month: str | None = None) -> list[VideoFile]:
  files: list[VideoFile] = []
  for scan_root in SCAN_ROOTS:
    base = root / scan_root
    for path in walk_files(base):
      if path.suffix.lower() not in VIDEO_EXTENSIONS:
        continue
      date = extract_date_from_path(path)
      if month and (not date or not date.startswith(month)):
        continue
      relative_path = path.relative_to(root).as_posix()
      files.append(VideoFile(
        path=path,
        relative_path=relative_path,
        date=date or "",
        stage=stage_from_relative_path(relative_path),
        bytes=path.stat().st_size,
        extension=path.suffix.lower(),
      ))
  return sorted(files, key=lambda item: (item.date, item.stage, -item.bytes, item.relative_path))


def summarize_video_files(files: list[VideoFile]) -> dict[str, object]:
  by_stage: dict[str, dict[str, int]] = {}
  by_date: dict[str, dict[str, int]] = {}
  for item in files:
    for bucket, key in ((by_stage, item.stage), (by_date, item.date or "unknown")):
      current = bucket.setdefault(key, {"count": 0, "bytes": 0})
      current["count"] += 1
      current["bytes"] += item.bytes
  return {
    "count": len(files),
    "bytes": sum(item.bytes for item in files),
    "by_stage": by_stage,
    "by_date": by_date,
  }


def write_video_manifest(path: Path, files: list[VideoFile]) -> None:
  lines = [
    "# 视频文件清单",
    "",
    "本文件用于人工确认和单文件删除。不要批量删除目录。",
    "",
    "| 日期 | 阶段 | 大小 | 路径 |",
    "| --- | --- | ---: | --- |",
  ]
  for item in files:
    lines.append(f"| {item.date or '-'} | {item.stage} | {format_bytes(item.bytes)} | `{item.relative_path}` |")
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_daily_log_value(log_path: Path, label: str) -> str:
  if not log_path.exists():
    return ""
  for line in log_path.read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    prefix = f"- {label}："
    if stripped.startswith(prefix):
      return stripped[len(prefix):].strip().strip("`")
  return ""


def build_monthly_stats(
  root: Path,
  month: str,
  ledger_rows: list[dict[str, str]],
  production_rows: list[dict[str, str]] | None = None,
) -> dict[str, object]:
  total_video_seconds = 0.0
  total_manual_minutes = 0.0
  total_elapsed_minutes = 0.0
  known_video_count = 0
  known_manual_count = 0
  known_elapsed_count = 0
  total_export_bytes = 0
  known_export_size_count = 0
  by_column: dict[str, dict[str, float]] = defaultdict(lambda: {
    "count": 0,
    "video_seconds": 0.0,
    "production_minutes": 0.0,
    "export_bytes": 0,
  })

  production_rows = production_rows or []
  if production_rows:
    for row in production_rows:
      column = row.get("column") or DEFAULT_COLUMN
      by_column[column]["count"] += 1

      duration_seconds = parse_duration_to_seconds(row.get("video_duration_seconds"))
      if duration_seconds is None:
        duration_seconds = parse_duration_to_seconds(row.get("video_duration_text"))
      if duration_seconds is not None:
        total_video_seconds += duration_seconds
        known_video_count += 1
        by_column[column]["video_seconds"] += duration_seconds

      elapsed_minutes = parse_minutes(row.get("production_total_minutes"))
      if elapsed_minutes is None:
        elapsed_minutes = parse_minutes(row.get("production_total_text"))
      if elapsed_minutes is not None:
        total_elapsed_minutes += elapsed_minutes
        known_elapsed_count += 1
        by_column[column]["production_minutes"] += elapsed_minutes

      export_size = parse_int(row.get("export_file_size_bytes"))
      if export_size is not None:
        total_export_bytes += export_size
        known_export_size_count += 1
        by_column[column]["export_bytes"] += export_size

    return {
      "published_or_logged_count": len(production_rows),
      "known_video_count": known_video_count,
      "video_seconds": total_video_seconds,
      "known_manual_count": known_manual_count,
      "manual_minutes": total_manual_minutes,
      "known_elapsed_count": known_elapsed_count,
      "elapsed_minutes": total_elapsed_minutes,
      "known_export_size_count": known_export_size_count,
      "export_bytes": total_export_bytes,
      "by_column": dict(by_column),
      "stats_source": "production-stats.csv",
    }

  for row in ledger_rows:
    date = row.get("date", "")
    log_path = root / "06_logs" / date / "video-diary" / "001.md"

    duration_seconds = parse_duration_to_seconds(row.get("video_duration"))
    if duration_seconds is None:
      duration_seconds = parse_duration_to_seconds(read_daily_log_value(log_path, "视频时长"))
    if duration_seconds is not None:
      total_video_seconds += duration_seconds
      known_video_count += 1

    manual_minutes = parse_minutes(row.get("manual_minutes"))
    if manual_minutes is not None:
      total_manual_minutes += manual_minutes
      known_manual_count += 1

    elapsed_minutes = parse_minutes(row.get("total_elapsed"))
    if elapsed_minutes is None:
      elapsed_minutes = parse_minutes(read_daily_log_value(log_path, "总耗时"))
    if elapsed_minutes is not None:
      total_elapsed_minutes += elapsed_minutes
      known_elapsed_count += 1

  return {
    "published_or_logged_count": len(ledger_rows),
    "known_video_count": known_video_count,
    "video_seconds": total_video_seconds,
    "known_manual_count": known_manual_count,
    "manual_minutes": total_manual_minutes,
    "known_elapsed_count": known_elapsed_count,
    "elapsed_minutes": total_elapsed_minutes,
    "known_export_size_count": 0,
    "export_bytes": 0,
    "by_column": {},
    "stats_source": "publish-ledger.csv + daily logs",
  }


def write_index(
  archive_dir: Path,
  month: str,
  counts: dict[str, int],
  stats: dict[str, object],
  video_summary: dict[str, object],
) -> None:
  by_stage = video_summary["by_stage"]
  stage_lines = []
  for stage, value in sorted(by_stage.items()):
    stage_lines.append(f"| {stage} | {value['count']} | {format_bytes(value['bytes'])} |")
  column_lines = []
  for column, value in sorted(stats.get("by_column", {}).items()):
    column_lines.append(
      f"| {column} | {int(value['count'])} | {seconds_to_hms(value['video_seconds'])} | "
      f"{minutes_to_text(value['production_minutes'])} | {format_bytes(int(value['export_bytes']))} |"
    )
  if not column_lines:
    column_lines.append("| - | 0 | 0分0秒 | 0分钟 | 0 B |")

  lines = [
    f"# {month} 视频日记月度复盘归档",
    "",
    "## 文本归档",
    "",
  ]
  if (archive_dir / "monthly-review-brief.md").exists():
    lines.append("- 人工简报：`monthly-review-brief.md`")
  if (archive_dir / "text-manuscripts.md").exists():
    lines.append("- 文字稿总汇：`text-manuscripts.md`")
  if (archive_dir / "text-assets-index.md").exists():
    lines.append("- 文字资产索引：`text-assets-index.md`")
  lines.extend([
    f"- 原始想法合并：{counts.get('inbox', 0)} 篇",
    f"- 脚本合并：{counts.get('scripts', 0)} 篇",
    f"- 日志合并：{counts.get('logs', 0)} 篇",
    f"- 发布台账行数：{counts.get('ledger', 0)} 行",
    f"- 制作统计行数：{counts.get('production_stats', 0)} 行",
    "",
    "## 生产统计（来自制作时埋点）",
    "",
    f"- 统计来源：{stats.get('stats_source', 'unknown')}",
    f"- 制作统计记录：{stats['published_or_logged_count']} 条",
    f"- 已知视频总长度：{seconds_to_hms(stats['video_seconds'])}（{stats['known_video_count']} 条有长度）",
    f"- 已知制作视频总用时：{minutes_to_text(stats['elapsed_minutes'])}（{stats['known_elapsed_count']} 条有记录）",
    f"- 已记录最终导出体积：{format_bytes(stats.get('export_bytes', 0))}（{stats.get('known_export_size_count', 0)} 条有记录）",
    "",
    "| 栏目 | 条数 | 视频总长度 | 制作用时 | 已记录导出体积 |",
    "| --- | ---: | ---: | ---: | ---: |",
    *column_lines,
    "",
    "## 当前本地视频文件扫描（仅清理参考）",
    "",
    "这里反映当前电脑里还剩多少媒体文件，不作为月度生产统计依据。",
    "",
    f"- 视频文件数：{video_summary['count']} 个",
    f"- 视频文件总大小：{format_bytes(video_summary['bytes'])}",
    "- 清单：`video-files.md`",
    "",
    "| 阶段 | 文件数 | 大小 |",
    "| --- | ---: | ---: |",
    *stage_lines,
    "",
    "## 安全规则",
    "",
    "- 月度复盘默认不删除视频文件。",
    "- 删除前先看 `video-files.md`。",
    "- 如需删除，只能用 `delete-one` 删除一个明确路径的视频文件。",
    "- 不删除 `01_inbox/`、`02_scripts/`、`06_logs/` 和本归档目录。",
    "",
  ])
  (archive_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def write_month_document(archive_dir: Path, month: str) -> Path:
  index_path = archive_dir / "INDEX.md"
  scripts_path = archive_dir / "scripts.md"
  target = archive_dir / f"{month}_month-document.md"

  lines = [
    f"# {month} 当月文档",
    "",
    "本文件汇总当月月度索引和全部脚本，方便月末删除视频文件后保留一个完整文字入口。",
    "",
    "## 文件来源",
    "",
    f"- 月度索引：`{index_path.name}`",
    f"- 当月脚本：`{scripts_path.name}`",
    "",
    "---",
    "",
    "## 月度索引",
    "",
  ]

  if index_path.exists():
    lines.append(index_path.read_text(encoding="utf-8").strip())
  else:
    lines.append("未找到 INDEX.md。")

  lines.extend([
    "",
    "---",
    "",
    "## 当月脚本",
    "",
  ])

  if scripts_path.exists():
    lines.append(scripts_path.read_text(encoding="utf-8").strip())
  else:
    lines.append("未找到 scripts.md。")

  target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
  return target


def run_review(args: argparse.Namespace) -> None:
  root = project_root()
  month = ensure_month(args.month)
  archive_dir = root / TEXT_ARCHIVE_DIR / month
  archive_dir.mkdir(parents=True, exist_ok=True)

  counts: dict[str, int] = {}
  for source_dir, target_name in DAILY_TEXT_ROOTS:
    files = list_daily_files(root, source_dir, month)
    if not files:
      files = list_archived_daily_files(archive_dir, source_dir, month)
    counts[target_name] = combine_markdown(
      files,
      f"{month} {target_name}",
      archive_dir / f"{target_name}.md",
      root,
    )
    if source_dir == "01_inbox":
      counts["source_inbox_bundle"] = write_source_month_bundle(root, source_dir, month, "inbox", files)
    if source_dir == "02_scripts":
      counts["source_scripts_bundle"] = write_source_month_bundle(root, source_dir, month, "scripts", files)

  ledger_count, monthly_ledger_rows = copy_monthly_ledger(root, archive_dir, month)
  counts["ledger"] = ledger_count
  production_count, monthly_production_rows = copy_monthly_production_stats(root, archive_dir, month)
  counts["production_stats"] = production_count

  video_files = scan_video_files(root, month)
  video_summary = summarize_video_files(video_files)
  write_video_manifest(archive_dir / "video-files.md", video_files)

  stats = build_monthly_stats(root, month, monthly_ledger_rows, monthly_production_rows)
  write_index(archive_dir, month, counts, stats, video_summary)
  month_document = write_month_document(archive_dir, month)

  print(f"monthly_archive={archive_dir.relative_to(root)}")
  print(f"month_document={month_document.relative_to(root)}")
  print(f"inbox={counts.get('inbox', 0)}")
  print(f"scripts={counts.get('scripts', 0)}")
  print(f"logs={counts.get('logs', 0)}")
  print(f"source_inbox_bundle={root / '01_inbox' / f'{month}_inbox.md'}")
  print(f"source_scripts_bundle={root / '02_scripts' / f'{month}_scripts.md'}")
  print(f"ledger_rows={counts.get('ledger', 0)}")
  print(f"production_stats_rows={counts.get('production_stats', 0)}")
  print(f"video_files={video_summary['count']}")
  print(f"video_size={format_bytes(video_summary['bytes'])}")
  print("No files were deleted.")


def run_scan_video(args: argparse.Namespace) -> None:
  root = project_root()
  month = args.month
  if month:
    month = ensure_month(month)
  files = scan_video_files(root, month)
  summary = summarize_video_files(files)

  if args.json:
    print(json.dumps({
      "count": summary["count"],
      "bytes": summary["bytes"],
      "human_size": format_bytes(summary["bytes"]),
      "files": [
        {
          "date": item.date,
          "stage": item.stage,
          "bytes": item.bytes,
          "human_size": format_bytes(item.bytes),
          "path": item.relative_path,
        }
        for item in files
      ],
    }, ensure_ascii=False, indent=2))
    return

  print(f"video_files={summary['count']}")
  print(f"video_size={format_bytes(summary['bytes'])}")
  for item in files:
    print(f"{format_bytes(item.bytes)}\t{item.date or '-'}\t{item.stage}\t{item.relative_path}")


def validate_delete_target(root: Path, raw_path: str) -> Path:
  path = (root / raw_path).resolve()
  try:
    path.relative_to(root)
  except ValueError:
    raise SystemExit("Refuse to delete paths outside the project.")
  if not path.exists() or not path.is_file():
    raise SystemExit(f"File does not exist: {raw_path}")
  if path.suffix.lower() not in VIDEO_EXTENSIONS:
    raise SystemExit("Refuse to delete non-video files.")
  return path


def run_delete_one(args: argparse.Namespace) -> None:
  root = project_root()
  target = validate_delete_target(root, args.path)
  relative_path = target.relative_to(root).as_posix()
  size = target.stat().st_size

  if not args.yes:
    print("dry_run=true")
    print(f"target={relative_path}")
    print(f"size={format_bytes(size)}")
    print("Pass --yes to delete this one explicit file.")
    return

  os.remove(target)
  log_path = root / "06_logs" / "video-file-delete-ledger.csv"
  is_new = not log_path.exists()
  log_path.parent.mkdir(parents=True, exist_ok=True)
  with log_path.open("a", encoding="utf-8", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=["deleted_at", "path", "bytes"])
    if is_new:
      writer.writeheader()
    writer.writerow({
      "deleted_at": datetime.now().isoformat(timespec="seconds"),
      "path": relative_path,
      "bytes": str(size),
    })

  print(f"deleted={relative_path}")
  print(f"size={format_bytes(size)}")
  print(f"ledger={log_path.relative_to(root)}")


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="Video diary monthly review and video file scanner.")
  subparsers = parser.add_subparsers(dest="command", required=True)

  review = subparsers.add_parser("review", help="Build monthly text archive and video file manifest.")
  review.add_argument("month", help="Month in YYYY-MM format.")
  review.set_defaults(func=run_review)

  scan = subparsers.add_parser("scan-video", help="Scan video files under 03_recordings/04_videos/05_exports.")
  scan.add_argument("--month", help="Optional month in YYYY-MM format.")
  scan.add_argument("--json", action="store_true", help="Print JSON instead of a text table.")
  scan.set_defaults(func=run_scan_video)

  delete_one = subparsers.add_parser("delete-one", help="Delete one explicit video file only.")
  delete_one.add_argument("path", help="Project-relative path to one video file.")
  delete_one.add_argument("--yes", action="store_true", help="Actually delete the one explicit file.")
  delete_one.set_defaults(func=run_delete_one)

  return parser


def main() -> None:
  parser = build_parser()
  args = parser.parse_args()
  args.func(args)


if __name__ == "__main__":
  main()
