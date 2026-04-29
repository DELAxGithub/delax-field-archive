#!/usr/bin/env -S uv run --quiet --with mlx-whisper --with anthropic python
"""動画から字幕生成 (mlx-whisper) + 多言語翻訳 (Claude API)。

ナレーションなし街歩き動画では出力 SRT が空 or 環境音断片のみになる想定。
DBT (Bike Tour) や街の人の発話を拾った場合の保険として実装。

入力: 完成動画 (long_*.mp4)
出力: <out-dir>/subtitles/
  - <stem>.jp.srt  (mlx-whisper 直出力)
  - <stem>.en.srt  (Claude 翻訳)
  - <stem>.es.srt  (Claude 翻訳)

使い方:
  scripts/generate_subtitles.py --source long_video.mp4
  scripts/generate_subtitles.py --source long_video.mp4 --langs jp,en   # ES スキップ
  scripts/generate_subtitles.py --source long_video.mp4 --no-translate  # JP のみ

注: 初回 mlx-whisper 実行時はモデル DL (large-v3, ~2.9GB) が走る。
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
from pathlib import Path


WHISPER_MODEL = "mlx-community/whisper-large-v3-mlx"


def srt_timestamp(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int((s - int(s)) * 1000):03d}"


def segments_to_srt(segments: list[dict]) -> str:
    """mlx-whisper segments → SRT 文字列。

    SRT 仕様上 cue 番号は 1..N で連続している必要があるので、
    空テキスト segment をスキップしても番号がずれないよう独立カウンタを使う。
    """
    out = []
    cue_num = 0
    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue
        cue_num += 1
        start = srt_timestamp(seg["start"])
        end = srt_timestamp(seg["end"])
        out.append(f"{cue_num}\n{start} --> {end}\n{text}\n")
    return "\n".join(out)


def extract_audio(source: Path, dest: Path) -> None:
    """16kHz mono WAV を抽出 (Whisper の標準入力形式)。"""
    subprocess.run([
        "ffmpeg", "-y", "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", "-f", "wav",
        str(dest)
    ], check=True, stderr=subprocess.DEVNULL)


def transcribe_jp(wav: Path) -> list[dict]:
    import mlx_whisper
    result = mlx_whisper.transcribe(
        str(wav),
        path_or_hf_repo=WHISPER_MODEL,
        language="ja",
        word_timestamps=False,
        verbose=False,
    )
    return result.get("segments", [])


def translate_srt(jp_srt: str, target_lang: str) -> str:
    """JP SRT を Claude API で target_lang に翻訳 (タイムスタンプ保持)。"""
    if not jp_srt.strip():
        return ""

    try:
        import anthropic
    except ImportError:
        print(f"[srt] anthropic not installed, skipping {target_lang}", file=sys.stderr)
        return ""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(f"[srt] ANTHROPIC_API_KEY not set, skipping {target_lang}", file=sys.stderr)
        return ""

    lang_label = {"en": "English", "es": "Spanish"}.get(target_lang, target_lang)
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=f"You are a professional subtitle translator. Translate Japanese SRT subtitles to {lang_label}. Preserve all SRT structure: subtitle numbers, timestamp lines (e.g. '00:01:23,456 --> 00:01:25,789'), and blank line separators EXACTLY. Translate only the text lines. Output the translated SRT only, nothing else.",
        messages=[{"role": "user", "content": f"Translate this SRT to {lang_label}:\n\n{jp_srt}"}],
    )
    return resp.content[0].text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="省略時: <source の親>/subtitles/")
    ap.add_argument("--langs", default="jp,en,es")
    ap.add_argument("--no-translate", action="store_true",
                    help="JP のみ生成、翻訳しない")
    args = ap.parse_args()

    if not args.source.exists():
        sys.exit(f"source not found: {args.source}")

    out_dir = args.out_dir or args.source.parent / "subtitles"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.source.stem

    # 音声抽出
    wav = out_dir / f"{stem}.16k.wav"
    print(f"[srt] extracting audio → {wav.name}")
    extract_audio(args.source, wav)

    # JP 文字起こし
    print(f"[srt] transcribing JP (mlx-whisper {WHISPER_MODEL})...")
    segments = transcribe_jp(wav)
    jp_srt = segments_to_srt(segments)

    if not jp_srt.strip():
        print("[srt] (empty transcription — likely no speech in source)")
        # 空ファイルも一応書いて pipeline 完走
        jp_srt = ""

    jp_path = out_dir / f"{stem}.jp.srt"
    jp_path.write_text(jp_srt)
    print(f"[srt] JP → {jp_path.name} ({len(segments)} segments)")

    # 翻訳
    if not args.no_translate and jp_srt.strip():
        langs = [l.strip() for l in args.langs.split(",") if l.strip() != "jp"]
        for lang in langs:
            print(f"[srt] translating to {lang}...")
            translated = translate_srt(jp_srt, lang)
            if translated:
                p = out_dir / f"{stem}.{lang}.srt"
                p.write_text(translated)
                print(f"[srt] {lang} → {p.name}")

    # クリーンアップ
    wav.unlink(missing_ok=True)
    print(f"[done] {out_dir}")


if __name__ == "__main__":
    main()
