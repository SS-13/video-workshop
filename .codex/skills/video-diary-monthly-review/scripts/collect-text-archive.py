#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
from dataclasses import dataclass
from pathlib import Path


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
TEXT_EXTENSIONS = {".md", ".srt", ".txt", ".csv", ".json", ".tsv", ".yaml", ".yml"}
SOURCE_ROOTS = [
  "01_inbox",
  "02_scripts",
  "04_videos",
  "06_logs",
  "13_predictions",
  "15_cover_gallery",
]
GLOBAL_SUPPORT_FILES = {
  "06_logs/publish-ledger.csv",
  "06_logs/douyin-videos.csv",
  "06_logs/douyin-metrics-snapshots.csv",
  "06_logs/workflow-todo.md",
}


@dataclass
class CopiedTextFile:
  source: Path
  relative_path: str
  target: Path


def ensure_month(value: str) -> str:
  if not MONTH_RE.match(value):
    raise SystemExit(f"Month must use YYYY-MM format: {value}")
  return value


def project_root() -> Path:
  return Path.cwd().resolve()


def is_text_file(path: Path) -> bool:
  return path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS


def path_matches_month(relative_path: str, month: str) -> bool:
  if month in relative_path:
    return True
  for match in DATE_RE.findall(relative_path):
    if match.startswith(month):
      return True
  return relative_path in GLOBAL_SUPPORT_FILES


def iter_text_sources(root: Path, month: str) -> list[Path]:
  results: list[Path] = []
  for source_root in SOURCE_ROOTS:
    base = root / source_root
    if not base.exists():
      continue
    for path in base.rglob("*"):
      if not is_text_file(path):
        continue
      relative_path = path.relative_to(root).as_posix()
      if path_matches_month(relative_path, month):
        results.append(path)
  return sorted(set(results), key=lambda path: path.relative_to(root).as_posix())


def copy_text_files(root: Path, month: str, archive_dir: Path) -> list[CopiedTextFile]:
  target_root = archive_dir / "text-assets" / "files"
  copied: list[CopiedTextFile] = []
  for source in iter_text_sources(root, month):
    relative_path = source.relative_to(root).as_posix()
    target = target_root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    copied.append(CopiedTextFile(source=source, relative_path=relative_path, target=target))
  return copied


def read_text(path: Path) -> str:
  try:
    return path.read_text(encoding="utf-8").strip()
  except UnicodeDecodeError:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def srt_to_plain_text(path: Path) -> str:
  lines: list[str] = []
  previous = ""
  for raw_line in read_text(path).splitlines():
    line = raw_line.strip()
    if not line:
      continue
    if line.isdigit():
      continue
    if "-->" in line:
      continue
    if line == previous:
      continue
    lines.append(line)
    previous = line
  return "\n".join(lines).strip()


def subtitle_score(path: Path) -> int:
  name = path.name.lower()
  score = 0
  if "no-fillers" in name:
    score += 100
  if "corrected" in name:
    score += 90
  if "reviewed" in name:
    score += 80
  if "transcribed" in name:
    score += 70
  if "tiny_full" in name:
    score += 20
  if "raw" in name:
    score -= 20
  if "scripted" in name:
    score -= 50
  if name.startswith("detail_"):
    score -= 10
  return score


def select_best_subtitle(root: Path, date: str) -> Path | None:
  subtitles_dir = root / "04_videos" / date / "subtitles"
  if not subtitles_dir.exists():
    return None
  candidates = [path for path in subtitles_dir.glob("*.srt") if path.is_file()]
  if not candidates:
    return None
  return sorted(candidates, key=lambda path: (subtitle_score(path), path.name), reverse=True)[0]


def list_month_dates(root: Path, month: str) -> list[str]:
  dates: set[str] = set()
  for source_root in ["01_inbox", "02_scripts", "04_videos", "06_logs"]:
    base = root / source_root
    if not base.exists():
      continue
    for path in base.rglob("*"):
      for match in DATE_RE.findall(path.as_posix()):
        if match.startswith(month):
          dates.add(match)
  return sorted(dates)


def append_source_block(lines: list[str], heading: str, path: Path | None, root: Path) -> None:
  lines.extend([f"### {heading}", ""])
  if not path or not path.exists():
    lines.extend(["未找到。", ""])
    return
  lines.extend([f"> Source: `{path.relative_to(root).as_posix()}`", ""])
  lines.extend(["```text", read_text(path), "```", ""])


