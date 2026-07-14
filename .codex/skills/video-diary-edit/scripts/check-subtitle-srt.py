from pathlib import Path
import argparse
import json
import re


DEFAULT_BAD_TERMS = [
  "逗报",
  "书法",
  "生辰",
  "光飙",
  "简贴",
  "卡段",
  "物操作",
  "多底",
  "卖一点",
  "常文本",
  "常与营",
  "副盘",
  "Bringstone",
  "多了人",
  "出书",
]


def read_blocks(path):
  text = path.read_text(encoding="utf-8-sig")
  return [block for block in re.split(r"\n\s*\n", text.strip()) if block.strip()]


def block_text(block):
  lines = [line.strip() for line in block.splitlines() if line.strip()]
  if len(lines) <= 2:
    return ""
  return "".join(lines[2:])


def block_caption_lines(block):
  lines = [line.strip() for line in block.splitlines() if line.strip()]
  return lines[2:] if len(lines) > 2 else []


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


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("srt")
  parser.add_argument("--max-chars", type=int, default=24)
  parser.add_argument("--max-line-units", type=float, default=18.0)
  parser.add_argument("--max-lines", type=int, default=2)
  parser.add_argument("--bad-term", action="append", default=[])
  parser.add_argument("--report")
  args = parser.parse_args()

  path = Path(args.srt)
  blocks = read_blocks(path)
  long_blocks = []
  bad_hits = []
  line_errors = []
  bad_terms = DEFAULT_BAD_TERMS + args.bad_term

  for block in blocks:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    index = lines[0] if lines else "?"
    text = block_text(block)
    caption_lines = block_caption_lines(block)
    if len(text) > args.max_chars:
      long_blocks.append((index, len(text), text))
    if len(caption_lines) > args.max_lines:
      line_errors.append((index, "too_many_lines", len(caption_lines), text))
    if len(caption_lines) > 1:
      for line_number, line in enumerate(caption_lines, 1):
        units = visual_units(line)
        if units > args.max_line_units:
          line_errors.append((index, f"line_{line_number}_too_wide", round(units, 2), line))
    for term in bad_terms:
      if term and term in text:
        bad_hits.append((index, term, text))

  print(f"srt={path}")
  print(f"blocks={len(blocks)}")
  print(f"long_blocks={len(long_blocks)}")
  print(f"bad_hits={len(bad_hits)}")
  print(f"line_errors={len(line_errors)}")

  for index, length, text in long_blocks[:20]:
    print(f"LONG\t{index}\t{length}\t{text}")
  for index, term, text in bad_hits[:20]:
    print(f"BAD\t{index}\t{term}\t{text}")
  for index, kind, value, text in line_errors[:20]:
    print(f"LINE\t{index}\t{kind}\t{value}\t{text}")

  if args.report:
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
      json.dumps(
        {
          "srt": str(path),
          "blocks": len(blocks),
          "longBlocks": len(long_blocks),
          "badHits": len(bad_hits),
          "lineErrors": len(line_errors),
          "passed": not (long_blocks or bad_hits or line_errors),
        },
        ensure_ascii=False,
        indent=2,
      ) + "\n",
      encoding="utf-8",
    )

  if long_blocks or bad_hits or line_errors:
    raise SystemExit(1)


if __name__ == "__main__":
  main()
