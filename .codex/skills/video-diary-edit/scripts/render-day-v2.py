from pathlib import Path
import argparse
import json
import os
import shlex
import subprocess
import sys
import time

from workflow_state import (
  content_media_dir,
  file_fingerprint,
  load_job,
  record_stage,
  save_job,
  stage_cache_key,
)


SCRIPT_DIR = Path(__file__).resolve().parent
FFPROBE_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffprobe")


def resolve_path(root, value):
  path = Path(value)
  return path if path.is_absolute() else root / path


def optional_artifact_path(root, value):
  if not value:
    return None
  path = resolve_path(root, value)
  return path if path.is_file() else None


def ffprobe_bin():
  return os.environ.get("FFPROBE_BIN") or (str(FFPROBE_FULL) if FFPROBE_FULL.exists() else "ffprobe")


def run_step(name, command, stages):
  started = time.time()
  print(f"RUN\t{name}\t{shlex.join(str(item) for item in command)}")
  subprocess.run([str(item) for item in command], check=True)
  elapsed = round(time.time() - started, 3)
  stages.append({"name": name, "elapsedSeconds": elapsed, "command": [str(item) for item in command]})
  print(f"DONE\t{name}\t{elapsed:.3f}s")
  return elapsed


def run_capture(command):
  return subprocess.run(
    [str(item) for item in command],
    text=True,
    capture_output=True,
    check=True,
  ).stdout


def probe_duration(path):
  output = run_capture([
    ffprobe_bin(),
    "-v",
    "error",
    "-show_entries",
    "format=duration",
    "-of",
    "json",
    path,
  ])
  return float(json.loads(output)["format"]["duration"])


def read_manifest(root, date, content_type="video-diary", sequence="001"):
  path = content_media_dir(root, "04_videos", date, content_type, sequence) / "preprocessed" / "preprocess_manifest.json"
  if not path.exists():
    raise SystemExit(f"Missing preprocess manifest: {path}")
  return json.loads(path.read_text(encoding="utf-8"))


def choose_usable_input(root, date, requested_input, content_type="video-diary", sequence="001"):
  manifest = read_manifest(root, date, content_type, sequence)
  items = manifest.get("items", [])
  if not items:
    raise SystemExit("Preprocess manifest has no items.")
  if requested_input:
    requested = resolve_path(root, requested_input).resolve()
    matches = [item for item in items if Path(item.get("input", "")).resolve() == requested]
    if not matches:
      raise SystemExit(f"Requested input was not found in preprocess manifest: {requested}")
    item = matches[0]
  else:
    if len(items) != 1:
      raise SystemExit(f"Multiple recordings found for {date}. Use --input with one explicit file.")
    item = items[0]
  usable = Path(item["usableInput"])
  if not usable.is_absolute():
    usable = root / usable
  if not usable.exists():
    raise SystemExit(f"Missing usable input: {usable}")
  return usable


def load_json(path):
  return json.loads(Path(path).read_text(encoding="utf-8"))


