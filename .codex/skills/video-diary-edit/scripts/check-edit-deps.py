from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import sys


FFMPEG_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffmpeg")
USER_WHISPER = Path.home() / "Library" / "Python" / "3.9" / "bin" / "whisper"
WHISPER_CPP = Path("/usr/local/bin/whisper-cli")
WHISPER_CPP_BASE_MODEL = Path.home() / ".cache" / "whisper.cpp" / "ggml-base.bin"
REQUIRED_FILTERS = ["ass", "subtitles", "drawtext"]


def find_executable(name, candidates=None):
  env_name = f"{name.upper()}_BIN"
  env_value = os.environ.get(env_name)
  if env_value:
    path = Path(env_value)
    if path.exists():
      return str(path)

  for candidate in candidates or []:
    if candidate.exists():
      return str(candidate)

  return shutil.which(name)


def run_command(command):
  return subprocess.run(
    command,
    text=True,
    capture_output=True,
    check=False,
  )


def check_pillow(results):
  spec = importlib.util.find_spec("PIL")
  if not spec:
    results.append(("missing", "Pillow", "Install with: python3 -m pip install -U Pillow"))
    return

  try:
    from PIL import __version__ as pillow_version
  except Exception:
    pillow_version = "unknown"

  results.append(("ok", "Pillow", pillow_version))


def parse_filter_names(output):
  names = set()
  for line in output.splitlines():
    parts = line.split()
    if len(parts) >= 2:
      names.add(parts[1])
  return names


def check_ffmpeg(results):
  ffmpeg = find_executable("ffmpeg", [FFMPEG_FULL])
  if not ffmpeg:
    results.append(("missing", "ffmpeg", "Install ffmpeg-full or put ffmpeg in PATH."))
    return None

  probe_candidates = [Path(ffmpeg).with_name("ffprobe")]
  ffprobe = find_executable("ffprobe", probe_candidates)
  if not ffprobe:
    results.append(("missing", "ffprobe", "Install ffmpeg-full or put ffprobe in PATH."))
  else:
    results.append(("ok", "ffprobe", ffprobe))

  result = run_command([ffmpeg, "-hide_banner", "-filters"])
  if result.returncode != 0:
    results.append(("missing", "ffmpeg filters", result.stderr.strip() or "Cannot inspect ffmpeg filters."))
    return ffmpeg

  filter_names = parse_filter_names(result.stdout)
  missing_filters = [name for name in REQUIRED_FILTERS if name not in filter_names]
  if missing_filters:
    results.append((
      "missing",
      "ffmpeg filters",
      "Missing filters: " + ", ".join(missing_filters),
    ))
  else:
    results.append(("ok", "ffmpeg filters", ", ".join(REQUIRED_FILTERS)))

  results.append(("ok", "ffmpeg", ffmpeg))
  return ffmpeg


def check_whisper(results):
  whisper = find_executable("whisper", [USER_WHISPER])
  whisper_cpp = find_executable("whisper-cli", [WHISPER_CPP])
  if whisper_cpp and WHISPER_CPP_BASE_MODEL.exists():
    results.append(("ok", "whisper.cpp", f"{whisper_cpp} | {WHISPER_CPP_BASE_MODEL}"))
  elif whisper:
    results.append(("ok", "openai-whisper fallback", whisper))
  else:
    results.append((
      "missing",
      "local transcription",
      "Install whisper.cpp + ggml-base.bin, or openai-whisper.",
    ))
    return
  if whisper:
    results.append(("ok", "openai-whisper legacy", whisper))


def main():
  results = []
  check_pillow(results)
  check_ffmpeg(results)
  check_whisper(results)

  missing = [item for item in results if item[0] != "ok"]
  for status, name, detail in results:
    print(f"{status.upper()}\t{name}\t{detail}")

  if missing:
    print(f"SUMMARY\tmissing={len(missing)}")
    raise SystemExit(1)

  print("SUMMARY\tok")


if __name__ == "__main__":
  main()
