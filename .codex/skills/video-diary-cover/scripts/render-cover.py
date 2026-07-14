from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import argparse
import json
import os


DEFAULT_COVER_WIDTH = 1080
DEFAULT_COVER_HEIGHT = 1440
COVER_WIDTH = DEFAULT_COVER_WIDTH
COVER_HEIGHT = DEFAULT_COVER_HEIGHT
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ROUTES_PATH = SKILL_DIR / "references" / "cover-routes.json"

CUSTOM_FONT = os.environ.get("VIDEO_WORKSHOP_FONT", "").strip()
DISPLAY_FONTS = [
  CUSTOM_FONT,
  "/System/Library/Fonts/STHeiti Medium.ttc",
  "/System/Library/Fonts/Hiragino Sans GB.ttc",
  "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
  "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
  "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
  "C:/Windows/Fonts/msyhbd.ttc",
  "C:/Windows/Fonts/msyh.ttc",
]
META_FONTS = [
  CUSTOM_FONT,
  "/System/Library/Fonts/Hiragino Sans GB.ttc",
  "/System/Library/Fonts/STHeiti Medium.ttc",
  "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
  "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
  "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
  "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
  "C:/Windows/Fonts/msyh.ttc",
  "C:/Windows/Fonts/msyhbd.ttc",
]
DISPLAY_FONTS = [value for value in DISPLAY_FONTS if value]
META_FONTS = [value for value in META_FONTS if value]


DEFAULT_ROUTES = {
  "defaultRoute": "video-diary",
  "routes": {
    "video-diary": {
      "defaultVersion": "v1.2",
      "aliases": ["视频日记", "video-diary"],
      "versions": {
        "v1.2": {
          "seriesLabel": "视频日记",
          "titleMode": "free-title",
          "metaSecondTemplate": "持续记录 {day_compact}",
          "accentColor": [255, 216, 0, 245],
          "tagTextColor": [20, 20, 20, 255],
          "titleFill": [255, 255, 255, 255],
          "titleOutline": [18, 18, 18, 210],
          "titleShadow": [0, 0, 0, 78],
          "panelAlpha": 48,
          "titleY": 500,
          "noteY": 1280,
          "contrast": 1.07,
          "color": 0.96,
          "labelUnderlineWidth": 318
        }
      }
    },
    "suisuinian": {
      "defaultVersion": "v0.1",
      "aliases": ["碎碎念", "碎碎念儿", "随手记录"],
      "versions": {
        "v0.1": {
          "seriesLabel": "碎碎念",
          "titleMode": "fixed-title",
          "fixedTitle": "碎碎念",
          "metaSecondTemplate": "随手记录",
          "accentColor": [159, 232, 112, 245],
          "tagTextColor": [18, 28, 18, 255],
          "titleFill": [255, 255, 255, 255],
          "titleOutline": [18, 18, 18, 190],
          "titleShadow": [0, 0, 0, 70],
          "panelAlpha": 38,
          "titleY": 520,
          "noteY": 1280,
          "contrast": 1.03,
          "color": 0.94,
          "labelUnderlineWidth": 250
        }
      }
    },
    "reading-note": {
      "defaultVersion": "v0.1",
      "aliases": ["读书笔记", "读书日记", "reading-note"],
      "versions": {
        "v0.1": {
          "seriesLabel": "读书笔记",
          "titleMode": "book-title",
          "metaSecondTemplate": "阅读记录",
          "accentColor": [255, 202, 78, 245],
          "tagTextColor": [26, 22, 16, 255],
          "titleFill": [255, 255, 255, 255],
          "titleOutline": [16, 16, 16, 205],
          "titleShadow": [0, 0, 0, 86],
          "panelAlpha": 58,
          "titleY": 500,
          "noteY": 1280,
          "contrast": 1.05,
          "color": 0.90,
          "labelUnderlineWidth": 318
        }
      }
    }
  }
}


def load_routes():
  if not ROUTES_PATH.exists():
    return DEFAULT_ROUTES
  with ROUTES_PATH.open("r", encoding="utf-8") as file:
    return json.load(file)


