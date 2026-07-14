from pathlib import Path
import argparse
import csv
import re


DEFAULT_MAX_TERMS = 30
DEFAULT_MAX_SCRIPT_CHARS = 220
PROJECT_DICTIONARY = Path("11_templates/关键词收集/字幕纠错词库.tsv")
PUBLIC_DICTIONARY = Path("00_system/defaults/transcript-corrections.tsv")


def read_terms(path):
  if not path.exists():
    return []
  terms = []
  with path.open("r", encoding="utf-8-sig", newline="") as file:
    reader = csv.reader(file, delimiter="\t")
    for row in reader:
      if not row or len(row) < 2 or row[0].strip().startswith("#"):
        continue
      target = row[1].strip()
      if target and target not in terms:
        terms.append(target)
  return terms


def compact_script(path, max_chars):
  if not path.exists():
    return ""
  text = path.read_text(encoding="utf-8-sig")
  text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
  text = re.sub(r"[#>*`_\-]+", " ", text)
  text = re.sub(r"\s+", " ", text).strip()
  return text[:max_chars]


def unique_terms(values):
  seen = set()
  output = []
  for value in values:
    if value in seen:
      continue
    seen.add(value)
    output.append(value)
  return output


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--date", required=True)
  parser.add_argument("--output", required=True)
  parser.add_argument("--max-terms", type=int, default=DEFAULT_MAX_TERMS)
  parser.add_argument("--max-script-chars", type=int, default=DEFAULT_MAX_SCRIPT_CHARS)
  args = parser.parse_args()

  root = Path.cwd()
  script_path = root / "02_scripts" / f"{args.date}.md"
  output_path = Path(args.output)
  if not output_path.is_absolute():
    output_path = root / output_path

  script = compact_script(script_path, args.max_script_chars)
  all_terms = unique_terms([
    *read_terms(root / PROJECT_DICTIONARY),
    *read_terms(root / PUBLIC_DICTIONARY),
  ])
  relevant_terms = [term for term in all_terms if term in script]
  fallback_terms = [term for term in all_terms if term not in relevant_terms]
  terms = (relevant_terms + fallback_terms)[:args.max_terms]
  parts = []
  if terms:
    parts.append("专有名词：" + "、".join(terms))
  if script:
    parts.append("当天口播语境：" + script)
  prompt = "。".join(parts)

  output_path.parent.mkdir(parents=True, exist_ok=True)
  output_path.write_text(prompt + "\n", encoding="utf-8")
  print(f"prompt={output_path}")
  print(f"terms={len(terms)}")
  print(f"chars={len(prompt)}")


if __name__ == "__main__":
  main()
