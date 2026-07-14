"""Validate an isolated short-video Shadow Regression workspace."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
import hashlib
import json
import os
import re
import subprocess

from PIL import Image

from video_production_core.contracts import load_json, validate_value
from video_production_core.transcript_quality import compare_transcripts


FFPROBE_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffprobe")
SSIM_RE = re.compile(r"All:(?P<value>\d+(?:\.\d+)?)")


def ffprobe_bin() -> str:
  return os.environ.get("FFPROBE_BIN") or (
    str(FFPROBE_FULL) if FFPROBE_FULL.exists() else "ffprobe"
  )


def inside(path: Path, directory: Path) -> bool:
  try:
    path.resolve().relative_to(directory.resolve())
    return True
  except ValueError:
    return False


def sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as file:
    for chunk in iter(lambda: file.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def probe_video(path: Path) -> Dict[str, Any]:
  result = subprocess.run(
    [
      ffprobe_bin(),
      "-v",
      "error",
      "-show_entries",
      "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
      "-of",
      "json",
      str(path),
    ],
    text=True,
    capture_output=True,
    check=True,
  )
  payload = json.loads(result.stdout)
  return {
    "durationSeconds": round(float(payload["format"]["duration"]), 3),
    "sizeBytes": int(payload["format"]["size"]),
    "streams": payload.get("streams", []),
    "sha256": sha256(path),
  }


def parse_ass(path: Path) -> Dict[str, Any]:
  play_res_x = None
  play_res_y = None
  style_fields: List[str] = []
  style: Dict[str, str] = {}
  max_lines = 0
  section = ""
  for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
    line = raw_line.strip()
    if line.startswith("[") and line.endswith("]"):
      section = line
    elif line.startswith("PlayResX:"):
      play_res_x = int(line.split(":", 1)[1].strip())
    elif line.startswith("PlayResY:"):
      play_res_y = int(line.split(":", 1)[1].strip())
    elif section == "[V4+ Styles]" and line.startswith("Format:"):
      style_fields = [item.strip() for item in line.split(":", 1)[1].split(",")]
    elif section == "[V4+ Styles]" and line.startswith("Style:") and style_fields:
      values = [item.strip() for item in line.split(":", 1)[1].split(",")]
      style = dict(zip(style_fields, values))
    elif section == "[Events]" and line.startswith("Dialogue:"):
      parts = line.split(",", 9)
      text = parts[9] if len(parts) == 10 else ""
      max_lines = max(max_lines, text.count("\\N") + 1)
  return {
    "playResX": play_res_x,
    "playResY": play_res_y,
    "fontSize": int(float(style.get("Fontsize", 0))),
    "borderStyle": int(style.get("BorderStyle", 0)),
    "alignment": int(style.get("Alignment", 0)),
    "marginLeft": int(style.get("MarginL", 0)),
    "marginRight": int(style.get("MarginR", 0)),
    "marginVertical": int(style.get("MarginV", 0)),
    "maxLines": max_lines,
  }


def parse_ssim_output(value: str) -> float:
  match = SSIM_RE.search(value)
  if not match:
    raise ValueError("FFmpeg SSIM output did not contain an All score.")
  return float(match.group("value"))


def compare_video_ssim(left: Path, right: Path) -> float:
  result = subprocess.run(
    [
      "/usr/local/opt/ffmpeg-full/bin/ffmpeg",
      "-hide_banner",
      "-i",
      str(left),
      "-i",
      str(right),
      "-filter_complex",
      "[0:v][1:v]ssim",
      "-an",
      "-f",
      "null",
      "-",
    ],
    text=True,
    capture_output=True,
    check=True,
  )
  return parse_ssim_output(result.stderr)


def newer_stable_media(root: Path, started_at: str) -> List[str]:
  threshold = datetime.fromisoformat(started_at).timestamp()
  changed = []
  for directory_name in ["03_recordings", "04_videos", "05_exports"]:
    directory = root / directory_name
    if not directory.exists():
      continue
    for path in directory.rglob("*"):
      if path.is_file() and path.stat().st_mtime >= threshold:
        changed.append(str(path.relative_to(root)))
  return sorted(changed)


def markdown_report(result: Dict[str, Any]) -> str:
  rows = [
    f"# {result.get('title', '3.0.0 RC1 Shadow Regression')}",
    "",
    f"- 结果：`{'pass' if result['valid'] else 'fail'}`",
    f"- 工作区：`{result['workspace']}`",
    f"- 样本日期：`{result['date']}`",
    f"- 生成时间：`{result['generatedAt']}`",
    "",
    "## Gate Results",
    "",
    "| Gate | Result | Evidence |",
    "| --- | --- | --- |",
  ]
  for check in result["checks"]:
    evidence = json.dumps(check.get("evidence", {}), ensure_ascii=False, sort_keys=True)
    rows.append(f"| {check['name']} | {check['status']} | `{evidence}` |")
  rows.extend([
    "",
    "## Notes",
    "",
  ])
  rows.extend(f"- {note}" for note in result.get("notes", []))
  rows.append("")
  return "\n".join(rows)


def validate_shadow(
  root: Path,
  workspace: Path,
  date: str,
  started_at: str,
  visual_check: str,
  min_transcript_accuracy: float = 0.98,
) -> Dict[str, Any]:
  workspace = workspace.resolve()
  export_dir = workspace / "05_exports" / date
  video_dir = workspace / "04_videos" / date
  paths = {
    "source": workspace / "03_recordings" / date / "golden-20s.mp4",
    "v2": export_dir / f"{date}_Shadow_v2.mp4",
    "legacy": export_dir / f"{date}_Shadow_legacy.mp4",
    "cover3x4": export_dir / f"{date}_Shadow_cover_3x4.jpg",
    "cover4x3": export_dir / f"{date}_Shadow_cover_4x3.jpg",
    "srt": video_dir / "subtitles" / f"{date}_transcribed_corrected.srt",
    "expectedSrt": workspace / "assets" / "golden-reference.srt",
    "ass": video_dir / "subtitles" / f"{date}_transcribed.ass",
    "textQc": video_dir / "subtitles" / f"{date}_subtitle_text_qc.json",
    "timingQc": video_dir / "subtitles" / f"{date}_subtitle_timing_qc.json",
    "publishPackage": export_dir / "publish-package.json",
  }
  checks: List[Dict[str, Any]] = []

  def add(name: str, passed: bool, evidence: Dict[str, Any]) -> None:
    checks.append({"name": name, "status": "pass" if passed else "fail", "evidence": evidence})

  missing = [name for name, path in paths.items() if not path.exists()]
  add("required-artifacts", not missing, {"missing": missing, "count": len(paths)})
  if missing:
    return {
      "valid": False,
      "title": "3.0.0 RC1 Short Golden Shadow Regression",
      "date": date,
      "workspace": str(workspace),
      "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
      "checks": checks,
    }

  outside = [name for name, path in paths.items() if not inside(path, workspace)]
  add("workspace-containment", not outside, {"outside": outside})

  source_info = probe_video(paths["source"])
  v2_info = probe_video(paths["v2"])
  legacy_info = probe_video(paths["legacy"])
  media_evidence = {"source": source_info, "v2": v2_info, "legacy": legacy_info}

  def media_shape(info: Dict[str, Any]) -> bool:
    video_streams = [item for item in info["streams"] if item.get("codec_type") == "video"]
    audio_streams = [item for item in info["streams"] if item.get("codec_type") == "audio"]
    return (
      len(video_streams) == 1
      and len(audio_streams) == 1
      and video_streams[0].get("width") == 1080
      and video_streams[0].get("height") == 1920
    )

  duration_delta = max(
    abs(v2_info["durationSeconds"] - source_info["durationSeconds"]),
    abs(legacy_info["durationSeconds"] - source_info["durationSeconds"]),
  )
  add(
    "media-output",
    media_shape(v2_info) and media_shape(legacy_info) and duration_delta <= 0.1,
    {"durationDelta": round(duration_delta, 3), **media_evidence},
  )

  with Image.open(paths["cover3x4"]) as image:
    cover_3x4_size = image.size
  with Image.open(paths["cover4x3"]) as image:
    cover_4x3_size = image.size
  add(
    "cover-pair",
    cover_3x4_size == (1080, 1440) and cover_4x3_size == (1440, 1080),
    {"3x4": cover_3x4_size, "4x3": cover_4x3_size},
  )

  transcript = compare_transcripts(paths["srt"], paths["expectedSrt"], min_transcript_accuracy)
  add("golden-transcript", transcript["passed"], transcript)

  text_qc = load_json(paths["textQc"])
  timing_qc = load_json(paths["timingQc"])
  alignment = timing_qc.get("alignment", {})
  subtitle_gate_passed = (
    text_qc.get("passed", False)
    and not timing_qc.get("errors", [])
    and alignment.get("p95StartDelta", 999) <= 0.25
    and alignment.get("p95EndDelta", 999) <= 0.25
    and abs(alignment.get("globalStartOffset", 999)) <= 0.25
  )
  add("subtitle-qc", subtitle_gate_passed, {"text": text_qc, "timing": timing_qc})

  ass = parse_ass(paths["ass"])
  subtitle_style_passed = (
    ass["playResX"] == 1080
    and ass["playResY"] == 1920
    and ass["fontSize"] >= 40
    and ass["alignment"] == 2
    and ass["borderStyle"] == 3
    and ass["marginLeft"] >= 200
    and ass["marginRight"] >= 200
    and 500 <= ass["marginVertical"] <= 800
    and ass["maxLines"] <= 2
  )
  add("subtitle-safe-area", subtitle_style_passed, ass)

  package = load_json(paths["publishPackage"])
  schema = load_json(root / "00_system" / "contracts" / "schemas" / "publish-package.schema.json")
  package_errors = validate_value(package, schema)
  package_artifacts = package.get("artifacts", {})
  missing_package_artifacts = []
  outside_package_artifacts = []
  for name, value in package_artifacts.items():
    artifact_path = Path(value)
    if not artifact_path.is_absolute():
      artifact_path = root / artifact_path
    if not artifact_path.exists():
      missing_package_artifacts.append(name)
    if not inside(artifact_path, workspace):
      outside_package_artifacts.append(name)
  package_passed = (
    not package_errors
    and not missing_package_artifacts
    and not outside_package_artifacts
    and package.get("production", {}).get("systemVersion") == "3.0.0"
  )
  add(
    "publish-package",
    package_passed,
    {
      "errors": package_errors,
      "missingArtifacts": missing_package_artifacts,
      "outsideArtifacts": outside_package_artifacts,
      "publishReady": package.get("publishReady"),
      "systemVersion": package.get("production", {}).get("systemVersion"),
    },
  )

  stable_writes = newer_stable_media(root, started_at)
  add("stable-channel-isolation", not stable_writes, {"writesSince": started_at, "paths": stable_writes})
  add("manual-visual-check", visual_check == "pass", {"result": visual_check})

  return {
    "valid": all(check["status"] == "pass" for check in checks),
    "title": "3.0.0 RC1 Short Golden Shadow Regression",
    "date": date,
    "workspace": str(workspace),
    "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
    "checks": checks,
    "notes": [
      "Shadow publish package intentionally remains `publishReady=false` because it does not write production statistics.",
      "A real-video Canary must record production statistics and produce `publishReady=true` before activation.",
      "Stable media directories are monitored from the supplied Shadow start timestamp.",
    ],
  }


def validate_historical_shadow(
  root: Path,
  workspace: Path,
  date: str,
  started_at: str,
  visual_check: str,
) -> Dict[str, Any]:
  workspace = workspace.resolve()
  export_dir = workspace / "05_exports" / date
  video_dir = workspace / "04_videos" / date
  legacy_date = f"{date}-legacy"
  paths = {
    "source": workspace / "03_recordings" / date / "full-history.mp4",
    "v2": export_dir / f"{date}_Shadow_v2.mp4",
    "legacy": export_dir / f"{date}_Shadow_legacy.mp4",
    "srt": video_dir / "subtitles" / f"{date}_transcribed_corrected.srt",
    "ass": video_dir / "subtitles" / f"{date}_transcribed.ass",
    "textQc": video_dir / "subtitles" / f"{date}_subtitle_text_qc.json",
    "timingQc": video_dir / "subtitles" / f"{date}_subtitle_timing_qc.json",
    "v2Report": video_dir / "edit-run" / f"{date}_v2_render_report.json",
    "legacyReport": (
      workspace
      / "04_videos"
      / legacy_date
      / "edit-run"
      / f"{legacy_date}_standard_render_day_report.json"
    ),
  }
  checks: List[Dict[str, Any]] = []

  def add(name: str, passed: bool, evidence: Dict[str, Any]) -> None:
    checks.append({"name": name, "status": "pass" if passed else "fail", "evidence": evidence})

  missing = [name for name, path in paths.items() if not path.exists()]
  add("required-artifacts", not missing, {"missing": missing, "count": len(paths)})
  if missing:
    return {
      "valid": False,
      "title": "3.0.0 RC1 Full Historical Shadow Regression",
      "date": date,
      "workspace": str(workspace),
      "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
      "checks": checks,
      "notes": [],
    }

  outside = [name for name, path in paths.items() if not inside(path, workspace)]
  add("workspace-containment", not outside, {"outside": outside})

  source_info = probe_video(paths["source"])
  v2_info = probe_video(paths["v2"])
  legacy_info = probe_video(paths["legacy"])

  def media_shape(info: Dict[str, Any]) -> bool:
    video_streams = [item for item in info["streams"] if item.get("codec_type") == "video"]
    audio_streams = [item for item in info["streams"] if item.get("codec_type") == "audio"]
    return (
      len(video_streams) == 1
      and len(audio_streams) == 1
      and video_streams[0].get("width") == 1080
      and video_streams[0].get("height") == 1920
    )

  duration_delta = max(
    abs(v2_info["durationSeconds"] - source_info["durationSeconds"]),
    abs(legacy_info["durationSeconds"] - source_info["durationSeconds"]),
  )
  add(
    "full-media-output",
    media_shape(v2_info) and media_shape(legacy_info) and duration_delta <= 0.1,
    {
      "durationDelta": round(duration_delta, 3),
      "source": source_info,
      "v2": v2_info,
      "legacy": legacy_info,
    },
  )

  ssim = compare_video_ssim(paths["v2"], paths["legacy"])
  add("v2-legacy-frame-equivalence", ssim >= 0.999999, {"ssim": ssim})

  text_qc = load_json(paths["textQc"])
  timing_qc = load_json(paths["timingQc"])
  add(
    "full-subtitle-structure",
    text_qc.get("passed", False) and not timing_qc.get("errors", []),
    {"text": text_qc, "timing": timing_qc},
  )

  ass = parse_ass(paths["ass"])
  subtitle_style_passed = (
    ass["playResX"] == 1080
    and ass["playResY"] == 1920
    and ass["fontSize"] >= 40
    and ass["alignment"] == 2
    and ass["borderStyle"] == 3
    and ass["marginLeft"] >= 200
    and ass["marginRight"] >= 200
    and 500 <= ass["marginVertical"] <= 800
    and ass["maxLines"] <= 2
  )
  add("full-subtitle-safe-area", subtitle_style_passed, ass)

  v2_report = load_json(paths["v2Report"])
  legacy_report = load_json(paths["legacyReport"])
  add(
    "render-reports",
    v2_report.get("engine") == "v2"
    and legacy_report.get("mode") == "standard"
    and abs(v2_report.get("durationSeconds", 0) - legacy_report.get("durationSeconds", 0)) <= 0.1,
    {
      "v2ElapsedSeconds": v2_report.get("totalElapsedSeconds"),
      "legacyElapsedSeconds": legacy_report.get("totalElapsedSeconds"),
      "v2DurationSeconds": v2_report.get("durationSeconds"),
      "legacyDurationSeconds": legacy_report.get("durationSeconds"),
      "v2WordJson": v2_report.get("wordJson"),
    },
  )

  stable_writes = newer_stable_media(root, started_at)
  add("stable-channel-isolation", not stable_writes, {"writesSince": started_at, "paths": stable_writes})
  add("manual-visual-check", visual_check == "pass", {"result": visual_check})

  return {
    "valid": all(check["status"] == "pass" for check in checks),
    "title": "3.0.0 RC1 Full Historical Shadow Regression",
    "date": date,
    "workspace": str(workspace),
    "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
    "checks": checks,
    "notes": [
      "The full historical source is an APFS clone inside the isolated Shadow workspace.",
      "The review-resume empty `wordJson` bug was found, fixed, and covered by a regression test before the successful rerun.",
      "Short Golden Regression remains the authoritative word-level timing and transcript-accuracy gate.",
    ],
  }
