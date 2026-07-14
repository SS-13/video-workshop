from pathlib import Path
import argparse
import json


def segment_reason(segment, args):
  reasons = []
  avg_logprob = float(segment.get("avg_logprob", 0.0))
  no_speech_prob = float(segment.get("no_speech_prob", 0.0))
  compression_ratio = float(segment.get("compression_ratio", 0.0))
  word_probabilities = [
    float(word.get("probability"))
    for word in segment.get("words", [])
    if word.get("probability") is not None
  ]

  if avg_logprob < args.min_logprob:
    reasons.append(f"low_logprob:{avg_logprob:.3f}")
  if no_speech_prob > args.max_no_speech:
    reasons.append(f"high_no_speech:{no_speech_prob:.3f}")
  if compression_ratio > args.max_compression_ratio:
    reasons.append(f"high_compression:{compression_ratio:.3f}")
  if not segment.get("words"):
    reasons.append("missing_word_timestamps")
  if word_probabilities:
    low_word_ratio = sum(1 for value in word_probabilities if value < args.min_word_probability) / len(word_probabilities)
    if min(word_probabilities) < args.min_word_probability:
      reasons.append(f"low_word_probability:{min(word_probabilities):.3f}")
    if low_word_ratio > args.max_low_word_ratio:
      reasons.append(f"many_low_probability_words:{low_word_ratio:.3f}")
  return reasons


def timestamp(seconds):
  seconds = max(0.0, float(seconds))
  minutes = int(seconds // 60)
  remainder = seconds - minutes * 60
  return f"{minutes:02}:{remainder:05.2f}"


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--input-json", required=True)
  parser.add_argument("--output-json", required=True)
  parser.add_argument("--output-md", required=True)
  parser.add_argument("--min-logprob", type=float, default=-0.72)
  parser.add_argument("--max-no-speech", type=float, default=0.45)
  parser.add_argument("--max-compression-ratio", type=float, default=2.35)
  parser.add_argument("--min-word-probability", type=float, default=0.32)
  parser.add_argument("--max-low-word-ratio", type=float, default=0.18)
  args = parser.parse_args()

  input_path = Path(args.input_json)
  output_json = Path(args.output_json)
  output_md = Path(args.output_md)
  data = json.loads(input_path.read_text(encoding="utf-8"))
  uncertain = []

  for segment in data.get("segments", []):
    reasons = segment_reason(segment, args)
    if not reasons:
      continue
    uncertain.append({
      "id": segment.get("id"),
      "start": round(float(segment.get("start", 0.0)), 3),
      "end": round(float(segment.get("end", 0.0)), 3),
      "text": str(segment.get("text", "")).strip(),
      "avgLogprob": segment.get("avg_logprob"),
      "noSpeechProb": segment.get("no_speech_prob"),
      "compressionRatio": segment.get("compression_ratio"),
      "reasons": reasons,
    })

  report = {
    "input": str(input_path),
    "segmentCount": len(data.get("segments", [])),
    "uncertainCount": len(uncertain),
    "thresholds": {
      "minLogprob": args.min_logprob,
      "maxNoSpeech": args.max_no_speech,
      "maxCompressionRatio": args.max_compression_ratio,
    },
    "uncertainSegments": uncertain,
  }

  output_json.parent.mkdir(parents=True, exist_ok=True)
  output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

  rows = [
    "# 字幕低置信度片段",
    "",
    f"- 总片段：{report['segmentCount']}",
    f"- 待复核：{report['uncertainCount']}",
    "",
  ]
  if not uncertain:
    rows.append("没有检测到需要额外复核的片段。")
  else:
    rows.extend(["| 时间 | 原始识别 | 原因 |", "| --- | --- | --- |"])
    for item in uncertain:
      rows.append(
        f"| {timestamp(item['start'])}-{timestamp(item['end'])} | "
        f"{item['text'].replace('|', '｜')} | {', '.join(item['reasons'])} |"
      )
  output_md.write_text("\n".join(rows).rstrip() + "\n", encoding="utf-8")

  print(f"input={input_path}")
  print(f"output_json={output_json}")
  print(f"output_md={output_md}")
  print(f"segments={report['segmentCount']}")
  print(f"uncertain={report['uncertainCount']}")


if __name__ == "__main__":
  main()
