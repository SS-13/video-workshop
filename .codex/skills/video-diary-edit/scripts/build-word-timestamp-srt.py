from pathlib import Path
import argparse
import csv
import json
import re


PROJECT_DICTIONARY = Path("11_templates/关键词收集/字幕纠错词库.tsv")
PUBLIC_DICTIONARY = Path("00_system/defaults/transcript-corrections.tsv")
DEFAULT_MAX_UNITS = 18.0
DEFAULT_MAX_DURATION = 2.8
DEFAULT_HARD_PAUSE = 0.62
DEFAULT_SOFT_PAUSE = 0.34
DEFAULT_PROTECTED_PHRASES = [
  "剧本沙",
  "剧本杀",
  "视频日记",
  "HyperFrames",
  "hyperframe",
  "Codex",
  "数字化转型",
  "互联网金融",
  "生产力",
  "碎碎念",
  "数字人格",
  "真人出镜",
  "企业家精神",
  "主创性",
  "社恐",
  "豁得出去",
  "非熟人圈子",
  "前沿阵地",
  "记录系统",
  "生活圈",
  "陌生人的反馈",
  "表达欲",
  "感谢",
  "正题",
]


def visual_units(text):
  total = 0.0
  for char in text:
    if char.isspace():
      total += 0.25
    elif ord(char) < 128:
      total += 0.55
    else:
      total += 1.0
  return total


def seconds_to_srt(seconds):
  seconds = max(0.0, seconds)
  millis_total = int(round(seconds * 1000))
  hours = millis_total // 3600000
  millis_total %= 3600000
  minutes = millis_total // 60000
  millis_total %= 60000
  whole_seconds = millis_total // 1000
  millis = millis_total % 1000
  return f"{hours:02}:{minutes:02}:{whole_seconds:02},{millis:03}"


def read_replacements(path):
  if not path.exists():
    return []

  replacements = []
  with path.open("r", encoding="utf-8-sig", newline="") as file:
    reader = csv.reader(file, delimiter="\t")
    for row in reader:
      if not row:
        continue
      source = row[0].strip()
      if not source or source.startswith("#") or len(row) < 2:
        continue
      target = row[1].strip()
      if target:
        replacements.append((source, target))
  return replacements


def parse_cli_replacements(values):
  replacements = []
  for value in values:
    if "=" not in value:
      raise SystemExit(f"Invalid --replace value: {value}")
    source, target = value.split("=", 1)
    source = source.strip()
    target = target.strip()
    if source and target:
      replacements.append((source, target))
  return replacements


def apply_replacements(text, replacements):
  updated = text
  for source, target in replacements:
    updated = updated.replace(source, target)
  return updated


def unique_values(values):
  seen = set()
  output = []
  for value in values:
    if not value or value in seen:
      continue
    seen.add(value)
    output.append(value)
  return output


def segment_words(data):
  segments = []
  for segment in data.get("segments", []):
    words = []
    for word in segment.get("words", []):
      text = str(word.get("word", "")).strip()
      if not text:
        continue
      start = word.get("start")
      end = word.get("end")
      if start is None or end is None or end <= start:
        continue
      words.append({
        "text": text,
        "start": float(start),
        "end": float(end),
      })
    if words:
      segments.append(words)
  return segments


def find_protected_spans(raw_text, phrases):
  candidates = []
  for phrase in unique_values(sorted(phrases, key=len, reverse=True)):
    start = 0
    while True:
      index = raw_text.find(phrase, start)
      if index < 0:
        break
      candidates.append((index, index + len(phrase)))
      start = index + 1

  selected = []
  occupied = set()
  for start, end in sorted(candidates, key=lambda item: (item[0], -(item[1] - item[0]))):
    positions = set(range(start, end))
    if occupied & positions:
      continue
    selected.append((start, end))
    occupied |= positions
  return sorted(selected)


def merge_protected_units(words, replacements, protected_phrases):
  if not words:
    return []

  offsets = []
  cursor = 0
  for word in words:
    start = cursor
    cursor += len(word["text"])
    offsets.append((start, cursor))

  raw_text = "".join(word["text"] for word in words)
  phrase_list = list(DEFAULT_PROTECTED_PHRASES)
  phrase_list.extend(source for source, _ in replacements)
  phrase_list.extend(target for _, target in replacements)
  phrase_list.extend(protected_phrases)

  spans = find_protected_spans(raw_text, phrase_list)
  span_by_start = {}
  for span_start, span_end in spans:
    word_indexes = [
      index for index, (word_start, word_end) in enumerate(offsets)
      if word_end > span_start and word_start < span_end
    ]
    if word_indexes:
      span_by_start[word_indexes[0]] = word_indexes[-1]

  units = []
  index = 0
  while index < len(words):
    if index in span_by_start:
      end_index = span_by_start[index]
      raw = "".join(word["text"] for word in words[index:end_index + 1])
      units.append({
        "text": apply_replacements(raw, replacements),
        "start": words[index]["start"],
        "end": words[end_index]["end"],
      })
      index = end_index + 1
      continue

    units.append({
      **words[index],
      "text": apply_replacements(words[index]["text"], replacements),
    })
    index += 1
  return units


