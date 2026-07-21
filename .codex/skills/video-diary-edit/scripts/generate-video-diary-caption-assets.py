from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import argparse
import re
import textwrap

from workflow_state import content_media_dir, content_text_path


VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
SUBTITLE_SAFE_MARGIN_X = int(VIDEO_WIDTH * 0.20)
SUBTITLE_MAX_WIDTH = VIDEO_WIDTH - SUBTITLE_SAFE_MARGIN_X * 2
SUBTITLE_BOTTOM_MARGIN = 286
SUBTITLE_BOX_PADDING_X = 30
SUBTITLE_BOX_PADDING_Y = 20
DEFAULT_DURATION = 192.468
FONT_CANDIDATES = [
  "/System/Library/Fonts/Hiragino Sans GB.ttc",
  "/System/Library/Fonts/STHeiti Medium.ttc",
  "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
  "/Library/Fonts/Arial Unicode.ttf",
  "/System/Library/Fonts/Supplemental/Songti.ttc",
]

CHINESE_FONT_CANDIDATES = [
  "/System/Library/Fonts/Hiragino Sans GB.ttc",
  "/System/Library/Fonts/STHeiti Medium.ttc",
  "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def load_font(size):
  for font_path in FONT_CANDIDATES:
    try:
      return ImageFont.truetype(font_path, size)
    except Exception:
      continue

  return ImageFont.load_default()


def load_font_from(candidates, size):
  for font_path in candidates:
    try:
      return ImageFont.truetype(font_path, size)
    except Exception:
      continue

  return load_font(size)


def load_chinese_font(size):
  return load_font_from(CHINESE_FONT_CANDIDATES, size)


def text_box(draw, text, font, stroke_width=0):
  return draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)


def text_size(draw, text, font, stroke_width=0):
  left, top, right, bottom = text_box(draw, text, font, stroke_width)
  return right - left, bottom - top


def centered_text(draw, text, y, font, fill, stroke_width=0, stroke_fill=None):
  width, _ = text_size(draw, text, font, stroke_width)
  draw.text(
    ((VIDEO_WIDTH - width) / 2, y),
    text,
    font=font,
    fill=fill,
    stroke_width=stroke_width,
    stroke_fill=stroke_fill,
  )


def centered_text_in_box(draw, text, x, y, box_width, font, fill):
  width, _ = text_size(draw, text, font)
  draw.text((x + (box_width - width) / 2, y), text, font=font, fill=fill)


def wrap_cjk(text, line_length):
  text = text.strip()
  if len(text) <= line_length:
    return [text]

  return textwrap.wrap(
    text,
    width=line_length,
    break_long_words=True,
    replace_whitespace=False,
  )


def wrap_text_by_width(draw, text, font, max_width, max_lines=4):
  text = text.strip()
  if not text:
    return []
  if text_size(draw, text, font)[0] <= max_width:
    return [text]

  chars = list(text)
  char_count = len(chars)
  width_cache = {}

  def measure(start, end):
    key = (start, end)
    if key not in width_cache:
      width_cache[key] = text_size(draw, "".join(chars[start:end]), font)[0]
    return width_cache[key]

  def collect_splits(start, remaining):
    if remaining == 1:
      if start < char_count and measure(start, char_count) <= max_width:
        return [[(start, char_count)]]
      return []

    splits = []
    min_end = start + 1
    max_end = char_count - remaining + 1
    for end in range(min_end, max_end + 1):
      if measure(start, end) > max_width:
        break
      for rest in collect_splits(end, remaining - 1):
        splits.append([(start, end)] + rest)

    return splits

  def score_split(split):
    widths = [measure(start, end) for start, end in split]
    lengths = [end - start for start, end in split]
    average_width = sum(widths) / len(widths)
    balance_score = sum((width - average_width) ** 2 for width in widths)
    short_last_penalty = 900000 if lengths[-1] <= 2 else 0
    uneven_last_penalty = 220000 if widths[-1] < average_width * 0.45 else 0

    return balance_score + short_last_penalty + uneven_last_penalty

  for line_count in range(2, min(max_lines, char_count) + 1):
    candidates = collect_splits(0, line_count)
    if candidates:
      best = min(candidates, key=score_split)
      return ["".join(chars[start:end]) for start, end in best]

  lines = []
  current = ""
  for char in text:
    candidate = current + char
    if current and text_size(draw, candidate, font)[0] > max_width:
      lines.append(current.rstrip())
      current = char.lstrip()
    else:
      current = candidate

  if current.strip():
    lines.append(current.strip())

  return lines