def normalize_route(value, routes):
  requested = (value or routes.get("defaultRoute") or "video-diary").strip()
  if requested in routes["routes"]:
    return requested

  for route_name, route in routes["routes"].items():
    aliases = route.get("aliases", [])
    if requested in aliases:
      return route_name

  valid = ", ".join(routes["routes"].keys())
  raise SystemExit(f"Unknown cover route: {requested}. Valid routes: {valid}")


def pick_style(routes, route_name, version):
  route = routes["routes"][route_name]
  style_version = version or route.get("defaultVersion")
  versions = route.get("versions", {})
  if style_version not in versions:
    valid = ", ".join(versions.keys())
    raise SystemExit(f"Unknown style version for {route_name}: {style_version}. Valid versions: {valid}")
  return style_version, versions[style_version]


def color(value):
  if isinstance(value, str):
    stripped = value.lstrip("#")
    if len(stripped) == 6:
      return tuple(int(stripped[i:i + 2], 16) for i in (0, 2, 4)) + (255,)
    if len(stripped) == 8:
      return tuple(int(stripped[i:i + 2], 16) for i in (0, 2, 4, 6))
  return tuple(value)


def load_font(size, candidates, strict=False):
  for font_path in candidates:
    try:
      return ImageFont.truetype(font_path, size)
    except Exception:
      continue
  if strict:
    raise SystemExit("No configured font could be loaded: " + ", ".join(candidates))
  return ImageFont.load_default()


def text_size(draw, text, font, stroke_width=0):
  left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
  return right - left, bottom - top


def fit_font(draw, text, start, min_size, max_width, stroke_width=0, font_candidates=None):
  candidates = font_candidates or DISPLAY_FONTS
  for size in range(start, min_size - 1, -2):
    font = load_font(size, candidates, strict=True)
    width, _ = text_size(draw, text, font, stroke_width)
    if width <= max_width:
      return font
  return load_font(min_size, candidates, strict=True)


def crop_to_cover(image):
  src_width, src_height = image.size
  crop_height = int(src_width * COVER_HEIGHT / COVER_WIDTH)
  if crop_height <= src_height:
    top = int((src_height - crop_height) * 0.28)
    return image.crop((0, top, src_width, top + crop_height))

  crop_width = int(src_height * COVER_WIDTH / COVER_HEIGHT)
  left = (src_width - crop_width) // 2
  return image.crop((left, 0, left + crop_width, src_height))


def split_title(title):
  title = (title or "").strip()
  if not title:
    return "", ""
  if len(title) <= 6:
    return title, ""

  split_at = len(title) // 2
  punctuation = "，,：:、｜| "
  best = split_at
  for distance in range(0, max(1, len(title) // 2)):
    for candidate in (split_at - distance, split_at + distance):
      if 1 <= candidate < len(title) and title[candidate - 1] in punctuation:
        best = candidate
        break
    else:
      continue
    break

  return title[:best].strip(punctuation), title[best:].strip(punctuation)


def format_book_title(title):
  title = (title or "").strip()
  if not title:
    return ""
  if title.startswith("《") and title.endswith("》"):
    return title
  return f"《{title.strip('《》')}》"


def resolve_title_content(args, style):
  title_mode = style.get("titleMode", "free-title")
  subtitle = (args.subtitle or args.tagline or "").strip()
  note = (args.note or "").strip()

  if title_mode == "fixed-title":
    fixed_title = style.get("fixedTitle") or style.get("seriesLabel", "")
    if not subtitle and args.title and args.title.strip() != fixed_title:
      subtitle = args.title.strip()
    title_line_1, title_line_2 = split_title(fixed_title)
    return title_line_1, title_line_2, subtitle, note

  if title_mode == "book-title":
    if args.title_line_1:
      return args.title_line_1, args.title_line_2, subtitle, note

    book_title = args.book_title or args.title
    book_title = format_book_title(book_title)
    if not book_title:
      raise SystemExit("Missing book title. Use --book-title or --title for reading-note covers.")
    title_line_1, title_line_2 = split_title(book_title)
    return title_line_1, title_line_2, subtitle, note

  title_line_1 = args.title_line_1
  title_line_2 = args.title_line_2
  if args.title and not title_line_1:
    title_line_1, title_line_2 = split_title(args.title)
  if not title_line_1:
    raise SystemExit("Missing title. Use --title or --title-line-1.")
  return title_line_1, title_line_2, subtitle, note


def format_meta_second(template, day_label):
  day_label = (day_label or "").strip()
  day_compact = day_label.replace(" ", "") if day_label else ""
  if "{day_compact}" in template and not day_compact:
    return template.replace("{day_compact}", "").strip()
  return template.format(day_label=day_label, day_compact=day_compact).strip()


def draw_fat_center_text(draw, text, y, font, style):
  if not text:
    return 0

  outline_width = int(style.get("titleOutlineWidth", 5))
  width, height = text_size(draw, text, font, outline_width)
  x = (COVER_WIDTH - width) / 2
  outline = color(style.get("titleOutline", [18, 18, 18, 210]))
  shadow = color(style.get("titleShadow", [0, 0, 0, 78]))
  fill = color(style.get("titleFill", [255, 255, 255, 255]))

  draw.text(
    (x + 8, y + 12),
    text,
    font=font,
    fill=shadow,
    stroke_width=outline_width,
    stroke_fill=shadow,
  )
  draw.text(
    (x, y),
    text,
    font=font,
    fill=fill,
    stroke_width=outline_width,
    stroke_fill=outline,
  )

  # Add a controlled face boost; too much closes counters in dense Chinese glyphs.
  face_boost = int(style.get("titleFaceBoost", 4))
  if face_boost <= 0:
    offsets = [(0, 0)]
  elif face_boost == 1:
    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1), (0, 0)]
  elif face_boost == 2:
    offsets = [(-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, -1), (-1, 1), (1, 1), (0, 0)]
  else:
    offsets = [(-4, 0), (4, 0), (0, -4), (0, 4), (-3, -2), (3, -2), (-3, 2), (3, 2), (-2, 0), (2, 0), (0, 0)]
  for dx, dy in offsets:
    draw.text((x + dx, y + dy), text, font=font, fill=fill)
  return height