def write_report(path, data):
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
  parser = argparse.ArgumentParser(description="Optimized video diary pipeline with word timestamps and one review gate.")
  parser.add_argument("--date", required=True)
  parser.add_argument("--content-type", "--column", dest="content_type", default="video-diary")
  parser.add_argument("--sequence", default="001")
  parser.add_argument("--input")
  parser.add_argument("--video-input")
  parser.add_argument("--srt-input")
  parser.add_argument("--output")
  parser.add_argument("--model", default="base")
  parser.add_argument("--language", default="Chinese")
  parser.add_argument("--from-stage", choices=["start", "review"], default="start")
  parser.add_argument("--stop-after-review", action="store_true")
  parser.add_argument("--confirmed", action="store_true")
  parser.add_argument("--skip-deps", action="store_true")
  parser.add_argument("--force", action="store_true")
  parser.add_argument("--title", default="")
  parser.add_argument("--subtitle", default="")
  parser.add_argument("--day-label", default="")
  parser.add_argument("--cover-route", default="video-diary")
  parser.add_argument("--cover-version", default="v1.3.1")
  parser.add_argument("--cover-3x4")
  parser.add_argument("--cover-4x3")
  parser.add_argument("--cover-card")
  parser.add_argument("--cover-duration", type=float, default=0.0)
  parser.add_argument("--overlay-plan")
  parser.add_argument("--encoder", choices=["auto", "libx264", "h264_videotoolbox"], default="libx264")
  parser.add_argument("--skip-cover-check", action="store_true")
  args = parser.parse_args()

  root = Path.cwd()
  stages = []
  content_cli = ["--content-type", args.content_type, "--sequence", args.sequence]
  workspace = content_media_dir(root, "04_videos", args.date, args.content_type, args.sequence)
  job = load_job(root, args.date, args.content_type, args.sequence)
  job["engine"] = "v2"
  job["contentType"] = args.content_type
  job["column"] = args.content_type
  job["sequence"] = args.sequence
  job.setdefault("content", {}).update({
    key: value for key, value in {
      "title": args.title,
      "subtitle": args.subtitle,
      "dayLabel": args.day_label,
    }.items() if value
  })
  job.setdefault("style", {}).update({
    "coverRoute": args.cover_route,
    "coverVersion": args.cover_version,
    "subtitleVersion": "chin-box-v1",
  })
  if args.cover_3x4:
    job.setdefault("artifacts", {})["cover3x4"] = str(resolve_path(root, args.cover_3x4))
  if args.cover_4x3:
    job.setdefault("artifacts", {})["cover4x3"] = str(resolve_path(root, args.cover_4x3))
  if args.overlay_plan:
    plan_path = resolve_path(root, args.overlay_plan)
    plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    job.setdefault("requests", {})["insertPlan"] = plan_data.get("items", plan_data)
    job["artifacts"]["overlayPlan"] = str(plan_path)
  job.setdefault("requests", {})["coverCardSeconds"] = args.cover_duration
  save_job(root, args.date, job, args.content_type, args.sequence)

  subtitle_dir = workspace / "subtitles"
  run_dir = workspace / "edit-run"
  subtitle_dir.mkdir(parents=True, exist_ok=True)
  run_dir.mkdir(parents=True, exist_ok=True)

  if args.from_stage == "start":
    if not args.skip_deps:
      elapsed = run_step("dependency_check", [sys.executable, SCRIPT_DIR / "check-edit-deps.py"], stages)
      record_stage(job, "dependencyCheck", "static", [], elapsed)

    preprocess_command = [
      sys.executable,
      SCRIPT_DIR / "preprocess-recording.py",
      "--date",
      args.date,
      *content_cli,
      "--all",
      "--tail-window",
      "10",
    ]
    if args.force:
      preprocess_command.append("--force")
    elapsed = run_step("preprocess_tail", preprocess_command, stages)
    source_video = choose_usable_input(
      root, args.date, args.input, args.content_type, args.sequence
    )
    job["source"] = {
      "recording": str(source_video),
      "fingerprint": file_fingerprint(source_video),
    }
    job["artifacts"]["videoInput"] = str(source_video)
    job["artifacts"]["reviewVideo"] = str(source_video)
    record_stage(
      job,
      "preprocess",
      stage_cache_key([source_video], {"tailWindow": 10}),
      [source_video],
      elapsed,
    )
    save_job(root, args.date, job, args.content_type, args.sequence)

    prompt_path = subtitle_dir / f"{args.date}_transcription_prompt.txt"
    elapsed = run_step(
      "build_transcription_prompt",
      [
        sys.executable,
        SCRIPT_DIR / "build-transcription-prompt.py",
        "--date",
        args.date,
        *content_cli,
        "--output",
        prompt_path,
      ],
      stages,
    )
    record_stage(job, "transcriptionPrompt", stage_cache_key([], {"date": args.date}), [prompt_path], elapsed)

    raw_segment_srt = subtitle_dir / f"{args.date}_segments_raw.srt"
    word_json = subtitle_dir / f"{args.date}_words_raw.json"
    audio_cache = subtitle_dir / f"{source_video.stem}_16k.wav"
    transcribe_command = [
      sys.executable,
      SCRIPT_DIR / "transcribe-recording-to-srt.py",
      "--date",
      args.date,
      *content_cli,
      "--input",
      source_video,
      "--output",
      raw_segment_srt,
      "--json-output",
      word_json,
      "--audio-cache",
      audio_cache,
      "--model",
      args.model,
      "--language",
      args.language,
      "--prompt-file",
      prompt_path,
      "--word-timestamps",
    ]
    if args.force:
      transcribe_command.append("--force")
    elapsed = run_step("transcribe_word_json", transcribe_command, stages)
    record_stage(
      job,
      "transcription",
      stage_cache_key([source_video, prompt_path], {"model": args.model, "language": args.language}),
      [raw_segment_srt, word_json, audio_cache],
      elapsed,
    )

    word_srt = subtitle_dir / f"{args.date}_word_timed_raw.srt"
    elapsed = run_step(
      "build_word_timed_srt",
      [
        sys.executable,
        SCRIPT_DIR / "build-word-timestamp-srt.py",
        "--input-json",
        word_json,
        "--output-srt",
        word_srt,
        "--max-units",
        "18",
        "--max-duration",
        "2.8",
      ],
      stages,
    )
    record_stage(job, "wordTimedSrt", stage_cache_key([word_json], {"maxUnits": 18}), [word_srt], elapsed)

    corrected_srt = subtitle_dir / f"{args.date}_transcribed_corrected.srt"
    elapsed = run_step(
      "correct_srt",
      [
        sys.executable,
        SCRIPT_DIR / "correct-transcript.py",
        args.date,
        *content_cli,
        "--input",
        word_srt,
        "--output",
        corrected_srt,
      ],
      stages,
    )
    record_stage(job, "subtitleCorrection", stage_cache_key([word_srt], {}), [corrected_srt], elapsed)

    confidence_json = subtitle_dir / f"{args.date}_confidence.json"
    confidence_md = subtitle_dir / f"{args.date}_confidence.md"
    elapsed = run_step(
      "analyze_confidence",
      [
        sys.executable,
        SCRIPT_DIR / "analyze-transcript-confidence.py",
        "--input-json",
        word_json,
        "--output-json",
        confidence_json,
        "--output-md",
        confidence_md,
      ],
      stages,
    )
    record_stage(job, "confidenceAnalysis", stage_cache_key([word_json], {}), [confidence_json, confidence_md], elapsed)

    text_report = subtitle_dir / f"{args.date}_subtitle_text_qc.json"
    elapsed = run_step(
      "check_subtitle_text",
      [
        sys.executable,
        SCRIPT_DIR / "check-subtitle-srt.py",
        corrected_srt,
        "--max-chars",
        "28",
        "--report",
        text_report,
      ],
      stages,
    )
    record_stage(job, "subtitleTextQc", stage_cache_key([corrected_srt], {"maxChars": 28}), [text_report], elapsed)

    timing_report = subtitle_dir / f"{args.date}_subtitle_timing_qc.json"
    elapsed = run_step(
      "check_subtitle_audio_alignment",
      [
        sys.executable,
        SCRIPT_DIR / "check-subtitle-timing.py",
        corrected_srt,
        "--video",
        source_video,
        "--word-json",
        word_json,
        "--max-chars",
        "28",
        "--report",
        timing_report,
      ],
      stages,
    )
    record_stage(job, "subtitleTimingQc", stage_cache_key([corrected_srt, word_json], {}), [timing_report], elapsed)

    confidence = load_json(confidence_json)
    job["artifacts"].update({
      "audioCache": str(audio_cache),
      "wordJson": str(word_json),
      "correctedSrt": str(corrected_srt),
      "confidenceReport": str(confidence_md),
      "subtitleTextQc": str(text_report),
      "subtitleTimingQc": str(timing_report),
    })
    job.setdefault("quality", {}).update({
      "transcriptConfidence": {
        "status": "review" if confidence["uncertainCount"] else "pass",
        "uncertainCount": confidence["uncertainCount"],
      },
      "subtitleText": {"status": "pass", "report": str(text_report)},
      "subtitleTiming": {"status": "pass", "report": str(timing_report)},
    })
    job["status"] = "review_ready"
    save_job(root, args.date, job, args.content_type, args.sequence)
    run_step(
      "build_review_pack",
      [sys.executable, SCRIPT_DIR / "build-review-pack.py", "--date", args.date, *content_cli],
      stages,
    )

    if args.stop_after_review or not args.confirmed:
      report_path = run_dir / f"{args.date}_v2_review_report.json"
      write_report(report_path, {
        "date": args.date,
        "engine": "v2",
        "stoppedAfter": "review",
        "videoInput": str(source_video),
        "correctedSrt": str(corrected_srt),
        "wordJson": str(word_json),
        "reviewPack": str(workspace / "REVIEW.md"),
        "totalElapsedSeconds": round(sum(stage["elapsedSeconds"] for stage in stages), 3),
        "stages": stages,
      })
      print(f"video_input={source_video}")
      print(f"final_srt={corrected_srt}")
      print(f"word_json={word_json}")
      print(f"review_pack={workspace / 'REVIEW.md'}")
      print("stopped_after=review")
      return
  else:
    source_video = (
      optional_artifact_path(root, args.video_input)
      if args.video_input
      else optional_artifact_path(root, job.get("artifacts", {}).get("videoInput"))
    )
    corrected_srt = (
      optional_artifact_path(root, args.srt_input)
      if args.srt_input
      else optional_artifact_path(root, job.get("artifacts", {}).get("correctedSrt"))
    )
    word_json = optional_artifact_path(root, job.get("artifacts", {}).get("wordJson"))

  if not args.confirmed:
    raise SystemExit("Final rendering requires --confirmed after cover and external SRT review.")
  if source_video is None or corrected_srt is None:
    raise SystemExit("Missing reviewed video input or corrected SRT. Resume from start or provide explicit paths.")
  if not args.skip_cover_check and job.get("quality", {}).get("cover", {}).get("status") != "pass":
    raise SystemExit("Final rendering requires a QC-passed cover pair. Use --skip-cover-check only for explicit edit-only exports.")

  text_report = subtitle_dir / f"{args.date}_subtitle_text_qc.json"
  run_step(
    "recheck_subtitle_text",
    [
      sys.executable,
      SCRIPT_DIR / "check-subtitle-srt.py",
      corrected_srt,
      "--max-chars",
      "28",
      "--report",
      text_report,
    ],
    stages,
  )
  timing_report = subtitle_dir / f"{args.date}_subtitle_timing_qc.json"
  timing_command = [
    sys.executable,
    SCRIPT_DIR / "check-subtitle-timing.py",
    corrected_srt,
    "--video",
    source_video,
    "--max-chars",
    "28",
    "--report",
    timing_report,
  ]
  if word_json is not None:
    timing_command.extend(["--word-json", word_json])
  run_step("recheck_subtitle_audio_alignment", timing_command, stages)
  job.setdefault("quality", {}).update({
    "subtitleText": {"status": "pass", "report": str(text_report)},
    "subtitleTiming": {"status": "pass", "report": str(timing_report)},
  })
  job["status"] = "render_ready"
  save_job(root, args.date, job, args.content_type, args.sequence)

  duration = probe_duration(source_video)
  ass_path = subtitle_dir / f"{args.date}_transcribed.ass"
  run_step(
    "generate_ass",
    [
      sys.executable,
      SCRIPT_DIR / "generate-video-diary-caption-assets.py",
      "--date",
      args.date,
      *content_cli,
      "--duration",
      f"{duration:.3f}",
      "--srt-input",
      corrected_srt,
      "--ass-only",
    ],
    stages,
  )

  output_path = resolve_path(root, args.output) if args.output else (
    workspace / f"{args.date}_{args.content_type}_{args.sequence}_v2_ass_subtitled.mp4"
  )
  render_command = [
    sys.executable,
    SCRIPT_DIR / "render-ass-subtitles.py",
    "--date",
    args.date,
    *content_cli,
    "--input",
    source_video,
    "--output",
    output_path,
    "--ass-input",
    ass_path,
    "--duration",
    f"{duration:.3f}",
    "--encoder",
    args.encoder,
  ]
  overlay_plan = args.overlay_plan or job.get("artifacts", {}).get("overlayPlan")
  if overlay_plan:
    render_command.extend(["--overlay-plan", overlay_plan])
  if args.cover_card and args.cover_duration > 0:
    render_command.extend([
      "--cover-input",
      resolve_path(root, args.cover_card),
      "--cover-duration",
      str(args.cover_duration),
    ])
  elapsed = run_step("render_final_once", render_command, stages)
  record_stage(
    job,
    "finalRender",
    stage_cache_key([source_video, corrected_srt, ass_path], {"encoder": args.encoder}),
    [output_path],
    elapsed,
  )
  job["status"] = "rendered"
  job["artifacts"]["finalDraft"] = str(output_path)
  save_job(root, args.date, job, args.content_type, args.sequence)

  report_path = run_dir / f"{args.date}_v2_render_report.json"
  write_report(report_path, {
    "date": args.date,
    "contentType": args.content_type,
    "sequence": args.sequence,
    "engine": "v2",
    "input": str(source_video),
    "correctedSrt": str(corrected_srt),
    "wordJson": str(word_json) if word_json else "",
    "ass": str(ass_path),
    "output": str(output_path),
    "durationSeconds": round(probe_duration(output_path), 3),
    "totalElapsedSeconds": round(sum(stage["elapsedSeconds"] for stage in stages), 3),
    "stages": stages,
  })
  print(f"output={output_path}")
  print(f"final_srt={corrected_srt}")
  print(f"ass={ass_path}")
  print(f"report={report_path}")


if __name__ == "__main__":
  main()
