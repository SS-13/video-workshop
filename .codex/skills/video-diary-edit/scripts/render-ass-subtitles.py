from pathlib import Path
import argparse
import json
import os
import shlex
import shutil
import subprocess
import tempfile

from workflow_state import content_media_dir


FFMPEG_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffmpeg")
FFPROBE_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffprobe")


def ffmpeg_bin():
  return os.environ.get("FFMPEG_BIN") or (str(FFMPEG_FULL) if FFMPEG_FULL.exists() else "ffmpeg")


def ffprobe_bin():
  return os.environ.get("FFPROBE_BIN") or (str(FFPROBE_FULL) if FFPROBE_FULL.exists() else "ffprobe")


def prepare_filter_ass(ass_path, date):
  temp_dir = Path(tempfile.gettempdir()) / "video-diary-ass"
  temp_dir.mkdir(parents=True, exist_ok=True)
  safe_path = temp_dir / f"{date}_subtitles.ass"
  shutil.copyfile(ass_path, safe_path)
  return safe_path


def probe_video(path):
  result = subprocess.run(
    [
      ffprobe_bin(),
      "-v",
      "error",
      "-select_streams",
      "v:0",
      "-show_entries",
      "stream=width,height,r_frame_rate",
      "-of",
      "json",
      str(path),
    ],
    check=True,
    capture_output=True,
    text=True,
  )
  stream = json.loads(result.stdout)["streams"][0]
  rate = stream.get("r_frame_rate", "30/1")
  numerator, denominator = rate.split("/", 1)
  fps = float(numerator) / max(1.0, float(denominator))
  return int(stream["width"]), int(stream["height"]), fps


def has_audio(path):
  result = subprocess.run(
    [
      ffprobe_bin(),
      "-v",
      "error",
      "-select_streams",
      "a:0",
      "-show_entries",
      "stream=index",
      "-of",
      "json",
      str(path),
    ],
    check=True,
    capture_output=True,
    text=True,
  )
  return bool(json.loads(result.stdout).get("streams"))


def encoder_available(name):
  result = subprocess.run(
    [ffmpeg_bin(), "-hide_banner", "-encoders"],
    check=False,
    capture_output=True,
    text=True,
  )
  return name in result.stdout


def resolve_encoder(value):
  if value != "auto":
    return value
  return "h264_videotoolbox" if encoder_available("h264_videotoolbox") else "libx264"


def parse_overlay_plan(path):
  if not path:
    return []
  data = json.loads(Path(path).read_text(encoding="utf-8"))
  items = data.get("items", data) if isinstance(data, dict) else data
  if not isinstance(items, list):
    raise SystemExit("Overlay plan must be a list or an object with an items list.")
  return items


def overlay_position(position, margin):
  positions = {
    "top-left": (str(margin), str(margin)),
    "top-right": (f"W-w-{margin}", str(margin)),
    "bottom-left": (str(margin), f"H-h-{margin}"),
    "bottom-right": (f"W-w-{margin}", f"H-h-{margin}"),
    "center": ("(W-w)/2", "(H-h)/2"),
    "top-center": ("(W-w)/2", str(margin)),
  }
  return positions.get(position, positions["top-right"])