def write_manuscripts(root: Path, month: str, archive_dir: Path) -> tuple[Path, dict[str, str]]:
  target = archive_dir / "text-manuscripts.md"
  selected_subtitles: dict[str, str] = {}
  lines = [
    f"# {month} 文字稿总汇",
    "",
    "本文件用于在删除视频媒体文件前保留文字资产。它汇总原始口述、口播脚本和最终字幕转写稿。",
    "",
  ]

  for date in list_month_dates(root, month):
    inbox_path = root / "01_inbox" / f"{date}.md"
    script_path = root / "02_scripts" / f"{date}.md"
    subtitle_path = select_best_subtitle(root, date)
    if subtitle_path:
      selected_subtitles[date] = subtitle_path.relative_to(root).as_posix()

    lines.extend([f"## {date}", ""])
    append_source_block(lines, "原始口述", inbox_path, root)
    append_source_block(lines, "口播脚本", script_path, root)

    lines.extend(["### 最终字幕转写", ""])
    if subtitle_path:
      lines.extend([
        f"> Source: `{subtitle_path.relative_to(root).as_posix()}`",
        "",
        "```text",
        srt_to_plain_text(subtitle_path),
        "```",
        "",
      ])
    else:
      lines.extend(["未找到最终字幕。", ""])

  target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
  return target, selected_subtitles


def write_index(
  root: Path,
  month: str,
  archive_dir: Path,
  copied: list[CopiedTextFile],
  manuscript_path: Path,
  selected_subtitles: dict[str, str],
) -> Path:
  target = archive_dir / "text-assets-index.md"
  by_root: dict[str, int] = {}
  for item in copied:
    top = item.relative_path.split("/", 1)[0]
    by_root[top] = by_root.get(top, 0) + 1

  lines = [
    f"# {month} 文字资产归档索引",
    "",
    "用途：删除视频媒体文件前，确认文字稿、字幕、脚本、日志已经进入月度归档。",
    "",
    "## 归档结果",
    "",
    f"- 文字稿总汇：`{manuscript_path.relative_to(archive_dir).as_posix()}`",
    f"- 已复制文字资产：{len(copied)} 个",
    "- 视频媒体文件：未复制，未删除。",
    "",
    "## 按来源统计",
    "",
    "| 来源 | 文件数 |",
    "| --- | ---: |",
  ]
  for source, count in sorted(by_root.items()):
    lines.append(f"| `{source}` | {count} |")

  lines.extend([
    "",
    "## 选用的最终字幕",
    "",
    "| 日期 | 字幕源 |",
    "| --- | --- |",
  ])
  for date, subtitle in selected_subtitles.items():
    lines.append(f"| {date} | `{subtitle}` |")

  lines.extend([
    "",
    "## 已复制文字文件",
    "",
    "| 原路径 | 归档路径 |",
    "| --- | --- |",
  ])
  for item in copied:
    target_relative = item.target.relative_to(archive_dir).as_posix()
    lines.append(f"| `{item.relative_path}` | `{target_relative}` |")

  lines.extend([
    "",
    "## 删除视频前确认",
    "",
    "- 本归档只保证文字资产，不包含 MP4/MOV/WebM。",
    "- 删除视频前先查看 `video-files.md`。",
    "- Codex 不批量删除视频；如需删除，只能逐个明确路径确认。",
    "",
  ])

  target.write_text("\n".join(lines), encoding="utf-8")
  return target


def run(month: str) -> None:
  root = project_root()
  archive_dir = root / "16_monthly_archive" / month
  archive_dir.mkdir(parents=True, exist_ok=True)

  copied = copy_text_files(root, month, archive_dir)
  manuscript_path, selected_subtitles = write_manuscripts(root, month, archive_dir)
  index_path = write_index(root, month, archive_dir, copied, manuscript_path, selected_subtitles)

  print(f"text_archive={archive_dir.relative_to(root)}")
  print(f"manuscripts={manuscript_path.relative_to(root)}")
  print(f"text_assets_index={index_path.relative_to(root)}")
  print(f"copied_text_files={len(copied)}")
  print(f"selected_subtitles={len(selected_subtitles)}")
  print("No video files were copied or deleted.")


def main() -> None:
  parser = argparse.ArgumentParser(description="Collect text assets before deleting video media files.")
  parser.add_argument("month", help="Month in YYYY-MM format")
  args = parser.parse_args()
  run(ensure_month(args.month))


if __name__ == "__main__":
  main()