def draw_header(draw, args, style):
  white = (255, 255, 255, 255)
  black = (0, 0, 0, 220)
  muted = (255, 255, 255, 220)
  meta_max_width = max(280, int(COVER_WIDTH * 0.46))
  small = fit_font(draw, args.meta_line_1 or args.date.replace("-", "."), int(style.get("metaSize", 48)), 28, meta_max_width, stroke_width=2, font_candidates=META_FONTS)
  meta_line_2 = args.meta_line_2 or format_meta_second(style.get("metaSecondTemplate", ""), args.day_label)
  small_bold = fit_font(draw, meta_line_2, int(style.get("metaBoldSize", 58)), 30, meta_max_width, stroke_width=2, font_candidates=META_FONTS)
  label = load_font(int(style.get("seriesSize", 88)), META_FONTS, strict=True)

  series_label = args.series_label or style.get("seriesLabel", "视频日记")
  x0, y0 = 58, 54
  draw.text((x0 + 4, y0 + 5), series_label, font=label, fill=(0, 0, 0, 135), stroke_width=4, stroke_fill=(0, 0, 0, 135))
  draw.text((x0, y0), series_label, font=label, fill=white, stroke_width=3, stroke_fill=black)
  underline_width = int(style.get("labelUnderlineWidth", 318))
  draw.line((x0, y0 + 116, x0 + underline_width, y0 + 116), fill=(255, 255, 255, 190), width=5)

  meta_line_1 = args.meta_line_1 or args.date.replace("-", ".")
  right = COVER_WIDTH - 56
  rows = [(meta_line_1, 64, small, muted), (meta_line_2, 124, small_bold, white)]
  for text, y, font, fill in rows:
    if not text:
      continue
    width, _ = text_size(draw, text, font, 2)
    draw.text((right - width + 3, y + 4), text, font=font, fill=(0, 0, 0, 135), stroke_width=2, stroke_fill=(0, 0, 0, 135))
    draw.text((right - width, y), text, font=font, fill=fill, stroke_width=2, stroke_fill=black)


