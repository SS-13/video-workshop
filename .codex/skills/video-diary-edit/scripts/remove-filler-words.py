from pathlib import Path
import argparse
import json
import os
import re
import shutil
import subprocess


FFMPEG_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffmpeg")
FFPROBE_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffprobe")
FILLER_PATTERN = re.compile(r"^(?:哎呀+|哎哟+|哎呦+|嗯+|呃+|啊+|额+|唔+|哎+|诶+|唉+)$")
LEADING_FILLER_PATTERN = re.compile(r"^(?:哎呀+|哎哟+|哎呦+|嗯+|呃+|啊+|额+|唔+|哎+|诶+|唉+)[，,、\s]*")
LEADING_FILLER_CAPTURE_PATTERN = re.compile(r"^(?P<filler>(?:哎呀+|哎哟+|哎呦+|嗯+|呃+|啊+|额+|唔+|哎+|诶+|唉+)[，,、\s]*)+")
INNER_FILLER_PATTERN = re.compile(r"(?P<filler>哎呀+|哎哟+|哎呦+|嗯+|呃+|啊+|额+|唔+|哎+|诶+|唉+)[，,、\s]*")
PUNCTUATION_PATTERN = re.compile(r"[，,。.!！?？、\s…~～]+")
TIME_PATTERN = re.compile(
  r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+"
  r"(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)


def resolve_path(root, value):
  path = Path(value)
  return path if path.is_absolute() else root / path


def ffmpeg_bin():
  return os.environ.get("FFMPEG_BIN") or (str(FFMPEG_FULL) if FFMPEG_FULL.exists() else "ffmpeg")


def ffprobe_bin():
  return os.environ.get("FFPROBE_BIN") or (str(FFPROBE_FULL) if FFPROBE_FULL.exists() else "ffprobe")


def run_command(command):
  result = subprocess.run(
    command,
    text=True,
    capture_output=True,
    check=False,
  )
  if result.returncode != 0:
    raise SystemExit(result.stderr.strip() or f"Command failed: {' '.join(command)}")
  return result


def seconds_from_timestamp(value):
  hours = int(value[0:2])
  minutes = int(value[3:5])
  seconds = int(value[6:8])
  millis = int(value[9:12])
  return hours * 3600 + minutes * 60 + seconds + millis / 1000


def timestamp_from_seconds(value):
  value = max(0, value)
  millis_total = int(round(value * 1000))
  hours = millis_total // 3600000
  millis_total %= 3600000
  minutes = millis_total // 60000
  millis_total %= 60000
  seconds = millis_total // 1000
  millis = millis_total % 1000
  return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def parse_srt(path):
  text = path.read_text(encoding="utf-8-sig").strip()
  if not text:
    return []

  blocks = []
  for raw_block in re.split(r"\n\s*\n", text):
    lines = [line.strip() for line in raw_block.splitlines() if line.strip()]
    if len(lines) < 2:
      continue

    time_line_index = 1 if "-->" in lines[1] else 0
    match = TIME_PATTERN.search(lines[time_line_index])
    if not match:
      continue

    block_text = "\n".join(lines[time_line_index + 1:]).strip()
    blocks.append({
      "index": len(blocks) + 1,
      "start": seconds_from_timestamp(match.group("start")),
      "end": seconds_from_timestamp(match.group("end")),
      "text": block_text,
    })

  return blocks


def normalize_text(text):
  return PUNCTUATION_PATTERN.sub("", text.strip())


def is_filler_only(text):
  normalized = normalize_text(text)
  if not normalized:
    return False
  return bool(FILLER_PATTERN.fullmatch(normalized))


def clean_caption_text(text):
  cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
  previous = None
  while cleaned != previous:
    previous = cleaned
    cleaned = LEADING_FILLER_PATTERN.sub("", cleaned).strip()

  cleaned = re.sub(r"\s+", " ", cleaned)
  cleaned = re.sub(r"^[，,、\s]+", "", cleaned)
  return cleaned.strip()


def leading_filler_cut_duration(text, block_duration, seconds_per_char, max_cut):
  single_line = " ".join(line.strip() for line in text.splitlines() if line.strip())
  match = LEADING_FILLER_CAPTURE_PATTERN.match(single_line)
  if not match:
    return 0.0

  cleaned = clean_caption_text(single_line)
  if not cleaned or cleaned == single_line:
    return 0.0

  filler_text = PUNCTUATION_PATTERN.sub("", match.group(0))
  if not filler_text:
    return 0.0

  estimate = len(filler_text) * seconds_per_char
  return max(0.0, min(estimate, max_cut, block_duration * 0.4))


def inner_filler_cut_intervals(text, block_start, block_duration, max_cut):
  single_line = " ".join(line.strip() for line in text.splitlines() if line.strip())
  normalized_length = max(1, len(PUNCTUATION_PATTERN.sub("", single_line)))
  seconds_per_char = block_duration / normalized_length
  intervals = []

  for match in INNER_FILLER_PATTERN.finditer(single_line):
    filler_text = PUNCTUATION_PATTERN.sub("", match.group("filler"))
    if not filler_text:
      continue
    # ponytail: ratio estimate; use word timestamps if this ever cuts meaningful speech.
    start = block_start + min(block_duration, match.start() * seconds_per_char)
    end = min(block_start + block_duration, start + min(max_cut, max(0.10, len(filler_text) * seconds_per_char)))
    if end > start:
      intervals.append((start, end, filler_text))

  return intervals


def merge_intervals(intervals, gap):
  if not intervals:
    return []

  merged = []
  for start, end in sorted(intervals):
    if not merged or start > merged[-1][1] + gap:
      merged.append([start, end])
    else:
      merged[-1][1] = max(merged[-1][1], end)

  return [(start, end) for start, end in merged if end > start]


def removed_before(time_value, cut_intervals):
  total = 0.0
  for start, end in cut_intervals:
    if time_value <= start:
      continue
    total += max(0.0, min(time_value, end) - start)
  return total


def build_outputs(
  blocks,
  pad_before,
  pad_after,
  merge_gap,
  min_cut_duration,
  leading_filler_seconds_per_char,
  max_leading_filler_cut,
  aggressive_fillers,
  max_inner_filler_cut,
):
  cut_candidates = []
  cleaned_blocks = []
  removed_blocks = []
  text_cleanups = []
  leading_filler_cuts = []
  inner_filler_cuts = []

  for block in blocks:
    text = block["text"]
    if is_filler_only(text):
      start = max(0.0, block["start"] - pad_before)
      end = max(start, block["end"] + pad_after)
      if end - start >= min_cut_duration:
        cut_candidates.append((start, end))
        removed_blocks.append({
          "index": block["index"],
          "start": block["start"],
          "end": block["end"],
          "text": text,
        })
      continue

    leading_cut = leading_filler_cut_duration(
      text,
      block["end"] - block["start"],
      leading_filler_seconds_per_char,
      max_leading_filler_cut,
    )
    if leading_cut >= min_cut_duration:
      cut_candidates.append((block["start"], block["start"] + leading_cut))
      leading_filler_cuts.append({
        "index": block["index"],
        "start": block["start"],
        "end": block["start"] + leading_cut,
        "duration": leading_cut,
        "text": text,
      })

    if aggressive_fillers:
      for start, end, filler_text in inner_filler_cut_intervals(
        text,
        block["start"],
        block["end"] - block["start"],
        max_inner_filler_cut,
      ):
        if end - start >= min_cut_duration:
          cut_candidates.append((start, end))
          inner_filler_cuts.append({
            "index": block["index"],
            "start": start,
            "end": end,
            "duration": end - start,
            "text": text,
            "filler": filler_text,
          })

    cleaned_text = clean_caption_text(text)
    if not cleaned_text:
      continue
    if cleaned_text != text:
      text_cleanups.append({
        "index": block["index"],
        "from": text,
        "to": cleaned_text,
      })
    cleaned_blocks.append({**block, "text": cleaned_text})

  cut_intervals = merge_intervals(cut_candidates, merge_gap)
  shifted_blocks = []
  for block in cleaned_blocks:
    start = block["start"] - removed_before(block["start"], cut_intervals)
    end = block["end"] - removed_before(block["end"], cut_intervals)
    if end <= start:
      continue
    shifted_blocks.append({
      "index": len(shifted_blocks) + 1,
      "start": start,
      "end": end,
      "text": block["text"],
    })

  return shifted_blocks, cut_intervals, removed_blocks, text_cleanups, leading_filler_cuts, inner_filler_cuts


def write_srt(path, blocks):
  path.parent.mkdir(parents=True, exist_ok=True)
  rows = []
  for block in blocks:
    rows.append(str(block["index"]))
    rows.append(f"{timestamp_from_seconds(block['start'])} --> {timestamp_from_seconds(block['end'])}")
    rows.append(block["text"])
    rows.append("")
  path.write_text("\n".join(rows).rstrip() + "\n", encoding="utf-8")


def probe_duration(path):
  result = run_command([
    ffprobe_bin(),
    "-v",
    "error",
    "-show_entries",
    "format=duration",
    "-of",
    "json",
    str(path),
  ])
  data = json.loads(result.stdout)
  return float(data["format"]["duration"])


def has_audio_stream(path):
  result = run_command([
    ffprobe_bin(),
    "-v",
    "error",
    "-select_streams",
    "a",
    "-show_entries",
    "stream=index",
    "-of",
    "json",
    str(path),
  ])
  data = json.loads(result.stdout)
  return bool(data.get("streams"))


def complement_intervals(cut_intervals, duration, min_keep_duration):
  keep = []
  cursor = 0.0
  for start, end in cut_intervals:
    start = max(0.0, min(duration, start))
    end = max(0.0, min(duration, end))
    if start - cursor >= min_keep_duration:
      keep.append((cursor, start))
    cursor = max(cursor, end)

  if duration - cursor >= min_keep_duration:
    keep.append((cursor, duration))

  return keep


def render_cut_video(input_path, output_path, cut_intervals, crf, preset):
  output_path.parent.mkdir(parents=True, exist_ok=True)
  if not cut_intervals:
    shutil.copy2(input_path, output_path)
    return

  duration = probe_duration(input_path)
  keep_intervals = complement_intervals(cut_intervals, duration, min_keep_duration=0.08)
  if not keep_intervals:
    raise SystemExit("No keep intervals left after filler removal.")

  audio_enabled = has_audio_stream(input_path)
  filter_parts = []
  concat_inputs = []
  for index, (start, end) in enumerate(keep_intervals):
    filter_parts.append(
      f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{index}]"
    )
    concat_inputs.append(f"[v{index}]")
    if audio_enabled:
      filter_parts.append(
        f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{index}]"
      )
      concat_inputs.append(f"[a{index}]")

  concat_suffix = f"concat=n={len(keep_intervals)}:v=1:a={1 if audio_enabled else 0}"
  concat_output = "[v][a]" if audio_enabled else "[v]"
  filter_parts.append("".join(concat_inputs) + concat_suffix + concat_output)

  command = [
    ffmpeg_bin(),
    "-hide_banner",
    "-y",
    "-i",
    str(input_path),
    "-filter_complex",
    ";".join(filter_parts),
    "-map",
    "[v]",
  ]

  if audio_enabled:
    command.extend(["-map", "[a]"])

  command.extend([
    "-c:v",
    "libx264",
    "-preset",
    preset,
    "-crf",
    crf,
    "-c:a",
    "aac",
    "-b:a",
    "192k",
    "-movflags",
    "+faststart",
    str(output_path),
  ])

  run_command(command)


