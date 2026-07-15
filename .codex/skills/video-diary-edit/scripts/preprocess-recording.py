from pathlib import Path
import argparse
import json
import os
import re
import subprocess

from workflow_state import content_media_dir, file_fingerprint


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".MP4", ".MOV", ".M4V"}
DEFAULT_MIN_OUTRO_DURATION = 1.0
DEFAULT_END_TOLERANCE = 0.65
DEFAULT_TAIL_WINDOW = 10.0
FFMPEG_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffmpeg")
FFPROBE_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffprobe")


def natural_key(path):
  return path.name.lower()


def find_recordings(root, date, content_type="video-diary", sequence="001"):
  recording_dir = content_media_dir(root, "03_recordings", date, content_type, sequence)
  if not recording_dir.exists():
    raise SystemExit(f"Missing recording directory: {recording_dir}")

  videos = sorted(
    [path for path in recording_dir.iterdir() if path.suffix in VIDEO_EXTENSIONS],
    key=natural_key,
  )
  if not videos:
    raise SystemExit(f"No video files found in {recording_dir}")

  return videos


def find_default_input(root, date):
  return find_recordings(root, date)[0]


def run_command(command):
  return subprocess.run(
    command,
    text=True,
    capture_output=True,
    check=False,
  )


def ffmpeg_bin():
  return os.environ.get("FFMPEG_BIN") or (str(FFMPEG_FULL) if FFMPEG_FULL.exists() else "ffmpeg")


def ffprobe_bin():
  return os.environ.get("FFPROBE_BIN") or (str(FFPROBE_FULL) if FFPROBE_FULL.exists() else "ffprobe")


def probe_duration(input_path):
  command = [
    ffprobe_bin(),
    "-v",
    "error",
    "-show_entries",
    "format=duration",
    "-of",
    "json",
    str(input_path),
  ]
  result = run_command(command)
  if result.returncode != 0:
    raise SystemExit(result.stderr.strip() or "ffprobe failed")

  data = json.loads(result.stdout)
  return float(data["format"]["duration"])


def detect_black_segments(input_path, duration, tail_window):
  scan_start = max(0.0, duration - tail_window)
  scan_duration = max(0.0, duration - scan_start)
  command = [
    ffmpeg_bin(),
    "-hide_banner",
    "-ss",
    f"{scan_start:.3f}",
    "-i",
    str(input_path),
    "-t",
    f"{scan_duration:.3f}",
    "-vf",
    "blackdetect=d=0.2:pic_th=0.95",
    "-an",
    "-f",
    "null",
    "-",
  ]
  result = run_command(command)
  if result.returncode != 0:
    raise SystemExit(result.stderr.strip() or "ffmpeg blackdetect failed")

  pattern = re.compile(
    r"black_start:(?P<start>[0-9.]+)\s+"
    r"black_end:(?P<end>[0-9.]+)\s+"
    r"black_duration:(?P<duration>[0-9.]+)"
  )
  segments = []
  for match in pattern.finditer(result.stderr):
    start = float(match.group("start"))
    end = float(match.group("end"))
    if end <= scan_duration + 1.0:
      start += scan_start
      end += scan_start
    segments.append({
      "start": start,
      "end": end,
      "duration": float(match.group("duration")),
    })

  return segments


def find_terminal_black_outro(segments, duration, min_outro_duration, end_tolerance):
  candidates = []
  for segment in segments:
    if segment["duration"] < min_outro_duration:
      continue
    if segment["end"] < duration - end_tolerance:
      continue
    candidates.append(segment)

  if not candidates:
    return None

  return sorted(candidates, key=lambda segment: segment["start"])[-1]


def trim_to_time(input_path, output_path, trim_end):
  output_path.parent.mkdir(parents=True, exist_ok=True)
  command = [
    ffmpeg_bin(),
    "-hide_banner",
    "-y",
    "-i",
    str(input_path),
    "-t",
    f"{trim_end:.3f}",
    "-map",
    "0",
    "-c",
    "copy",
    "-movflags",
    "+faststart",
    str(output_path),
  ]
  result = run_command(command)
  if result.returncode != 0:
    raise SystemExit(result.stderr.strip() or "ffmpeg trim failed")


def write_report(report_path, report):
  report_path.parent.mkdir(parents=True, exist_ok=True)
  report_path.write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
  )


