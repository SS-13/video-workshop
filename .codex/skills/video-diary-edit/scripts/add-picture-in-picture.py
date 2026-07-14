from pathlib import Path
import argparse
import shutil
import subprocess


DEFAULT_WIDTH_RATIO = 0.34
DEFAULT_MARGIN_X = 54
DEFAULT_MARGIN_Y = 156
DEFAULT_LABEL = ""
VIDEO_WIDTH = 1080


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


def get_duration(path):
  result = run_command([
    "ffprobe",
    "-v",
    "error",
    "-show_entries",
    "format=duration",
    "-of",
    "default=noprint_wrappers=1:nokey=1",
    str(path),
  ])
  return float(result.stdout.strip())


def escape_drawtext(value):
  return (
    value
    .replace("\\", "\\\\")
    .replace(":", "\\:")
    .replace("'", "\\'")
    .replace("%", "\\%")
  )


def build_filter(start, duration, width_ratio, margin_x, margin_y, label, position):
  pip_width = int(round(VIDEO_WIDTH * width_ratio / 2) * 2)
  end = start + duration
  overlay_x = "(W-w)/2" if position == "top-center" else f"W-w-{margin_x}"
  overlay_y = str(margin_y)
  parts = [
    f"[1:v]trim=0:{duration:.3f},setpts=PTS-STARTPTS+{start:.3f}/TB,scale={pip_width}:-2,setsar=1[pip];",
    f"[0:v][pip]overlay=x={overlay_x}:y={overlay_y}:enable='between(t,{start:.3f},{end:.3f})':eof_action=pass:format=auto[v0]",
  ]

  if label and shutil.which("ffmpeg"):
    text = escape_drawtext(label)
    text_x = "(w-tw)/2" if position == "top-center" else f"w-tw-{margin_x}"
    text_y = margin_y + int(round(pip_width * 9 / 16)) + 12
    parts.append(
      f";[v0]drawtext=text='{text}':x={text_x}:y={text_y}:"
      "fontsize=26:fontcolor=white@0.86:"
      "box=1:boxcolor=black@0.36:boxborderw=10[v]"
    )
  else:
    parts.append(";[v0]format=yuv420p[v]")

  return "".join(parts), end


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--input", required=True)
  parser.add_argument("--pip", required=True)
  parser.add_argument("--output", required=True)
  parser.add_argument("--start", type=float, required=True)
  parser.add_argument("--duration", type=float, default=9.0)
  parser.add_argument("--still", action="store_true")
  parser.add_argument("--width-ratio", type=float, default=DEFAULT_WIDTH_RATIO)
  parser.add_argument("--position", choices=["top-right", "top-center"], default="top-right")
  parser.add_argument("--margin-x", type=int, default=DEFAULT_MARGIN_X)
  parser.add_argument("--margin-y", type=int, default=DEFAULT_MARGIN_Y)
  parser.add_argument("--label", default=DEFAULT_LABEL)
  parser.add_argument("--no-label", action="store_true")
  parser.add_argument("--crf", default="18")
  parser.add_argument("--preset", default="veryfast")
  args = parser.parse_args()

  root = Path.cwd()
  input_path = resolve_path(root, args.input)
  pip_path = resolve_path(root, args.pip)
  output_path = resolve_path(root, args.output)

  if not input_path.exists():
    raise SystemExit(f"Missing input video: {input_path}")
  if not pip_path.exists():
    raise SystemExit(f"Missing PIP video: {pip_path}")

  input_duration = get_duration(input_path)
  if args.start >= input_duration:
    raise SystemExit(f"Overlay start {args.start:.3f}s is beyond input duration {input_duration:.3f}s")
  overlay_duration = min(args.duration, input_duration - args.start)

  output_path.parent.mkdir(parents=True, exist_ok=True)
  filter_script, end = build_filter(
    args.start,
    overlay_duration,
    args.width_ratio,
    args.margin_x,
    args.margin_y,
    "" if args.no_label else args.label,
    args.position,
  )

  command = [
    "ffmpeg",
    "-hide_banner",
    "-y",
    "-i",
    str(input_path),
    "-an",
  ]
  if args.still:
    command.extend(["-loop", "1", "-t", f"{overlay_duration:.3f}"])
  command.extend([
    "-i",
    str(pip_path),
    "-filter_complex",
    filter_script,
    "-map",
    "[v]",
    "-map",
    "0:a?",
    "-c:v",
    "libx264",
    "-preset",
    args.preset,
    "-crf",
    args.crf,
    "-pix_fmt",
    "yuv420p",
    "-c:a",
    "copy",
    "-t",
    f"{input_duration:.3f}",
    "-movflags",
    "+faststart",
    str(output_path),
  ])

  run_command(command)

  print(f"input={input_path}")
  print(f"pip={pip_path}")
  print(f"output={output_path}")
  print(f"start={args.start:.3f}")
  print(f"end={end:.3f}")
  print(f"input_duration={input_duration:.3f}")


if __name__ == "__main__":
  main()
