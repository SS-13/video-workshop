#!/usr/bin/env python3
"""Archive an external video link for learning with yt-dlp."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi"}
SUBTITLE_EXTENSIONS = {".srt", ".vtt"}


def projectRoot() -> Path:
  return Path(__file__).resolve().parents[4]


def todayString() -> str:
  return datetime.now().strftime("%Y-%m-%d")


def slugify(value: str) -> str:
  text = value.strip().lower()
  text = re.sub(r"https?://", "", text)
  text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text)
  text = re.sub(r"-+", "-", text).strip("-")
  return text[:60] or "video"


def slugFromUrl(url: str) -> str:
  parsed = urlparse(url)
  pathBits = [bit for bit in parsed.path.split("/") if bit]
  candidate = pathBits[-1] if pathBits else parsed.netloc
  return slugify(candidate)


def ensureHttpUrl(url: str) -> None:
  parsed = urlparse(url)
  if parsed.scheme not in {"http", "https"} or not parsed.netloc:
    raise SystemExit(f"Invalid URL: {url}")


def ytDlpCommand() -> Optional[List[str]]:
  binary = shutil.which("yt-dlp")
  if binary:
    return [binary]
  try:
    import yt_dlp  # noqa: F401
  except ImportError:
    return None
  return [sys.executable, "-m", "yt_dlp"]


def runCommand(cmd: List[str], cwd: Path) -> int:
  print("Running:", " ".join(cmd))
  return subprocess.run(cmd, cwd=str(cwd), check=False).returncode


def findFiles(baseDir: Path, extensions: set[str]) -> List[Path]:
  return sorted(
    [
      path
      for path in baseDir.iterdir()
      if path.is_file() and path.suffix.lower() in extensions and not path.name.endswith(".part")
    ],
    key=lambda path: path.stat().st_mtime,
    reverse=True,
  )


def parseSrt(path: Path) -> str:
  lines: List[str] = []
  seenBlank = False
  for rawLine in path.read_text(encoding="utf-8", errors="ignore").splitlines():
    line = rawLine.strip()
    if not line:
      if not seenBlank and lines:
        lines.append("")
      seenBlank = True
      continue
    if line.isdigit():
      continue
    if "-->" in line:
      continue
    lines.append(line)
    seenBlank = False
  return "\n".join(lines).strip()


def parseVtt(path: Path) -> str:
  lines: List[str] = []
  for rawLine in path.read_text(encoding="utf-8", errors="ignore").splitlines():
    line = rawLine.strip()
    if not line or line == "WEBVTT" or line.startswith(("Kind:", "Language:", "NOTE")):
      continue
    if "-->" in line or re.match(r"^\d+$", line):
      continue
    line = re.sub(r"<[^>]+>", "", line)
    if line:
      lines.append(line)
  return "\n".join(lines).strip()


def writeTranscript(itemDir: Path, subtitleFiles: List[Path]) -> Path:
  subtitlesDir = itemDir / "subtitles"
  subtitlesDir.mkdir(exist_ok=True)
  transcriptPath = subtitlesDir / "transcript.md"
  if not subtitleFiles:
    transcriptPath.write_text(
      "# Transcript\n\n未找到可用字幕。需要逐字稿时，下一步应对本地视频执行语音转写。\n",
      encoding="utf-8",
    )
    return transcriptPath

  source = subtitleFiles[0]
  transcript = parseSrt(source) if source.suffix.lower() == ".srt" else parseVtt(source)
  transcriptPath.write_text(
    f"# Transcript\n\nSource subtitle: `{source.name}`\n\n{transcript}\n",
    encoding="utf-8",
  )
  return transcriptPath


def writeSourceJson(itemDir: Path, payload: dict) -> Path:
  sourcePath = itemDir / "source.json"
  sourcePath.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  return sourcePath


def writeSummaryTemplate(itemDir: Path, url: str, title: Optional[str]) -> Path:
  summaryPath = itemDir / "summary.md"
  if summaryPath.exists():
    return summaryPath
  summaryPath.write_text(
    "\n".join(
      [
        "# 视频学习总结",
        "",
        f"- 标题：{title or '待补充'}",
        f"- 链接：{url}",
        "",
        "## 核心观点",
        "",
        "- 待基于逐字稿整理。",
        "",
        "## 可学习的方法",
        "",
        "- 待整理。",
        "",
        "## 可迁移到我的内容工作流",
        "",
        "- 待整理。",
        "",
        "## 值得复看的时间点",
        "",
        "- 待整理。",
        "",
      ]
    ),
    encoding="utf-8",
  )
  return summaryPath


def writeNotesTemplate(itemDir: Path) -> Path:
  notesPath = itemDir / "notes.md"
  if notesPath.exists():
    return notesPath
  notesPath.write_text(
    "# 学习笔记\n\n## 我为什么收藏它\n\n- 待补充。\n\n## 画面/结构/表达拆解\n\n- 待补充。\n",
    encoding="utf-8",
  )
  return notesPath


def appendLinksIndex(root: Path, date: str, title: str | None, url: str, itemDir: Path) -> None:
  linksPath = root / "links.md"
  if not linksPath.exists():
    linksPath.write_text("# 视频学习链接\n\n| 日期 | 标题 | 链接 | 归档 |\n| --- | --- | --- | --- |\n", encoding="utf-8")
  current = linksPath.read_text(encoding="utf-8")
  if url in current:
    return
  relativeDir = itemDir.relative_to(root)
  safeTitle = (title or relativeDir.name).replace("|", "/")
  with linksPath.open("a", encoding="utf-8") as file:
    file.write(f"| {date} | {safeTitle} | {url} | `{relativeDir}` |\n")


def buildParser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="Archive an external video link into 18_learning.")
  parser.add_argument("url", help="Video URL to archive")
  parser.add_argument("--title", help="Optional human title for index and folder slug")
  parser.add_argument("--date", default=todayString(), help="Archive date, default: today")
  parser.add_argument("--slug", help="Optional folder slug")
  parser.add_argument("--root", default=str(projectRoot() / "18_learning"), help="Learning archive root")
  parser.add_argument("--playlist", action="store_true", help="Allow playlist download")
  parser.add_argument("--skip-video", action="store_true", help="Download metadata and subtitles only")
  parser.add_argument("--cookies-from-browser", help="Optional browser name, only use with user approval")
  return parser


def main() -> int:
  args = buildParser().parse_args()
  ensureHttpUrl(args.url)

  ytDlp = ytDlpCommand()
  if not ytDlp:
    print("Missing yt-dlp. Install with: python3 -m pip install -U yt-dlp", file=sys.stderr)
    return 2

  root = Path(args.root).expanduser().resolve()
  root.mkdir(parents=True, exist_ok=True)
  itemSlug = slugify(args.slug or args.title or slugFromUrl(args.url))
  itemDir = root / f"{args.date}_{itemSlug}"
  itemDir.mkdir(parents=True, exist_ok=True)

  outputTemplate = str(itemDir / "%(title).200B [%(id)s].%(ext)s")
  cmd = [
    *ytDlp,
    "--write-info-json",
    "--write-subs",
    "--write-auto-subs",
    "--sub-langs",
    "zh.*,en.*",
    "--convert-subs",
    "srt",
    "--merge-output-format",
    "mp4",
    "-o",
    outputTemplate,
  ]
  if not args.playlist:
    cmd.append("--no-playlist")
  if args.skip_video:
    cmd.append("--skip-download")
  if args.cookies_from_browser:
    cmd.extend(["--cookies-from-browser", args.cookies_from_browser])
  cmd.append(args.url)

  exitCode = runCommand(cmd, projectRoot())
  infoFiles = findFiles(itemDir, {".json"})
  subtitleFiles = findFiles(itemDir, SUBTITLE_EXTENSIONS)
  videoFiles = findFiles(itemDir, VIDEO_EXTENSIONS)
  transcriptPath = writeTranscript(itemDir, subtitleFiles)
  summaryPath = writeSummaryTemplate(itemDir, args.url, args.title)
  notesPath = writeNotesTemplate(itemDir)
  sourcePath = writeSourceJson(
    itemDir,
    {
      "url": args.url,
      "title": args.title,
      "date": args.date,
      "slug": itemSlug,
      "yt_dlp_exit_code": exitCode,
      "metadata_files": [path.name for path in infoFiles],
      "subtitle_files": [path.name for path in subtitleFiles],
      "video_files": [path.name for path in videoFiles],
      "transcript": str(transcriptPath.relative_to(itemDir)),
      "summary": str(summaryPath.relative_to(itemDir)),
      "notes": str(notesPath.relative_to(itemDir)),
    },
  )
  appendLinksIndex(root, args.date, args.title, args.url, itemDir)

  print(f"Archive folder: {itemDir}")
  print(f"Source: {sourcePath}")
  print(f"Transcript: {transcriptPath}")
  print(f"Summary: {summaryPath}")
  return exitCode


if __name__ == "__main__":
  raise SystemExit(main())
