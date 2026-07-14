from pathlib import Path
import argparse
import json
import math
import os
import shutil
import subprocess
import wave

from workflow_state import file_fingerprint, value_fingerprint


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".MP4", ".MOV", ".M4V"}
FFMPEG_FULL = Path("/usr/local/opt/ffmpeg-full/bin/ffmpeg")
USER_WHISPER = Path.home() / "Library" / "Python" / "3.9" / "bin" / "whisper"
WHISPER_CPP = Path("/usr/local/bin/whisper-cli")
WHISPER_CPP_MODEL_DIR = Path.home() / ".cache" / "whisper.cpp"
MAX_PROMPT_CHARS = 600


def natural_key(path):
  return path.name.lower()


def find_default_input(root, date):
  recording_dir = root / "03_recordings" / date
  if not recording_dir.exists():
    raise SystemExit(f"Missing recording directory: {recording_dir}")

  videos = sorted(
    [path for path in recording_dir.iterdir() if path.suffix in VIDEO_EXTENSIONS],
    key=natural_key,
  )
  if not videos:
    raise SystemExit(f"No video files found in {recording_dir}")
  return videos[0]


def find_whisper():
  whisper = shutil.which("whisper")
  if whisper:
    return whisper
  if USER_WHISPER.exists():
    return str(USER_WHISPER)
  raise SystemExit(
    "Missing transcription tool: whisper\n"
    "Install one local transcription tool first, then rerun this command.\n"
    "Recommended MVP: python3 -m pip install -U openai-whisper"
  )


def find_whisper_cpp():
  value = os.environ.get("WHISPER_CPP_BIN")
  if value and Path(value).exists():
    return value
  executable = shutil.which("whisper-cli")
  if executable:
    return executable
  if WHISPER_CPP.exists():
    return str(WHISPER_CPP)
  return None


def whisper_cpp_model(model, explicit_path=None):
  if explicit_path:
    path = Path(explicit_path)
    return path if path.exists() else None
  env_path = os.environ.get("WHISPER_CPP_MODEL")
  if env_path and Path(env_path).exists():
    return Path(env_path)
  path = WHISPER_CPP_MODEL_DIR / f"ggml-{model}.bin"
  return path if path.exists() else None


def ffmpeg_bin():
  return os.environ.get("FFMPEG_BIN") or (str(FFMPEG_FULL) if FFMPEG_FULL.exists() else "ffmpeg")


def resolve_path(root, value):
  path = Path(value)
  return path if path.is_absolute() else root / path


def seconds_to_srt(seconds):
  millis_total = int(round(max(0.0, seconds) * 1000))
  hours = millis_total // 3600000
  millis_total %= 3600000
  minutes = millis_total // 60000
  millis_total %= 60000
  whole_seconds = millis_total // 1000
  millis = millis_total % 1000
  return f"{hours:02}:{minutes:02}:{whole_seconds:02},{millis:03}"


def write_segment_srt(json_path, output_path):
  data = json.loads(json_path.read_text(encoding="utf-8"))
  rows = []
  for index, segment in enumerate(data.get("segments", []), 1):
    text = str(segment.get("text", "")).strip()
    start = segment.get("start")
    end = segment.get("end")
    if not text or start is None or end is None or end <= start:
      continue
    rows.extend([
      str(index),
      f"{seconds_to_srt(float(start))} --> {seconds_to_srt(float(end))}",
      text,
      "",
    ])
  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text("\n".join(rows).rstrip() + "\n", encoding="utf-8")