def draw_tagline(draw, text, y, style):
  if not text:
    return 0

  tag_font = load_font(int(style.get("taglineSize", 54)), META_FONTS, strict=True)
  while text_size(draw, text, tag_font)[0] > COVER_WIDTH - 120 and getattr(tag_font, "size", 54) > 28:
    tag_font = load_font(tag_font.size - 2, META_FONTS, strict=True)
  tag_width, tag_height = text_size(draw, text, tag_font)
  tag_x = (COVER_WIDTH - (tag_width + 80)) / 2
  fill = color(style.get("accentColor", [255, 216, 0, 245]))
  text_fill = color(style.get("tagTextColor", [20, 20, 20, 255]))
  draw.rounded_rectangle((tag_x, y, tag_x + tag_width + 80, y + tag_height + 38), radius=18, fill=fill)
  draw.text((tag_x + 40, y + 15), text, font=tag_font, fill=text_fill)
  return tag_height + 38


def draw_note(draw, text, y, style):
  if not text:
    return

  note_font = load_font(int(style.get("noteSize", 43)), META_FONTS, strict=True)
  max_width = COVER_WIDTH - 180
  while text_size(draw, text, note_font, 2)[0] > max_width and getattr(note_font, "size", 43) > 24:
    note_font = load_font(note_font.size - 2, META_FONTS, strict=True)
  note_width, _ = text_size(draw, text, note_font, 2)
  note_x = (COVER_WIDTH - note_width) / 2
  draw.text((note_x + 3, y + 4), text, font=note_font, fill=(0, 0, 0, 150), stroke_width=2, stroke_fill=(0, 0, 0, 150))
  draw.text((note_x, y), text, font=note_font, fill=(255, 255, 255, 235), stroke_width=2, stroke_fill=(0, 0, 0, 200))