def write_report(path, data):
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_input_srt(root, date):
  subtitle_dir = root / "04_videos" / date / "subtitles"
  candidates = [
    subtitle_dir / f"{date}_transcribed_corrected.srt",
    subtitle_dir / f"{date}_transcribed.srt",
  ]
  for candidate in candidates:
    if candidate.exists():
      return candidate
  raise SystemExit(f"No default SRT found in {subtitle_dir}")


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--date", required=True)
  parser.add_argument("--input-video")
  parser.add_argument("--input-srt")
  parser.add_argument("--output-video")
  parser.add_argument("--output-srt")
  parser.add_argument("--report")
  parser.add_argument("--pad-before", type=float, default=0.02)
  parser.add_argument("--pad-after", type=float, default=0.05)
  parser.add_argument("--merge-gap", type=float, default=0.08)
  parser.add_argument("--min-cut-duration", type=float, default=0.10)
  parser.add_argument("--leading-filler-seconds-per-char", type=float, default=0.22)
  parser.add_argument("--max-leading-filler-cut", type=float, default=0.45)
  parser.add_argument("--aggressive-fillers", action="store_true")
  parser.add_argument("--max-inner-filler-cut", type=float, default=0.35)
  parser.add_argument("--crf", default="18")
  parser.add_argument("--preset", default="veryfast")
  parser.add_argument("--dry-run", action="store_true")
  args = parser.parse_args()

  root = Path.cwd()
  input_srt = resolve_path(root, args.input_srt) if args.input_srt else default_input_srt(root, args.date)
  output_srt = resolve_path(root, args.output_srt) if args.output_srt else (
    root / "04_videos" / args.date / "subtitles" / f"{args.date}_transcribed_no-fillers.srt"
  )
  report_path = resolve_path(root, args.report) if args.report else (
    root / "04_videos" / args.date / "subtitles" / f"{args.date}_filler_removal_report.json"
  )

  blocks = parse_srt(input_srt)
  shifted_blocks, cut_intervals, removed_blocks, text_cleanups, leading_filler_cuts, inner_filler_cuts = build_outputs(
    blocks,
    args.pad_before,
    args.pad_after,
    args.merge_gap,
    args.min_cut_duration,
    args.leading_filler_seconds_per_char,
    args.max_leading_filler_cut,
    args.aggressive_fillers,
    args.max_inner_filler_cut,
  )

  input_video = resolve_path(root, args.input_video) if args.input_video else None
  output_video = resolve_path(root, args.output_video) if args.output_video else None
  if input_video and not output_video:
    output_video = root / "04_videos" / args.date / "preprocessed" / f"{input_video.stem}_no-fillers.mp4"

  report = {
    "date": args.date,
    "inputSrt": str(input_srt),
    "outputSrt": str(output_srt),
    "inputVideo": str(input_video) if input_video else None,
    "outputVideo": str(output_video) if output_video else None,
    "cutCount": len(cut_intervals),
    "removedDuration": round(sum(end - start for start, end in cut_intervals), 3),
    "cutIntervals": [
      {"start": round(start, 3), "end": round(end, 3), "duration": round(end - start, 3)}
      for start, end in cut_intervals
    ],
    "removedBlocks": removed_blocks,
    "leadingFillerCutCount": len(leading_filler_cuts),
    "leadingFillerCuts": [
      {
        **item,
        "start": round(item["start"], 3),
        "end": round(item["end"], 3),
        "duration": round(item["duration"], 3),
      }
      for item in leading_filler_cuts
    ],
    "innerFillerCutCount": len(inner_filler_cuts),
    "innerFillerCuts": [
      {
        **item,
        "start": round(item["start"], 3),
        "end": round(item["end"], 3),
        "duration": round(item["duration"], 3),
      }
      for item in inner_filler_cuts
    ],
    "textCleanupCount": len(text_cleanups),
    "textCleanups": text_cleanups,
    "dryRun": args.dry_run,
  }

  if not args.dry_run:
    write_srt(output_srt, shifted_blocks)
    if input_video:
      if not input_video.exists():
        raise SystemExit(f"Missing input video: {input_video}")
      render_cut_video(input_video, output_video, cut_intervals, args.crf, args.preset)

  write_report(report_path, report)

  print(f"input_srt={input_srt}")
  print(f"output_srt={output_srt}")
  print(f"report={report_path}")
  print(f"cut_count={len(cut_intervals)}")
  print(f"removed_duration={report['removedDuration']}")
  print(f"leading_filler_cut_count={len(leading_filler_cuts)}")
  print(f"inner_filler_cut_count={len(inner_filler_cuts)}")
  print(f"text_cleanup_count={len(text_cleanups)}")
  if input_video:
    print(f"input_video={input_video}")
    print(f"output_video={output_video}")


if __name__ == "__main__":
  main()
