from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import statistics


FFPROBE_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffprobe")
TIME_RE = re.compile(
  r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+"
  r"(?P<end>\d{2}:\d{2}:\d{2},\d{3})"
)


def ffprobe_bin():
  return os.environ.get("FFPROBE_BIN") or (str(FFPROBE_FULL) if FFPROBE_FULL.exists() else "ffprobe")


def seconds(value):
  hours = int(value[0:2])
  minutes = int(value[3:5])
  whole = int(value[6:8])
  millis = int(value[9:12])
  return hours * 3600 + minutes * 60 + whole + millis / 1000


def probe_duration(path):
  result = subprocess.run(
    [
      ffprobe_bin(),
      "-v",
      "error",
      "-show_entries",
      "format=duration",
      "-of",
      "json",
      str(path),
    ],
    check=True,
    capture_output=True,
    text=True,
  )
  return float(json.loads(result.stdout)["format"]["duration"])


def parse_srt(path):
  text = path.read_text(encoding="utf-8-sig").strip()
  blocks = []
  if not text:
    return blocks

  for raw in re.split(r"\n\s*\n", text):
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    match = next((TIME_RE.search(line) for line in lines if "-->" in line), None)
    if not match:
      continue
    time_index = next(index for index, line in enumerate(lines) if "-->" in line)
    blocks.append({
      "start": seconds(match.group("start")),
      "end": seconds(match.group("end")),
      "text": "".join(lines[time_index + 1:]),
    })
  return blocks


def parse_words(path):
  data = json.loads(path.read_text(encoding="utf-8"))
  words = []
  for segment in data.get("segments", []):
    for word in segment.get("words", []):
      start = word.get("start")
      end = word.get("end")
      text = str(word.get("word", "")).strip()
      if start is None or end is None or end <= start or not text:
        continue
      words.append({"start": float(start), "end": float(end), "text": text})
  return words


def percentile(values, ratio):
  if not values:
    return 0.0
  ordered = sorted(values)
  index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
  return ordered[index]


def check_word_alignment(blocks, words, max_boundary_delta, max_global_offset, max_unmatched):
  errors = []
  unmatched = []
  start_deltas = []
  end_deltas = []
  signed_start_offsets = []

  for index, block in enumerate(blocks, 1):
    overlapping = [
      word for word in words
      if word["end"] > block["start"] + 0.001 and word["start"] < block["end"] - 0.001
    ]
    if not overlapping:
      unmatched.append(index)
      continue

    first_word = overlapping[0]
    last_word = overlapping[-1]
    start_delta = abs(block["start"] - first_word["start"])
    end_delta = abs(block["end"] - last_word["end"])
    start_deltas.append(start_delta)
    end_deltas.append(end_delta)
    signed_start_offsets.append(block["start"] - first_word["start"])

    if start_delta > max_boundary_delta:
      errors.append(f"audio_start_mismatch:{index}:{start_delta:.3f}")
    if end_delta > max_boundary_delta:
      errors.append(f"audio_end_mismatch:{index}:{end_delta:.3f}")

  if len(unmatched) > max_unmatched:
    errors.append(f"unmatched_audio_cues:{len(unmatched)}")

  global_offset = statistics.median(signed_start_offsets) if signed_start_offsets else 0.0
  if abs(global_offset) > max_global_offset:
    errors.append(f"global_audio_offset:{global_offset:.3f}")

  return errors, {
    "wordCount": len(words),
    "matchedCueCount": len(blocks) - len(unmatched),
    "unmatchedCueIndexes": unmatched,
    "p95StartDelta": round(percentile(start_deltas, 0.95), 3),
    "p95EndDelta": round(percentile(end_deltas, 0.95), 3),
    "globalStartOffset": round(global_offset, 3),
  }


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("srt")
  parser.add_argument("--video", required=True)
  parser.add_argument("--max-chars", type=int, default=28)
  parser.add_argument("--duration-tolerance", type=float, default=0.4)
  parser.add_argument("--word-json")
  parser.add_argument("--max-boundary-delta", type=float, default=0.45)
  parser.add_argument("--max-global-offset", type=float, default=0.25)
  parser.add_argument("--max-unmatched", type=int, default=0)
  parser.add_argument("--report")
  args = parser.parse_args()

  srt_path = Path(args.srt)
  video_path = Path(args.video)
  duration = probe_duration(video_path)
  blocks = parse_srt(srt_path)
  errors = []

  if not blocks:
    errors.append("empty_srt")

  previous_end = -1.0
  for index, block in enumerate(blocks, 1):
    if block["start"] < previous_end - 0.001:
      errors.append(f"overlap_or_not_monotonic:{index}")
    if block["end"] <= block["start"]:
      errors.append(f"non_positive_duration:{index}")
    if block["end"] > duration + args.duration_tolerance:
      errors.append(f"beyond_video_duration:{index}")
    if len(block["text"]) > args.max_chars:
      errors.append(f"too_long:{index}:{len(block['text'])}")
    previous_end = block["end"]

  alignment = None
  if args.word_json:
    word_json_path = Path(args.word_json)
    words = parse_words(word_json_path)
    alignment_errors, alignment = check_word_alignment(
      blocks,
      words,
      args.max_boundary_delta,
      args.max_global_offset,
      args.max_unmatched,
    )
    errors.extend(alignment_errors)

  print(f"srt={srt_path}")
  print(f"video={video_path}")
  print(f"video_duration={duration:.3f}")
  print(f"blocks={len(blocks)}")
  print(f"errors={len(errors)}")
  if alignment:
    print(f"word_count={alignment['wordCount']}")
    print(f"matched_cues={alignment['matchedCueCount']}")
    print(f"unmatched_cues={len(alignment['unmatchedCueIndexes'])}")
    print(f"p95_start_delta={alignment['p95StartDelta']:.3f}")
    print(f"p95_end_delta={alignment['p95EndDelta']:.3f}")
    print(f"global_start_offset={alignment['globalStartOffset']:.3f}")
  for error in errors[:30]:
    print(f"ERROR\t{error}")

  if args.report:
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
      json.dumps(
        {
          "srt": str(srt_path),
          "video": str(video_path),
          "videoDuration": round(duration, 3),
          "cueCount": len(blocks),
          "errors": errors,
          "alignment": alignment,
        },
        ensure_ascii=False,
        indent=2,
      ) + "\n",
      encoding="utf-8",
    )

  if errors:
    raise SystemExit(1)


if __name__ == "__main__":
  main()