def render_cover(args):
  global COVER_WIDTH, COVER_HEIGHT
  if args.aspect == "4:3":
    COVER_WIDTH, COVER_HEIGHT = 1440, 1080
  else:
    COVER_WIDTH, COVER_HEIGHT = DEFAULT_COVER_WIDTH, DEFAULT_COVER_HEIGHT

  routes = load_routes()
  route_name = normalize_route(args.route, routes)
  style_version, style = pick_style(routes, route_name, args.style_version)
  style = dict(style)
  if args.aspect == "4:3":
    style["titleY"] = int(style.get("titleY", 500) * 0.66)
    style["noteY"] = min(COVER_HEIGHT - 72, int(style.get("noteY", 1280) * 0.76))
    style["title1StartSize"] = int(style.get("title1StartSize", 190) * 0.82)
    style["title2StartSize"] = int(style.get("title2StartSize", 168) * 0.82)
    style["taglineSize"] = int(style.get("taglineSize", 48) * 0.88)
    style["seriesSize"] = int(style.get("seriesSize", 78) * 0.82)
    style["metaSize"] = int(style.get("metaSize", 44) * 0.82)
    style["metaBoldSize"] = int(style.get("metaBoldSize", 52) * 0.82)

  title_line_1, title_line_2, subtitle, note = resolve_title_content(args, style)

  image = Image.open(args.base_frame).convert("RGB")
  image = crop_to_cover(image)
  image = image.resize((COVER_WIDTH, COVER_HEIGHT), Image.Resampling.LANCZOS)
  image = ImageEnhance.Contrast(image).enhance(args.contrast or float(style.get("contrast", 1.07)))
  image = ImageEnhance.Color(image).enhance(args.color or float(style.get("color", 0.96)))
  canvas = image.convert("RGBA")

  overlay = Image.new("RGBA", (COVER_WIDTH, COVER_HEIGHT), (0, 0, 0, 0))
  overlay_draw = ImageDraw.Draw(overlay)
  for y in range(COVER_HEIGHT):
    top_alpha = max(0, int(118 * (1 - y / 360))) if y < 360 else 0
    bottom_alpha = max(0, int(86 * ((y - 980) / 460))) if y > 980 else 0
    overlay_draw.line((0, y, COVER_WIDTH, y), fill=(0, 0, 0, max(top_alpha, bottom_alpha)))
  panel_alpha = int(style.get("panelAlpha", 48))
  panel_top = 300 if args.aspect == "4:3" else 430
  panel_bottom = 870 if args.aspect == "4:3" else 950
  overlay_draw.rounded_rectangle((36, panel_top, COVER_WIDTH - 36, panel_bottom), radius=18, fill=(0, 0, 0, panel_alpha))
  canvas = Image.alpha_composite(canvas, overlay)
  draw = ImageDraw.Draw(canvas)

  draw_header(draw, args, style)

  title_font_candidates = style.get("titleFonts", DISPLAY_FONTS)
  title_outline_width = int(style.get("titleOutlineWidth", 5))
  title_1_font = fit_font(draw, title_line_1, int(style.get("title1StartSize", 224)), 128, 930, stroke_width=title_outline_width, font_candidates=title_font_candidates)
  title_2_font = fit_font(draw, title_line_2 or "", int(style.get("title2StartSize", 202)), 118, 980, stroke_width=title_outline_width, font_candidates=title_font_candidates)
  main_y = args.title_y if args.title_y is not None else int(style.get("titleY", 500))
  title_1_height = draw_fat_center_text(draw, title_line_1, main_y, title_1_font, style)
  title_2_height = draw_fat_center_text(draw, title_line_2 or "", main_y + title_1_height + 24, title_2_font, style)

  tag_gap = 52 if args.aspect == "4:3" else 90
  tag_y = main_y + title_1_height + title_2_height + tag_gap
  tag_height = draw_tagline(draw, subtitle, tag_y, style)
  note_y = args.note_y if args.note_y is not None else int(style.get("noteY", 1280))
  draw_note(draw, note, note_y, style)

  output_path = Path(args.output)
  if not output_path.is_absolute():
    output_path = Path.cwd() / output_path
  output_path.parent.mkdir(parents=True, exist_ok=True)
  canvas.convert("RGB").save(output_path, quality=args.quality)

  title_1_width, _ = text_size(draw, title_line_1, title_1_font, title_outline_width)
  title_2_width, _ = text_size(draw, title_line_2 or "", title_2_font, title_outline_width)
  qc = {
    "passed": True,
    "output": str(output_path),
    "aspect": args.aspect,
    "dimensions": [COVER_WIDTH, COVER_HEIGHT],
    "route": route_name,
    "styleVersion": style_version,
    "title": [title_line_1, title_line_2],
    "titleWidths": [title_1_width, title_2_width],
    "fontNames": [getattr(title_1_font, "getname", lambda: ("unknown", "unknown"))()[0]],
    "errors": [],
  }
  if title_1_width > COVER_WIDTH - 120 or title_2_width > COVER_WIDTH - 100:
    qc["errors"].append("title_overflow")
  if main_y < 0 or main_y + title_1_height + title_2_height > COVER_HEIGHT:
    qc["errors"].append("title_outside_canvas")
  if subtitle and tag_y + tag_height > COVER_HEIGHT - 24:
    qc["errors"].append("subtitle_outside_canvas")
  if note and note_y > COVER_HEIGHT - 36:
    qc["errors"].append("note_outside_canvas")
  qc["passed"] = not qc["errors"]

  if args.qc_output:
    qc_path = Path(args.qc_output)
    if not qc_path.is_absolute():
      qc_path = Path.cwd() / qc_path
    qc_path.parent.mkdir(parents=True, exist_ok=True)
    qc_path.write_text(json.dumps(qc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
  if not qc["passed"]:
    raise SystemExit("Cover QC failed: " + ", ".join(qc["errors"]))
  print(f"cover={output_path}")
  print(f"route={route_name}")
  print(f"style_version={style_version}")
  print("qc=pass")


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--date", required=True)
  parser.add_argument("--route", default="video-diary")
  parser.add_argument("--style-version")
  parser.add_argument("--day-label", default="")
  parser.add_argument("--base-frame", required=True)
  parser.add_argument("--output", required=True)
  parser.add_argument("--title")
  parser.add_argument("--title-line-1")
  parser.add_argument("--title-line-2", default="")
  parser.add_argument("--book-title")
  parser.add_argument("--subtitle", default="")
  parser.add_argument("--tagline", default="")
  parser.add_argument("--note", default="")
  parser.add_argument("--series-label")
  parser.add_argument("--meta-line-1")
  parser.add_argument("--meta-line-2")
  parser.add_argument("--title-y", type=int)
  parser.add_argument("--note-y", type=int)
  parser.add_argument("--contrast", type=float)
  parser.add_argument("--color", type=float)
  parser.add_argument("--quality", type=int, default=96)
  parser.add_argument("--aspect", choices=["3:4", "4:3"], default="3:4")
  parser.add_argument("--qc-output")
  args = parser.parse_args()
  render_cover(args)


if __name__ == "__main__":
  main()