def extract_script_blocks(script_text):
  blocks = re.findall(
    r"### 提词器文案\s+```text\s+(.*?)\s+```",
    script_text,
    flags=re.S,
  )
  lines = []
  for block in blocks:
    for raw_line in block.splitlines():
      line = raw_line.strip()
      if line:
        lines.append(line)

  return lines


def split_caption_line(line):
  parts = []
  buffer = ""
  for char in line:
    buffer += char
    if char in "。！？!?":
      parts.append(buffer.strip())
      buffer = ""

  if buffer.strip():
    parts.append(buffer.strip())

  captions = []
  for part in parts:
    captions.extend(wrap_cjk(part, 18))

  return [caption for caption in captions if caption]


def build_caption_segments(lines, duration):
  captions = []
  for line in lines:
    captions.extend(split_caption_line(line))

  start = 1.4
  end = min(duration - 4.0, 188.0)
  span = max(1, end - start)
  weights = [max(1.25, min(4.2, len(caption) / 6.5)) for caption in captions]
  scale = span / sum(weights)
  segments = []
  cursor = start

  for caption, weight in zip(captions, weights):
    segment_duration = max(1.4, weight * scale)
    segment_end = min(cursor + segment_duration, end)
    if segment_end > cursor:
      segments.append((cursor, segment_end, caption))
    cursor = segment_end

  return segments