def canonicalize_whisper_cpp(input_path, output_path):
  raw = json.loads(input_path.read_text(encoding="utf-8"))
  segments = []
  full_text = []
  for index, item in enumerate(raw.get("transcription", [])):
    words = []
    probabilities = []
    for token in item.get("tokens", []):
      text = str(token.get("text", ""))
      offsets = token.get("offsets", {})
      start = offsets.get("from")
      end = offsets.get("to")
      if not text or text.startswith("[") or start is None or end is None or end <= start:
        continue
      probability = max(1e-6, float(token.get("p", 0.0)))
      probabilities.append(probability)
      words.append({
        "word": text,
        "start": float(start) / 1000.0,
        "end": float(end) / 1000.0,
        "probability": round(probability, 6),
      })

    offsets = item.get("offsets", {})
    segment_text = str(item.get("text", "")).strip()
    full_text.append(segment_text)
    avg_logprob = sum(math.log(value) for value in probabilities) / len(probabilities) if probabilities else -10.0
    segments.append({
      "id": index,
      "start": float(offsets.get("from", 0)) / 1000.0,
      "end": float(offsets.get("to", 0)) / 1000.0,
      "text": segment_text,
      "avg_logprob": avg_logprob,
      "no_speech_prob": 0.0,
      "compression_ratio": 0.0,
      "words": words,
    })

  canonical = {
    "text": "".join(full_text),
    "language": raw.get("result", {}).get("language", "zh"),
    "segments": segments,
    "engine": "whisper.cpp",
    "engineMetadata": {
      "systemInfo": raw.get("systeminfo", ""),
      "model": raw.get("model", {}).get("type", ""),
    },
  }
  output_path.write_text(json.dumps(canonical, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_whisper_cpp(audio_path, json_output, model_path, language, initial_prompt):
  whisper_cpp = find_whisper_cpp()
  if not whisper_cpp or not model_path:
    raise SystemExit("whisper.cpp executable or model is missing")

  with wave.open(str(audio_path), "rb") as audio_file:
    duration_ms = int(round(audio_file.getnframes() / audio_file.getframerate() * 1000))
  raw_prefix = json_output.parent / f"{json_output.stem}_whisper_cpp_raw"
  command = [
    whisper_cpp,
    "-m",
    str(model_path),
    "-f",
    str(audio_path),
    "-l",
    "zh" if language.lower() in ("chinese", "mandarin", "zh") else language,
    "-ojf",
    "-of",
    str(raw_prefix),
    "-sow",
    "-d",
    str(duration_ms),
    "-t",
    str(max(4, min(8, os.cpu_count() or 4))),
    "-np",
  ]
  if initial_prompt:
    command.extend(["--prompt", initial_prompt])
  subprocess.run(command, check=True)
  raw_json = raw_prefix.with_suffix(".json")
  if not raw_json.exists():
    raise SystemExit(f"whisper.cpp finished, but JSON was not found: {raw_json}")
  canonicalize_whisper_cpp(raw_json, json_output)


def build_prompt(values, prompt_files):
  parts = [value.strip() for value in values if value and value.strip()]
  for path in prompt_files:
    if path.exists():
      parts.append(path.read_text(encoding="utf-8-sig").strip())
  prompt = "\n".join(parts)
  return prompt[:MAX_PROMPT_CHARS]


def extract_audio(input_path, audio_path, force):
  metadata_path = audio_path.with_suffix(audio_path.suffix + ".meta.json")
  fingerprint = file_fingerprint(input_path)
  if not force and audio_path.exists() and metadata_path.exists():
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("inputFingerprint") == fingerprint:
      return True

  audio_path.parent.mkdir(parents=True, exist_ok=True)
  command = [
    ffmpeg_bin(),
    "-hide_banner",
    "-y",
    "-i",
    str(input_path),
    "-vn",
    "-ac",
    "1",
    "-ar",
    "16000",
    "-c:a",
    "pcm_s16le",
    str(audio_path),
  ]
  subprocess.run(command, check=True)
  metadata_path.write_text(
    json.dumps({"inputFingerprint": fingerprint}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
  )
  return False


def run_legacy_srt(input_path, output_path, model, language):
  whisper = find_whisper()
  output_dir = output_path.parent
  output_dir.mkdir(parents=True, exist_ok=True)
  command = [
    whisper,
    str(input_path),
    "--language",
    language,
    "--task",
    "transcribe",
    "--model",
    model,
    "--output_dir",
    str(output_dir),
    "--output_format",
    "srt",
    "--fp16",
    "False",
  ]
  subprocess.run(command, check=True)
  whisper_output = output_dir / f"{input_path.stem}.srt"
  if not whisper_output.exists():
    raise SystemExit(f"Whisper finished, but SRT was not found: {whisper_output}")
  if whisper_output != output_path:
    output_path.write_text(whisper_output.read_text(encoding="utf-8"), encoding="utf-8")


def run_word_json(
  input_path,
  output_path,
  json_output,
  model,
  language,
  initial_prompt,
  metadata_path,
  force,
  engine,
  whisper_cpp_model_path,
):
  selected_engine = engine
  cpp_model = whisper_cpp_model(model, whisper_cpp_model_path)
  if selected_engine == "auto":
    selected_engine = "whisper-cpp" if find_whisper_cpp() and cpp_model else "openai-whisper"
  params = {
    "model": model,
    "language": language,
    "initialPromptHash": value_fingerprint(initial_prompt),
    "wordTimestamps": True,
    "engine": selected_engine,
  }
  input_fingerprint = file_fingerprint(input_path)
  if not force and output_path.exists() and json_output.exists() and metadata_path.exists():
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("inputFingerprint") == input_fingerprint and metadata.get("params") == params:
      return True

  output_dir = json_output.parent
  output_dir.mkdir(parents=True, exist_ok=True)
  if selected_engine == "whisper-cpp":
    run_whisper_cpp(input_path, json_output, cpp_model, language, initial_prompt)
  else:
    whisper = find_whisper()
    command = [
      whisper,
      str(input_path),
      "--language",
      language,
      "--task",
      "transcribe",
      "--model",
      model,
      "--output_dir",
      str(output_dir),
      "--output_format",
      "json",
      "--word_timestamps",
      "True",
      "--fp16",
      "False",
      "--verbose",
      "False",
    ]
    if initial_prompt:
      command.extend(["--initial_prompt", initial_prompt])
    subprocess.run(command, check=True)
    whisper_json = output_dir / f"{input_path.stem}.json"
    if not whisper_json.exists():
      raise SystemExit(f"Whisper finished, but JSON was not found: {whisper_json}")
    if whisper_json != json_output:
      json_output.write_text(whisper_json.read_text(encoding="utf-8"), encoding="utf-8")
  write_segment_srt(json_output, output_path)
  metadata_path.write_text(
    json.dumps(
      {"inputFingerprint": input_fingerprint, "params": params},
      ensure_ascii=False,
      indent=2,
    ) + "\n",
    encoding="utf-8",
  )
  return False


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--date", required=True)
  parser.add_argument("--input")
  parser.add_argument("--output")
  parser.add_argument("--json-output")
  parser.add_argument("--audio-cache")
  parser.add_argument("--model", default="small")
  parser.add_argument("--language", default="Chinese")
  parser.add_argument("--initial-prompt", action="append", default=[])
  parser.add_argument("--prompt-file", action="append", default=[])
  parser.add_argument("--word-timestamps", action="store_true")
  parser.add_argument("--engine", choices=["auto", "whisper-cpp", "openai-whisper"], default="auto")
  parser.add_argument("--whisper-cpp-model")
  parser.add_argument("--force", action="store_true")
  args = parser.parse_args()

  root = Path.cwd()
  input_path = resolve_path(root, args.input) if args.input else find_default_input(root, args.date)
  output_path = resolve_path(root, args.output) if args.output else (
    root / "04_videos" / args.date / "subtitles" / f"{args.date}_transcribed.srt"
  )

  if not args.word_timestamps and not args.json_output and not args.audio_cache:
    run_legacy_srt(input_path, output_path, args.model, args.language)
    print(f"srt={output_path}")
    print("engine=legacy")
    return

  json_output = resolve_path(root, args.json_output) if args.json_output else output_path.with_suffix(".json")
  audio_path = resolve_path(root, args.audio_cache) if args.audio_cache else (
    output_path.parent / f"{input_path.stem}_16k.wav"
  )
  prompt_files = [resolve_path(root, value) for value in args.prompt_file]
  initial_prompt = build_prompt(args.initial_prompt, prompt_files)
  audio_cache_hit = extract_audio(input_path, audio_path, args.force)
  metadata_path = json_output.with_suffix(json_output.suffix + ".meta.json")
  transcription_cache_hit = run_word_json(
    audio_path,
    output_path,
    json_output,
    args.model,
    args.language,
    initial_prompt,
    metadata_path,
    args.force,
    args.engine,
    args.whisper_cpp_model,
  )

  print(f"srt={output_path}")
  print(f"json={json_output}")
  print(f"audio={audio_path}")
  print(f"audio_cache_hit={str(audio_cache_hit).lower()}")
  print(f"transcription_cache_hit={str(transcription_cache_hit).lower()}")
  metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
  print(f"engine={metadata['params']['engine']}")


if __name__ == "__main__":
  main()
