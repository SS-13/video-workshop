from pathlib import Path
import argparse
import json
import os
import shlex
import subprocess
import sys
import time


SCRIPT_DIR = Path(__file__).resolve().parent
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".MP4", ".MOV", ".M4V"}
FFPROBE_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffprobe")


def resolve_path(root, value):
  path = Path(value)
  return path if path.is_absolute() else root / path


def format_command(command):
  return shlex.join(str(item) for item in command)


def ffprobe_bin():
  return os.environ.get("FFPROBE_BIN") or (str(FFPROBE_FULL) if FFPROBE_FULL.exists() else "ffprobe")


def run_step(name, command, stages):
  started = time.time()
  print(f"RUN\t{name}\t{format_command(command)}")
  subprocess.run([str(item) for item in command], check=True)
  finished = time.time()
  elapsed = round(finished - started, 3)
  stages.append({
    "name": name,
    "elapsedSeconds": elapsed,
    "command": [str(item) for item in command],
  })
  print(f"DONE\t{name}\t{elapsed:.3f}s")


def run_capture(command):
  result = subprocess.run(
    [str(item) for item in command],
    text=True,
    capture_output=True,
    check=True,
  )
  return result.stdout


def probe_duration(video_path):
  output = run_capture([
    ffprobe_bin(),
    "-v",
    "error",
    "-show_entries",
    "format=duration",
    "-of",
    "json",
    str(video_path),
  ])
  return float(json.loads(output)["format"]["duration"])


def read_manifest(root, date):
  manifest_path = root / "04_videos" / date / "preprocessed" / "preprocess_manifest.json"
  if not manifest_path.exists():
    raise SystemExit(f"Missing preprocess manifest: {manifest_path}")
  return json.loads(manifest_path.read_text(encoding="utf-8"))


def choose_usable_input(root, date, requested_input):
  manifest = read_manifest(root, date)
  items = manifest.get("items", [])
  if not items:
    raise SystemExit("Preprocess manifest has no items.")

  if requested_input:
    requested = resolve_path(root, requested_input).resolve()
    matches = [
      item for item in items
      if Path(item.get("input", "")).resolve() == requested
    ]
    if not matches:
      raise SystemExit(f"Requested input was not found in preprocess manifest: {requested}")
    item = matches[0]
  else:
    if len(items) != 1:
      raise SystemExit(
        f"Multiple recordings found for {date}. Rerun with --input and one explicit file path."
      )
    item = items[0]

  usable = Path(item["usableInput"])
  if not usable.is_absolute():
    usable = root / usable
  if not usable.exists():
    raise SystemExit(f"Missing usable input: {usable}")
  return usable


def default_output_path(root, date, mode):
  return root / "04_videos" / date / f"{date}_{mode}_ass_subtitled.mp4"


def print_dry_run(args):
  source = args.input or "USABLE_INPUT_FROM_PREPROCESS_MANIFEST"
  print(f"DRY RUN: {args.mode} deterministic edit route")
  if args.from_stage != "start":
    print(f"resume_from={args.from_stage}")
    print(f"video_input={args.video_input}")
    if args.srt_input:
      print(f"srt_input={args.srt_input}")
    if args.ass_input:
      print(f"ass_input={args.ass_input}")
    return
  print(f"1. check deps: {SCRIPT_DIR / 'check-edit-deps.py'}")
  print(f"2. preprocess: --date {args.date} --all")
  print(f"3. transcribe: {source} -> RAW_SRT")
  if args.mode == "polished":
    print("4. remove fillers from video, then transcribe clean spoken video")
    print("5. correct/check clean SRT")
  else:
    print("4. correct/check SRT")
    if args.stop_after_srt:
      print("5. stop after corrected SRT for user review")
      return
    print("5. generate ASS subtitles")
    print("6. render ASS subtitles into MP4")
    return
  if args.stop_after_srt:
    print("6. stop after corrected clean SRT for user review")
    return
  print("6. generate ASS subtitles")
  print("7. render ASS subtitles into MP4")


