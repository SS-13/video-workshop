from pathlib import Path
import argparse
import subprocess


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--date", required=True)
  parser.add_argument("--input", required=True)
  parser.add_argument("--output", required=True)
  parser.add_argument("--duration", required=True)
  parser.add_argument("--crf", default="18")
  parser.add_argument("--preset", default="veryfast")
  args = parser.parse_args()

  root = Path.cwd()
  subtitle_dir = root / "04_videos" / args.date / "subtitles"
  caption_dir = subtitle_dir / "caption_png"
  filter_script = subtitle_dir / f"{args.date}_caption_filter.ffmpeg"
  captions = sorted(caption_dir.glob("caption_*.png"))

  if not captions:
    raise SystemExit(f"No caption PNG files found in {caption_dir}")

  if not filter_script.exists():
    raise SystemExit(f"Missing filter script: {filter_script}")

  command = [
    "ffmpeg",
    "-y",
    "-i",
    args.input,
  ]

  for caption in captions:
    command.extend(["-loop", "1", "-i", str(caption)])

  command.extend([
    "-filter_complex_script",
    str(filter_script),
    "-map",
    "[vout]",
    "-map",
    "0:a?",
    "-t",
    args.duration,
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
