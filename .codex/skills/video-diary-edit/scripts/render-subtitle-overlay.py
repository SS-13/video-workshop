from pathlib import Path
import argparse
import subprocess

from workflow_state import content_media_dir


DEFAULT_CRF = "18"
DEFAULT_PRESET = "veryfast"


def resolve_path(root, value):
  path = Path(value)
  return path if path.is_absolute() else root / path


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


def find_default_input(root, date, content_type="video-diary", sequence="001"):
  workspace = content_media_dir(root, "04_videos", date, content_type, sequence)
  manifest_path = workspace / "preprocessed" / "preprocess_manifest.json"
  if manifest_path.exists():
    import json
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = manifest.get("items", [])
    usable_inputs = [item.get("usableInput") for item in items if item.get("usableInput")]
    if len(usable_inputs) == 1:
      return Path(usable_inputs[0])

  export_dir = content_media_dir(root, "05_exports", date, content_type, sequence)
  if export_dir.exists():
    candidates = sorted(
      [
        path for path in export_dir.glob("*video-diary*.mp4")
        if "_with-bgm" not in path.name and "captioned" not in path.name
      ],
      key=lambda path: path.stat().st_mtime,
      reverse=True,
    )
    if candidates:
      return candidates[0]

  raise SystemExit("Missing --input and no default input could be found.")


def infer_stem(date, concat_path):
  name = concat_path.name
  suffix = "_overlay_concat.txt"
  if name.endswith(suffix):
    return name[:-len(suffix)]
  return date


def render_overlay(concat_path, overlay_path, fps):
  overlay_path.parent.mkdir(parents=True, exist_ok=True)
  run_command([
    "ffmpeg",
    "-hide_banner",
    "-y",
    "-f",
    "concat",
    "-safe",
    "0",
    "-i",
    str(concat_path),
    "-vf",
    f"fps={fps},format=argb",
    "-c:v",
    "qtrle",
    str(overlay_path),
  ])


def burn_overlay(input_path, overlay_path, output_path, crf, preset, duration):
  output_path.parent.mkdir(parents=True, exist_ok=True)
  command = [
    "ffmpeg",
    "-hide_banner",
    "-y",
    "-i",
    str(input_path),
    "-i",
    str(overlay_path),
    "-filter_complex",
    "[0:v][1:v]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[v]",
  ]

  if duration:
    command.extend(["-t", str(duration)])

  command.extend([
    "-map",
    "[v]",
    "-map",
    "0:a?",
    "-c:v",
    "libx264",
    "-preset",
    preset,
    "-crf",
    crf,
    "-c:a",
    "copy",
    "-movflags",
    "+faststart",
    str(output_path),
  ])

  run_command(command)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--date", required=True)
  parser.add_argument("--content-type", "--column", dest="content_type", default="video-diary")
  parser.add_argument("--sequence", default="001")
  parser.add_argument("--input")
  parser.add_argument("--output", required=True)
  parser.add_argument("--concat-input")
  parser.add_argument("--overlay-output")
  parser.add_argument("--fps", default="30")
  parser.add_argument("--crf", default=DEFAULT_CRF)
  parser.add_argument("--preset", default=DEFAULT_PRESET)
  parser.add_argument("--duration")
  parser.add_argument("--reuse-overlay", action="store_true")
  args = parser.parse_args()

  root = Path.cwd()
  workspace = content_media_dir(root, "04_videos", args.date, args.content_type, args.sequence)
  input_path = resolve_path(root, args.input) if args.input else find_default_input(
    root, args.date, args.content_type, args.sequence
  )
  concat_path = (
    resolve_path(root, args.concat_input)
    if args.concat_input
    else workspace / "subtitles" / f"{args.date}_overlay_concat.txt"
  )
  if not concat_path.exists():
    raise SystemExit(f"Missing subtitle concat file: {concat_path}")
  if not input_path.exists():
    raise SystemExit(f"Missing input video: {input_path}")

  stem = infer_stem(args.date, concat_path)
  overlay_path = (
    resolve_path(root, args.overlay_output)
    if args.overlay_output
    else workspace / "subtitles" / f"{stem}_subtitle_overlay.mov"
  )
  output_path = resolve_path(root, args.output)

  if not args.reuse_overlay or not overlay_path.exists():
    render_overlay(concat_path, overlay_path, args.fps)

  burn_overlay(input_path, overlay_path, output_path, args.crf, args.preset, args.duration)

  print(f"input={input_path}")
  print(f"concat={concat_path}")
  print(f"overlay={overlay_path}")
  print(f"output={output_path}")
  if args.duration:
    print(f"duration={args.duration}")


if __name__ == "__main__":
  main()