def main():
  parser = argparse.ArgumentParser(
    description="Run the deterministic daily video edit pipeline."
  )
  parser.add_argument("--date", required=True)
  parser.add_argument("--input")
  parser.add_argument("--output")
  parser.add_argument("--mode", choices=["standard", "polished"], default="standard")
  parser.add_argument("--model", default="tiny")
  parser.add_argument("--language", default="Chinese")
  parser.add_argument("--max-chars", type=int, default=28)
  parser.add_argument("--duration-tolerance", type=float, default=0.4)
  parser.add_argument(
    "--from-stage",
    choices=["start", "check", "ass", "render"],
    default="start",
    help="Resume from an existing corrected SRT or ASS without rerunning earlier slow stages.",
  )
  parser.add_argument("--video-input", help="Required when --from-stage is not start.")
  parser.add_argument("--srt-input", help="Existing corrected SRT for --from-stage check/ass/render.")
  parser.add_argument("--ass-input", help="Existing ASS for --from-stage render.")
  parser.add_argument("--stop-after-srt", action="store_true", help="Stop after corrected SRT and subtitle checks, before ASS generation or video rendering.")
  parser.add_argument("--skip-deps", action="store_true")
  parser.add_argument("--dry-run", action="store_true")
  args = parser.parse_args()

  if args.dry_run:
    print_dry_run(args)
    return

  root = Path.cwd()
  stages = []
  source_video = None
  subtitle_dir = root / "04_videos" / args.date / "subtitles"
  subtitle_dir.mkdir(parents=True, exist_ok=True)

  if not args.skip_deps:
    run_step("dependency_check", [sys.executable, SCRIPT_DIR / "check-edit-deps.py"], stages)

  if args.from_stage == "start":
    run_step(
      "preprocess_recording",
      [
        sys.executable,
        SCRIPT_DIR / "preprocess-recording.py",
        "--date",
        args.date,
        "--all",
        "--tail-window",
        "999999",
        "--force",
      ],
      stages,
    )

    source_video = choose_usable_input(root, args.date, args.input)
    raw_srt = subtitle_dir / f"{args.date}_transcribed_raw.srt"
    corrected_srt = subtitle_dir / f"{args.date}_transcribed_corrected.srt"

    run_step(
      "transcribe_raw",
      [
        sys.executable,
        SCRIPT_DIR / "transcribe-recording-to-srt.py",
        "--date",
        args.date,
        "--input",
        source_video,
        "--output",
        raw_srt,
        "--model",
        args.model,
        "--language",
        args.language,
      ],
      stages,
    )
    run_step(
      "correct_raw_srt",
      [
        sys.executable,
        SCRIPT_DIR / "correct-transcript.py",
        args.date,
        "--input",
        raw_srt,
        "--output",
        corrected_srt,
      ],
      stages,
    )
    final_video_input = source_video
    final_srt = corrected_srt

    if args.mode == "polished":
      no_filler_video = root / "04_videos" / args.date / "preprocessed" / f"{source_video.stem}_no-fillers.mp4"
      no_filler_srt = subtitle_dir / f"{args.date}_rough_no-fillers.srt"
      run_step(
        "remove_fillers",
        [
          sys.executable,
          SCRIPT_DIR / "remove-filler-words.py",
          "--date",
          args.date,
          "--input-video",
          source_video,
          "--input-srt",
          corrected_srt,
          "--output-video",
          no_filler_video,
          "--output-srt",
          no_filler_srt,
          "--aggressive-fillers",
        ],
        stages,
      )
      final_video_input = no_filler_video
      clean_raw_srt = subtitle_dir / f"{args.date}_clean_transcribed_raw.srt"
      clean_corrected_srt = subtitle_dir / f"{args.date}_clean_transcribed_corrected.srt"
      run_step(
        "transcribe_clean",
        [
          sys.executable,
          SCRIPT_DIR / "transcribe-recording-to-srt.py",
          "--date",
          args.date,
          "--input",
          final_video_input,
          "--output",
          clean_raw_srt,
          "--model",
          args.model,
          "--language",
          args.language,
        ],
        stages,
      )
      run_step(
        "correct_clean_srt",
        [
          sys.executable,
          SCRIPT_DIR / "correct-transcript.py",
          args.date,
          "--input",
          clean_raw_srt,
          "--output",
          clean_corrected_srt,
        ],
        stages,
      )
      final_srt = clean_corrected_srt
  else:
    if not args.video_input:
      raise SystemExit("--video-input is required when --from-stage is not start.")
    final_video_input = resolve_path(root, args.video_input)
    final_srt = resolve_path(root, args.srt_input) if args.srt_input else subtitle_dir / f"{args.date}_transcribed_corrected.srt"
    if args.from_stage in ("check", "ass", "render") and not final_srt.exists():
      raise SystemExit(f"Missing SRT for resume: {final_srt}")

  if args.from_stage in ("start", "check"):
    run_step(
      "check_subtitle_text",
      [
        sys.executable,
        SCRIPT_DIR / "check-subtitle-srt.py",
        final_srt,
        "--max-chars",
        str(args.max_chars),
      ],
      stages,
    )
    run_step(
      "check_subtitle_timing",
      [
        sys.executable,
        SCRIPT_DIR / "check-subtitle-timing.py",
        final_srt,
        "--video",
        final_video_input,
        "--max-chars",
        str(args.max_chars),
        "--duration-tolerance",
        str(args.duration_tolerance),
      ],
      stages,
    )

  duration = probe_duration(final_video_input)
  report_path = root / "04_videos" / args.date / "edit-run" / f"{args.date}_{args.mode}_render_day_report.json"
  report_path.parent.mkdir(parents=True, exist_ok=True)

  if args.stop_after_srt:
    report = {
      "date": args.date,
      "mode": args.mode,
      "model": args.model,
      "input": str(source_video) if args.from_stage == "start" else str(final_video_input),
      "finalVideoInput": str(final_video_input),
      "finalSrt": str(final_srt),
      "output": "",
      "durationSeconds": round(duration, 3),
      "stoppedAfter": "srt",
      "totalElapsedSeconds": round(sum(stage["elapsedSeconds"] for stage in stages), 3),
      "stages": stages,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"final_srt={final_srt}")
    print(f"video_input={final_video_input}")
    print(f"duration={duration:.3f}")
    print(f"report={report_path}")
    print("stopped_after=srt")
    return

  ass_input = resolve_path(root, args.ass_input) if args.ass_input else subtitle_dir / f"{args.date}_transcribed.ass"
  if args.from_stage in ("start", "check", "ass"):
    run_step(
      "generate_ass",
      [
        sys.executable,
        SCRIPT_DIR / "generate-video-diary-caption-assets.py",
        "--date",
        args.date,
        "--duration",
        f"{duration:.3f}",
        "--srt-input",
        final_srt,
        "--ass-only",
      ],
      stages,
    )
  elif not ass_input.exists():
    raise SystemExit(f"Missing ASS for resume: {ass_input}")
  output_path = resolve_path(root, args.output) if args.output else default_output_path(root, args.date, args.mode)
  output_path.parent.mkdir(parents=True, exist_ok=True)
  run_step(
    "render_ass_video",
    [
      sys.executable,
      SCRIPT_DIR / "render-ass-subtitles-legacy.py",
      "--date",
      args.date,
      "--input",
      final_video_input,
      "--output",
      output_path,
      "--ass-input",
      ass_input,
      "--duration",
      f"{duration:.3f}",
    ],
    stages,
  )

  report = {
    "date": args.date,
    "mode": args.mode,
    "model": args.model,
    "input": str(source_video or final_video_input),
    "finalVideoInput": str(final_video_input),
    "finalSrt": str(final_srt),
    "assInput": str(ass_input),
    "output": str(output_path),
    "durationSeconds": round(duration, 3),
    "totalElapsedSeconds": round(sum(stage["elapsedSeconds"] for stage in stages), 3),
    "stages": stages,
  }
  report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

  print(f"output={output_path}")
  print(f"final_srt={final_srt}")
  print(f"ass={ass_input}")
  print(f"duration={duration:.3f}")
  print(f"report={report_path}")


if __name__ == "__main__":
  main()
