from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile


FFMPEG_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffmpeg")


def ffmpeg_bin():
  return os.environ.get("FFMPEG_BIN") or (str(FFMPEG_FULL) if FFMPEG_FULL.exists() else "ffmpeg")


def prepare_filter_ass(ass_path, date):
  temp_dir = Path(tempfile.gettempdir()) / "video-diary-ass"
  temp_dir.mkdir(parents=True, exist_ok=True)
  safe_path = temp_dir / f"{date}_subtitles.ass"
  shutil.copyfile(ass_path, safe_path)
  return safe_path


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--date", required=True)
  parser.add_argument("--input", required=True)
  parser.add_argument("--output", required=True)
  parser.add_argument("--ass-input")
  parser.add_argument("--duration")
  parser.add_argument("--crf", default="20")
  parser.add_argument("--preset", default="veryfast")
  args = parser.parse_args()

  root = Path.cwd()
  ass_path = Path(args.ass_input) if args.ass_input else root / "04_videos" / args.date / "subtitles" / f"{args.date}_scripted.ass"
  if not ass_path.is_absolute():
    ass_path = root / ass_path
  if not ass_path.exists():
    raise SystemExit(f"Missing ASS subtitle file: {ass_path}")

  filter_ass_path = prepare_filter_ass(ass_path, args.date)
  command = [ffmpeg_bin(), "-hide_banner", "-y", "-i", args.input]
  if args.duration:
    command.extend(["-t", args.duration])
  command.extend([
    "-vf",
    f"subtitles=filename={filter_ass_path}",
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
    "-movflags",
    "+faststart",
    args.output,
  ])
  subprocess.run(command, check=True)


if __name__ == "__main__":
  main()