def add_encoder_args(command, encoder, args):
  command.extend(["-c:v", encoder])
  if encoder == "h264_videotoolbox":
    command.extend([
      "-b:v",
      args.video_bitrate,
      "-maxrate",
      args.video_maxrate,
      "-bufsize",
      args.video_bufsize,
      "-realtime",
      "true",
      "-allow_sw",
      "1",
    ])
  else:
    command.extend(["-preset", args.preset, "-crf", args.crf])


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--date", required=True)
  parser.add_argument("--content-type", "--column", dest="content_type", default="video-diary")
  parser.add_argument("--sequence", default="001")
  parser.add_argument("--input", required=True)
  parser.add_argument("--output", required=True)
  parser.add_argument("--ass-input")
  parser.add_argument("--duration")
  parser.add_argument("--crf", default="20")
  parser.add_argument("--preset", default="veryfast")
  parser.add_argument("--encoder", choices=["auto", "libx264", "h264_videotoolbox"], default="libx264")
  parser.add_argument("--video-bitrate", default="8M")
  parser.add_argument("--video-maxrate", default="12M")
  parser.add_argument("--video-bufsize", default="16M")
  parser.add_argument("--overlay-plan")
  parser.add_argument("--cover-input")
  parser.add_argument("--cover-duration", type=float, default=0.0)
  parser.add_argument("--dry-run", action="store_true")
  args = parser.parse_args()

  root = Path.cwd()
  input_path = Path(args.input)
  if not input_path.is_absolute():
    input_path = root / input_path
  ass_path = Path(args.ass_input) if args.ass_input else (
    content_media_dir(root, "04_videos", args.date, args.content_type, args.sequence)
    / "subtitles" / f"{args.date}_scripted.ass"
  )
  if not ass_path.is_absolute():
    ass_path = root / ass_path
  if not ass_path.exists():
    raise SystemExit(f"Missing ASS subtitle file: {ass_path}")

  filter_ass_path = prepare_filter_ass(ass_path, args.date)
  width, height, fps = probe_video(input_path)
  audio_enabled = has_audio(input_path)
  overlays = parse_overlay_plan(args.overlay_plan)
  encoder = resolve_encoder(args.encoder)

  command = [ffmpeg_bin(), "-hide_banner", "-y", "-i", str(input_path)]
  overlay_indexes = []
  for item in overlays:
    image_path = Path(item["path"])
    if not image_path.is_absolute():
      image_path = root / image_path
    if not image_path.exists():
      raise SystemExit(f"Missing overlay image: {image_path}")
    start_seconds = float(item["start"])
    end_seconds = float(item["end"])
    bounded_duration = max(0.01, end_seconds - start_seconds)
    command.extend(["-loop", "1", "-t", f"{bounded_duration:.3f}", "-i", str(image_path)])
    overlay_indexes.append(len(overlay_indexes) + 1)

  cover_index = None
  cover_path = None
  if args.cover_input and args.cover_duration > 0:
    cover_path = Path(args.cover_input)
    if not cover_path.is_absolute():
      cover_path = root / cover_path
    if not cover_path.exists():
      raise SystemExit(f"Missing cover image: {cover_path}")
    cover_index = len(overlays) + 1
    command.extend(["-loop", "1", "-t", f"{args.cover_duration:.3f}", "-i", str(cover_path)])

  if args.duration:
    total_duration = float(args.duration) + (args.cover_duration if cover_index is not None else 0.0)
    command.extend(["-t", f"{total_duration:.3f}"])

  filters = [f"[0:v]subtitles=filename={filter_ass_path}[v0]"]
  current_video = "v0"
  for sequence, (item, input_index) in enumerate(zip(overlays, overlay_indexes), 1):
    percent = max(0.05, min(1.0, float(item.get("widthPercent", 30)) / 100.0))
    overlay_width = max(2, int(width * percent) // 2 * 2)
    margin = int(item.get("margin", 40))
    x, y = overlay_position(item.get("position", "top-right"), margin)
    scaled = f"img{sequence}"
    output_label = f"v{sequence}"
    filters.append(
      f"[{input_index}:v]trim=duration={float(item['end']) - float(item['start']):.3f},"
      f"setpts=PTS-STARTPTS+{float(item['start']):.3f}/TB,scale={overlay_width}:-2[{scaled}]"
    )
    filters.append(
      f"[{current_video}][{scaled}]overlay={x}:{y}:"
      f"enable='between(t,{float(item['start']):.3f},{float(item['end']):.3f})'[{output_label}]"
    )
    current_video = output_label

  final_video_label = current_video
  final_audio_label = None
  if cover_index is not None:
    filters.append(
      f"[{cover_index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
      f"crop={width}:{height},setsar=1,fps={fps:.3f},trim=duration={args.cover_duration:.3f},"
      "setpts=PTS-STARTPTS[coverv]"
    )
    filters.append(f"[{current_video}]setpts=PTS-STARTPTS[mainv]")
    filters.append("[coverv][mainv]concat=n=2:v=1:a=0[vout]")
    final_video_label = "vout"
    if audio_enabled:
      filters.append(
        f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={args.cover_duration:.3f}[silence]"
      )
      filters.append("[silence][0:a]concat=n=2:v=0:a=1[aout]")
      final_audio_label = "aout"

  command.extend(["-filter_complex", ";".join(filters), "-map", f"[{final_video_label}]"])
  if final_audio_label:
    command.extend(["-map", f"[{final_audio_label}]"])
  elif audio_enabled:
    command.extend(["-map", "0:a?"])

  add_encoder_args(command, encoder, args)
  command.extend(["-pix_fmt", "yuv420p"])
  if final_audio_label:
    command.extend(["-c:a", "aac", "-b:a", "192k"])
  elif audio_enabled:
    command.extend(["-c:a", "copy"])
  command.extend(["-movflags", "+faststart", args.output])

  print(f"encoder={encoder}")
  print(f"overlay_count={len(overlays)}")
  print(f"cover_duration={args.cover_duration:.3f}")
  if args.dry_run:
    print(shlex.join(command))
    return
  subprocess.run(command, check=True)


if __name__ == "__main__":
  main()
