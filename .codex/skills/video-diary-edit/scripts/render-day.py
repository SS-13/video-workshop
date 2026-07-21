from pathlib import Path
import os
import subprocess
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[3]
TOOLS_DIR = PROJECT_ROOT / "09_tools"
sys.path.insert(0, str(TOOLS_DIR))

from video_production_core.media_retention import (  # noqa: E402
  MediaRetentionError,
  disk_space_status,
)


VALID_ENGINES = {"v2", "legacy"}


def extract_engine(arguments):
  engine = os.environ.get("VIDEO_DIARY_EDIT_ENGINE", "v2")
  cleaned = []
  index = 0
  while index < len(arguments):
    value = arguments[index]
    if value == "--engine":
      if index + 1 >= len(arguments):
        raise SystemExit("--engine requires v2 or legacy")
      engine = arguments[index + 1]
      index += 2
      continue
    if value.startswith("--engine="):
      engine = value.split("=", 1)[1]
      index += 1
      continue
    cleaned.append(value)
    index += 1
  if engine not in VALID_ENGINES:
    raise SystemExit(f"Unknown engine: {engine}. Use v2 or legacy.")
  return engine, cleaned


def needs_legacy(arguments):
  if "--mode" in arguments:
    index = arguments.index("--mode")
    if index + 1 < len(arguments) and arguments[index + 1] == "polished":
      return True
  for value in arguments:
    if value in ("--from-stage=check", "--from-stage=ass", "--from-stage=render"):
      return True
  if "--from-stage" in arguments:
    index = arguments.index("--from-stage")
    if index + 1 < len(arguments) and arguments[index + 1] in ("check", "ass", "render"):
      return True
  return False


def translate_v2_arguments(arguments):
  translated = []
  skip_next = False
  for index, value in enumerate(arguments):
    if skip_next:
      skip_next = False
      continue
    if value == "--stop-after-srt":
      translated.append("--stop-after-review")
      continue
    if value == "--mode":
      skip_next = True
      continue
    if value.startswith("--mode="):
      continue
    translated.append(value)
  return translated


def main():
  try:
    disk = disk_space_status(PROJECT_ROOT)
  except MediaRetentionError as error:
    raise SystemExit(f"render_preflight=failed\nreason={error}") from error
  if not disk["ready"]:
    print("render_preflight=failed")
    print("reason=insufficient-disk-space")
    print(f"free_bytes={disk['freeBytes']}")
    print(f"minimum_free_bytes={disk['minimumFreeBytes']}")
    raise SystemExit(2)
  print("render_preflight=pass")
  print(f"free_bytes={disk['freeBytes']}")

  engine, arguments = extract_engine(sys.argv[1:])
  if engine == "v2" and needs_legacy(arguments):
    print("engine_fallback=legacy")
    print("reason=polished_or_legacy_resume_stage")
    engine = "legacy"

  if engine == "v2":
    script = SCRIPT_DIR / "render-day-v2.py"
    arguments = translate_v2_arguments(arguments)
  else:
    script = SCRIPT_DIR / "render-day-legacy.py"

  print(f"engine={engine}")
  subprocess.run([sys.executable, str(script), *arguments], check=True)


if __name__ == "__main__":
  main()