def clean_caption(text):
  text = re.sub(r"\s+", "", text.strip())
  text = re.sub(r"^[，,、。！？!?；;：:\s]+", "", text)
  text = re.sub(r"[，,、\s]+$", "", text)
  return text


def caption_text(words, replacements):
  raw = "".join(word["text"] for word in words)
  return clean_caption(apply_replacements(raw, replacements))


def should_break(current_words, next_word, replacements, args):
  if not current_words:
    return False

  gap = next_word["start"] - current_words[-1]["end"]
  current_text = caption_text(current_words, replacements)
  candidate_text = caption_text(current_words + [next_word], replacements)
  current_duration = current_words[-1]["end"] - current_words[0]["start"]
  candidate_duration = next_word["end"] - current_words[0]["start"]

  if gap >= args.hard_pause:
    return True
  if visual_units(candidate_text) > args.max_units:
    return True
  if candidate_duration > args.max_duration and visual_units(current_text) >= args.min_units:
    return True
  if gap >= args.soft_pause and visual_units(current_text) >= args.soft_break_units:
    return True
  return False


def build_blocks(words, replacements, args):
  blocks = []
  current_words = []

  for word in words:
    if should_break(current_words, word, replacements, args):
      text = caption_text(current_words, replacements)
      if text:
        blocks.append((current_words[0]["start"], current_words[-1]["end"], text))
      current_words = []
    current_words.append(word)

  if current_words:
    text = caption_text(current_words, replacements)
    if text:
      blocks.append((current_words[0]["start"], current_words[-1]["end"], text))

  return blocks


def build_segmented_blocks(segments, replacements, args):
  blocks = []
  for words in segments:
    units = merge_protected_units(words, replacements, args.protect)
    blocks.extend(build_blocks(units, replacements, args))
  return blocks


def write_srt(path, blocks):
  rows = []
  for index, (start, end, text) in enumerate(blocks, 1):
    rows.append(str(index))
    rows.append(f"{seconds_to_srt(start)} --> {seconds_to_srt(end)}")
    rows.append(text)
    rows.append("")
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text("\n".join(rows).rstrip() + "\n", encoding="utf-8")


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--input-json", required=True)
  parser.add_argument("--output-srt", required=True)
  parser.add_argument("--max-units", type=float, default=DEFAULT_MAX_UNITS)
  parser.add_argument("--min-units", type=float, default=8.0)
  parser.add_argument("--soft-break-units", type=float, default=11.0)
  parser.add_argument("--max-duration", type=float, default=DEFAULT_MAX_DURATION)
  parser.add_argument("--hard-pause", type=float, default=DEFAULT_HARD_PAUSE)
  parser.add_argument("--soft-pause", type=float, default=DEFAULT_SOFT_PAUSE)
  parser.add_argument("--replace", action="append", default=[])
  parser.add_argument("--protect", action="append", default=[])
  args = parser.parse_args()

  root = Path.cwd()
  input_json = Path(args.input_json)
  output_srt = Path(args.output_srt)
  if not input_json.is_absolute():
    input_json = root / input_json
  if not output_srt.is_absolute():
    output_srt = root / output_srt

  replacements = []
  replacements.extend(read_replacements(root / PROJECT_DICTIONARY))
  replacements.extend(read_replacements(root / PUBLIC_DICTIONARY))
  replacements.extend(parse_cli_replacements(args.replace))

  data = json.loads(input_json.read_text(encoding="utf-8"))
  segments = segment_words(data)
  words = [word for segment in segments for word in segment]
  blocks = build_segmented_blocks(segments, replacements, args)
  write_srt(output_srt, blocks)

  long_blocks = [block for block in blocks if visual_units(block[2]) > args.max_units]
  print(f"input_json={input_json}")
  print(f"output_srt={output_srt}")
  print(f"segments={len(segments)}")
  print(f"words={len(words)}")
  print(f"blocks={len(blocks)}")
  print(f"long_blocks={len(long_blocks)}")


if __name__ == "__main__":
  main()
