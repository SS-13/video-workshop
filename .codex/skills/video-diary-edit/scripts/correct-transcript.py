from pathlib import Path
import argparse
import csv

from workflow_state import content_media_dir


PROJECT_DICTIONARY = Path("11_templates/关键词收集/字幕纠错词库.tsv")
PUBLIC_DICTIONARY = Path("00_system/defaults/transcript-corrections.tsv")


def read_replacements(path):
  replacements = []
  with path.open("r", encoding="utf-8-sig", newline="") as file:
    reader = csv.reader(file, delimiter="\t")
    for line_number, row in enumerate(reader, 1):
      if not row:
        continue

      source = row[0].strip()
      if not source or source.startswith("#"):
        continue

      if len(row) < 2 or not row[1].strip():
        raise SystemExit(f"Invalid replacement at {path}:{line_number}")

      replacements.append({
        "source": source,
        "target": row[1].strip(),
        "note": row[2].strip() if len(row) >= 3 else "",
      })

  return replacements


def read_dictionary_chain(paths):
  replacements = []
  used_paths = []
  for path in paths:
    if not path.exists():
      continue
    replacements.extend(read_replacements(path))
    used_paths.append(path)

  return replacements, used_paths


def resolve_path(root, value):
  path = Path(value)
  return path if path.is_absolute() else root / path


def find_default_input(root, date, content_type="video-diary", sequence="001"):
  subtitle_dir = content_media_dir(root, "04_videos", date, content_type, sequence) / "subtitles"
  candidates = [
    subtitle_dir / f"{date}_transcribed_raw.srt",
    subtitle_dir / f"{date}_transcribed.srt",
  ]
  candidates.extend(sorted(
    subtitle_dir.glob("*_trimmed.srt"),
    key=lambda path: path.stat().st_mtime,
    reverse=True,
  ))

  for candidate in candidates:
    if candidate.exists():
      return candidate

  raise SystemExit(f"No transcript SRT found in {subtitle_dir}")


def apply_replacements(text, replacements):
  stats = []
  updated = text

  for replacement in replacements:
    source = replacement["source"]
    target = replacement["target"]
    count = updated.count(source)
    if count:
      updated = updated.replace(source, target)
    stats.append({
      **replacement,
      "count": count,
    })

  return updated, stats


def write_report(path, date, input_path, output_path, dictionary_paths, stats, dry_run):
  changed = [item for item in stats if item["count"]]
  total = sum(item["count"] for item in changed)
  rows = [
    f"# {date} 字幕纠错报告",
    "",
    f"- 输入：`{input_path}`",
    f"- 输出：`{output_path}`",
    f"- 词典：{', '.join(f'`{item}`' for item in dictionary_paths) or '未配置，原样输出'}",
    f"- 模式：{'dry-run' if dry_run else 'write'}",
    f"- 命中替换：{len(changed)} 项 / {total} 次",
    "",
    "| 原词 | 修正为 | 次数 | 备注 |",
    "| --- | --- | ---: | --- |",
  ]

  if changed:
    for item in changed:
      rows.append(f"| {item['source']} | {item['target']} | {item['count']} | {item['note']} |")
  else:
    rows.append("| - | - | 0 | 未命中词典 |")

  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("date", nargs="?")
  parser.add_argument("--date", dest="date_flag")
  parser.add_argument("--content-type", "--column", dest="content_type", default="video-diary")
  parser.add_argument("--sequence", default="001")
  parser.add_argument("--input")
  parser.add_argument("--output")
  parser.add_argument("--dictionary", action="append")
  parser.add_argument("--report")
  parser.add_argument("--promote", action="store_true")
  parser.add_argument("--dry-run", action="store_true")
  args = parser.parse_args()

  date = args.date_flag or args.date
  if not date:
    raise SystemExit("Usage: python3 .codex/skills/video-diary-edit/scripts/correct-transcript.py YYYY-MM-DD [--input path] [--promote]")

  root = Path.cwd()
  dictionary_paths = (
    [resolve_path(root, item) for item in args.dictionary]
    if args.dictionary
    else [
      resolve_path(root, PROJECT_DICTIONARY),
      resolve_path(root, PUBLIC_DICTIONARY),
    ]
  )

  input_path = resolve_path(root, args.input) if args.input else find_default_input(
    root, date, args.content_type, args.sequence
  )
  subtitle_dir = content_media_dir(root, "04_videos", date, args.content_type, args.sequence) / "subtitles"
  if not input_path.exists():
    raise SystemExit(f"Missing transcript SRT: {input_path}")

  output_path = (
    resolve_path(root, args.output)
    if args.output
    else subtitle_dir / f"{date}_transcribed_corrected.srt"
  )
  report_path = (
    resolve_path(root, args.report)
    if args.report
    else subtitle_dir / f"{date}_transcript_corrections.md"
  )

  replacements, used_dictionary_paths = read_dictionary_chain(dictionary_paths)
  text = input_path.read_text(encoding="utf-8-sig")
  corrected, stats = apply_replacements(text, replacements)

  if not args.dry_run:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(corrected, encoding="utf-8")
    if args.promote:
      promoted_path = subtitle_dir / f"{date}_transcribed.srt"
      if promoted_path != output_path:
        promoted_path.write_text(corrected, encoding="utf-8")

  write_report(
    report_path,
    date,
    input_path.relative_to(root) if input_path.is_relative_to(root) else input_path,
    output_path.relative_to(root) if output_path.is_relative_to(root) else output_path,
    [
      path.relative_to(root) if path.is_relative_to(root) else path
      for path in used_dictionary_paths
    ],
    stats,
    args.dry_run,
  )

  changed = [item for item in stats if item["count"]]
  print(f"input={input_path}")
  print(f"output={output_path}")
  print(f"report={report_path}")
  print("dictionaries=" + ",".join(str(path) for path in used_dictionary_paths))
  print(f"replacement_items={len(changed)}")
  print(f"replacement_total={sum(item['count'] for item in changed)}")
  if args.promote and not args.dry_run:
    print(f"promoted={subtitle_dir / f'{date}_transcribed.srt'}")


if __name__ == "__main__":
  main()