def srt_time(seconds):
  seconds = max(0, seconds)
  hours = int(seconds // 3600)
  minutes = int((seconds % 3600) // 60)
  whole_seconds = int(seconds % 60)
  milliseconds = int(round((seconds - int(seconds)) * 1000))
  if milliseconds == 1000:
    whole_seconds += 1
    milliseconds = 0

  return f"{hours:02}:{minutes:02}:{whole_seconds:02},{milliseconds:03}"


def ass_time(seconds):
  seconds = max(0, seconds)
  hours = int(seconds // 3600)
  minutes = int((seconds % 3600) // 60)
  whole_seconds = int(seconds % 60)
  centiseconds = int(round((seconds - int(seconds)) * 100))
  if centiseconds == 100:
    whole_seconds += 1
    centiseconds = 0

  return f"{hours}:{minutes:02}:{whole_seconds:02}.{centiseconds:02}"


def ass_escape(text):
  return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def parse_srt_timestamp(value):
  normalized = value.strip().replace(".", ",")
  time_part, milliseconds = normalized.split(",")
  hours, minutes, seconds = [int(part) for part in time_part.split(":")]

  return hours * 3600 + minutes * 60 + seconds + int(milliseconds) / 1000


def read_srt(path):
  text = path.read_text(encoding="utf-8-sig")
  blocks = re.split(r"\n\s*\n", text.strip())
  segments = []
  time_pattern = re.compile(
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})"
  )

  for block in blocks:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    time_index = None
    match = None
    for index, line in enumerate(lines):
      match = time_pattern.search(line)
      if match:
        time_index = index
        break

    if time_index is None or not match:
      continue

    caption = "\n".join(lines[time_index + 1:]).strip()
    caption = re.sub(r"<[^>]+>", "", caption).strip()
    if not caption:
      continue

    start = parse_srt_timestamp(match.group(1))
    end = parse_srt_timestamp(match.group(2))
    if end > start:
      segments.append((start, end, caption))

  return segments


def write_srt(path, segments):
  rows = []
  for index, (start, end, caption) in enumerate(segments, 1):
    rows.append(f"{index}\n{srt_time(start)} --> {srt_time(end)}\n{caption}\n")

  path.write_text("\n".join(rows), encoding="utf-8")


def write_ass(path, segments):
  header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Unicode MS,44,&H00FFFFFF,&H000000FF,&HCC000000,&H8A000000,-1,0,0,0,100,100,0,0,3,14,0,2,216,216,620,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
  lines = [header]
  for start, end, caption in segments:
    caption = caption.replace("\n", r"\N")
    lines.append(
      f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{ass_escape(caption)}"
    )

  path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_caption_png(path, caption):
  image = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
  draw = ImageDraw.Draw(image)
  font = load_chinese_font(44)
  lines = []
  for part in caption.splitlines():
    lines.extend(wrap_text_by_width(draw, part, font, SUBTITLE_MAX_WIDTH))
  line_height = 76
  total_height = line_height * len(lines)
  block_height = total_height + SUBTITLE_BOX_PADDING_Y * 2
  box_top = VIDEO_HEIGHT - SUBTITLE_BOTTOM_MARGIN - block_height
  box_left = SUBTITLE_SAFE_MARGIN_X - SUBTITLE_BOX_PADDING_X
  box_right = VIDEO_WIDTH - SUBTITLE_SAFE_MARGIN_X + SUBTITLE_BOX_PADDING_X
  box_bottom = box_top + block_height

  draw.rounded_rectangle(
    (box_left, box_top, box_right, box_bottom),
    radius=22,
    fill=(0, 0, 0, 112),
  )

  y = box_top + SUBTITLE_BOX_PADDING_Y - 3

  for line in lines:
    centered_text_in_box(
      draw,
      line,
      SUBTITLE_SAFE_MARGIN_X,
      y,
      SUBTITLE_MAX_WIDTH,
      font,
      fill=(255, 255, 255, 255),
    )
    y += line_height

  image.save(path)


def write_overlay_concat(path, blank_path, segments, caption_image_dir, duration):
  rows = []
  cursor = 0.0
  base_dir = path.parent

  def add_image(image_path, image_duration):
    if image_duration <= 0:
      return
    relative_path = image_path.relative_to(base_dir)
    rows.append(f"file '{relative_path}'")
    rows.append(f"duration {image_duration:.3f}")

  for index, (start, end, _) in enumerate(segments, 1):
    add_image(blank_path, start - cursor)
    add_image(caption_image_dir / f"caption_{index:03}.png", end - start)
    cursor = end

  add_image(blank_path, duration - cursor)
  rows.append(f"file '{blank_path.relative_to(base_dir)}'")
  path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_filter_script(path, segments):
  lines = []
  previous = "[0:v]"
  for index, (start, end, _) in enumerate(segments, 1):
    current = f"[v{index}]"
    input_label = f"[{index}:v]"
    lines.append(
      f"{previous}{input_label}overlay=0:0:enable='between(t,{start:.3f},{end:.3f})':eof_action=pass:repeatlast=0{current};"
    )
    previous = current

  lines.append(f"{previous}format=yuv420p[vout]")
  path.write_text("\n".join(lines), encoding="utf-8")


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--date", required=True)
  parser.add_argument("--content-type", "--column", dest="content_type", default="video-diary")
  parser.add_argument("--sequence", default="001")
  parser.add_argument("--duration", type=float, default=DEFAULT_DURATION)
  parser.add_argument("--srt-input")
  parser.add_argument("--ass-only", action="store_true")
  root = Path.cwd()
  args = parser.parse_args()

  script_path = content_text_path(root, "02_scripts", args.date, args.content_type, args.sequence)
  output_dir = content_media_dir(root, "04_videos", args.date, args.content_type, args.sequence)
  subtitle_dir = output_dir / "subtitles"
  caption_image_dir = subtitle_dir / "caption_png"

  subtitle_dir.mkdir(parents=True, exist_ok=True)
  caption_image_dir.mkdir(parents=True, exist_ok=True)

  subtitle_stem = "scripted"
  if args.srt_input:
    subtitle_stem = "transcribed"
    segments = read_srt(Path(args.srt_input))
    if not segments:
      raise SystemExit(f"No valid subtitle segments found in {args.srt_input}")
  else:
    script_text = script_path.read_text(encoding="utf-8")
    lines = extract_script_blocks(script_text)
    segments = build_caption_segments(lines[:], args.duration)

  write_srt(subtitle_dir / f"{args.date}_{subtitle_stem}.srt", segments)
  write_ass(subtitle_dir / f"{args.date}_{subtitle_stem}.ass", segments)
  if args.ass_only:
    print(f"captions={len(segments)}")
    print(f"srt={subtitle_dir / f'{args.date}_{subtitle_stem}.srt'}")
    print(f"ass={subtitle_dir / f'{args.date}_{subtitle_stem}.ass'}")
    return

  write_filter_script(subtitle_dir / f"{args.date}_caption_filter.ffmpeg", segments)

  for index, (_, _, caption) in enumerate(segments, 1):
    render_caption_png(caption_image_dir / f"caption_{index:03}.png", caption)

  blank_path = caption_image_dir / "blank.png"
  Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0)).save(blank_path)
  write_overlay_concat(
    subtitle_dir / f"{args.date}_overlay_concat.txt",
    blank_path,
    segments,
    caption_image_dir,
    args.duration,
  )

  print(f"captions={len(segments)}")
  print(f"srt={subtitle_dir / f'{args.date}_{subtitle_stem}.srt'}")


if __name__ == "__main__":
  main()