def preprocess_one(
  input_path,
  output_path,
  report_path,
  min_outro_duration,
  end_tolerance,
  tail_window,
  force,
):
  input_fingerprint = file_fingerprint(input_path)
  if not force and report_path.exists():
    cached = json.loads(report_path.read_text(encoding="utf-8"))
    usable_input = Path(cached.get("usableInput", ""))
    if (
      cached.get("inputFingerprint") == input_fingerprint
      and float(cached.get("tailWindow", tail_window)) == tail_window
      and usable_input.exists()
    ):
      cached["cacheHit"] = True
      return cached

  duration = probe_duration(input_path)
  black_segments = detect_black_segments(input_path, duration, tail_window)
  outro = find_terminal_black_outro(
    black_segments,
    duration,
    min_outro_duration,
    end_tolerance,
  )

  report = {
    "input": str(input_path),
    "output": str(output_path) if outro else None,
    "usableInput": str(output_path) if outro else str(input_path),
    "duration": duration,
    "inputFingerprint": input_fingerprint,
    "tailWindow": tail_window,
    "blackSegments": black_segments,
    "terminalBlackOutro": outro,
    "trimmed": bool(outro),
  }

  if outro:
    trim_end = max(0.0, outro["start"])
    trim_to_time(input_path, output_path, trim_end)
    report["trimEnd"] = trim_end
    report["removedDuration"] = max(0.0, duration - trim_end)

  write_report(report_path, report)

  return report


def write_manifest(root, date, reports, content_type="video-diary", sequence="001"):
  manifest_path = content_media_dir(root, "04_videos", date, content_type, sequence) / "preprocessed" / "preprocess_manifest.json"
  manifest = {
    "date": date,
    "processedCount": len(reports),
    "trimmedCount": sum(1 for report in reports if report["trimmed"]),
    "items": reports,
  }
  write_report(manifest_path, manifest)
  return manifest_path


def print_report(report, report_path):
  print(f"input={report['input']}")
  print(f"report={report_path}")
  print(f"trimmed={str(report['trimmed']).lower()}")
  if report["terminalBlackOutro"]:
    print(f"output={report['output']}")
    print(f"trim_end={report['trimEnd']:.3f}")
    print(f"removed_duration={report['removedDuration']:.3f}")


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--date", required=True)
  parser.add_argument("--content-type", "--column", dest="content_type", default="video-diary")
  parser.add_argument("--sequence", default="001")
  parser.add_argument("--input")
  parser.add_argument("--output")
  parser.add_argument("--report")
  parser.add_argument("--all", action="store_true")
  parser.add_argument("--min-outro-duration", type=float, default=DEFAULT_MIN_OUTRO_DURATION)
  parser.add_argument("--end-tolerance", type=float, default=DEFAULT_END_TOLERANCE)
  parser.add_argument("--tail-window", type=float, default=DEFAULT_TAIL_WINDOW)
  parser.add_argument("--force", action="store_true")
  args = parser.parse_args()

  root = Path.cwd()

  if args.all:
    if args.input or args.output or args.report:
      raise SystemExit("--all cannot be used with --input, --output, or --report.")

    reports = []
    workspace = content_media_dir(root, "04_videos", args.date, args.content_type, args.sequence)
    for input_path in find_recordings(root, args.date, args.content_type, args.sequence):
      output_path = workspace / "preprocessed" / f"{input_path.stem}_trimmed.mp4"
      report_path = workspace / "preprocessed" / f"{input_path.stem}_preprocess_report.json"
      report = preprocess_one(
        input_path,
        output_path,
        report_path,
        args.min_outro_duration,
        args.end_tolerance,
        args.tail_window,
        args.force,
      )
      reports.append(report)
      print_report(report, report_path)
      print("")

    manifest_path = write_manifest(root, args.date, reports, args.content_type, args.sequence)
    trimmed_count = sum(1 for report in reports if report["trimmed"])
    print(f"processed={len(reports)}")
    print(f"trimmed_count={trimmed_count}")
    print(f"manifest={manifest_path}")
    return

  input_path = Path(args.input) if args.input else find_default_input(root, args.date)
  if not input_path.is_absolute():
    input_path = root / input_path

  output_path = Path(args.output) if args.output else (
    content_media_dir(root, "04_videos", args.date, args.content_type, args.sequence) / "preprocessed" / f"{input_path.stem}_trimmed.mp4"
  )
  if not output_path.is_absolute():
    output_path = root / output_path

  report_path = Path(args.report) if args.report else (
    content_media_dir(root, "04_videos", args.date, args.content_type, args.sequence) / "preprocessed" / f"{input_path.stem}_preprocess_report.json"
  )
  if not report_path.is_absolute():
    report_path = root / report_path

  report = preprocess_one(
    input_path,
    output_path,
    report_path,
    args.min_outro_duration,
    args.end_tolerance,
    args.tail_window,
    args.force,
  )
  print_report(report, report_path)


if __name__ == "__main__":
  main()
