#!/usr/bin/env -S uv run --quiet --with librosa --with soundfile --with numpy python
"""BGM ライブラリ解析 → カタログ生成 (long-form-pipeline 用)。

入力: <bgm-library>/_inbox/*.mp3 (Storyblocks DL 直後の状態)
処理: librosa + ffprobe で音響特徴抽出 → ジャンル別フォルダに振り分け
出力:
  - <bgm-library>/<genre>/*.mp3 (移動先)
  - <bgm-library>/_catalog.json
  - <bgm-library>/_catalog.csv

ジャンル推測はファイル名キーワードベース (Storyblocks 命名規則を活用):
  lofi, ambient, cinematic, lounge, other

使い方:
    ./scripts/analyze_bgm.py
    ./scripts/analyze_bgm.py --library ~/src/_workdir/long-form-pipeline/bgm-library
    ./scripts/analyze_bgm.py --no-move    # 解析だけしてファイル移動しない
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import librosa
import numpy as np


GENRE_KEYWORDS = {
    "lofi": ["lofi", "lo-fi", "chill"],
    "ambient": ["ambient", "meditation", "meditative", "atmospheric", "dreamy"],
    "cinematic": ["cinstyle", "cinematic", "soundtrack", "score"],
    "lounge": ["lounge", "city", "cafe", "jazz", "bossa"],
}

SBA_PATTERN = re.compile(r"SBA-(\d+)")


def guess_genre(filename: str) -> str:
    name = filename.lower()
    for genre, keywords in GENRE_KEYWORDS.items():
        if any(kw in name for kw in keywords):
            return genre
    return "other"


def extract_sba_id(filename: str) -> str | None:
    m = SBA_PATTERN.search(filename)
    return m.group(1) if m else None


def ffprobe_duration(path: Path) -> float:
    """ffprobe で正確な duration を取得 (librosa より速い)。"""
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True,
    )
    return float(out.strip())


def analyze_track(path: Path) -> dict:
    """librosa で BPM / RMS / spectral_centroid / intro_silence_ms を抽出。"""
    y, sr = librosa.load(str(path), sr=22050, mono=True)

    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    # librosa >= 0.10 returns ndarray; coerce to scalar
    tempo_val = float(np.asarray(tempo).flatten()[0])
    rms = librosa.feature.rms(y=y)[0]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]

    # intro_silence: 先頭から RMS が静音閾値を初めて超えるまでの時間
    threshold = float(np.median(rms)) * 0.15
    hop_sec = 512 / sr
    onset_idx = int(np.argmax(rms > threshold))
    intro_silence_ms = int(onset_idx * hop_sec * 1000)

    # outro_fadeout: 末尾2秒の RMS が中央値の半分以下なら True
    tail_samples = int(2.0 / hop_sec)
    outro_fadeout = bool(rms[-tail_samples:].mean() < float(np.median(rms)) * 0.5)

    return {
        "bpm": round(tempo_val, 1),
        "rms_mean": round(float(rms.mean()), 4),
        "spectral_centroid_hz": int(centroid.mean()),
        "intro_silence_ms": intro_silence_ms,
        "outro_fadeout": outro_fadeout,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--library",
        type=Path,
        default=Path.home() / "src/_workdir/long-form-pipeline/bgm-library",
    )
    ap.add_argument("--inbox", type=str, default="_inbox",
                    help="library 配下の inbox サブディレクトリ名")
    ap.add_argument("--no-move", action="store_true",
                    help="解析のみ、ファイル移動しない")
    args = ap.parse_args()

    library: Path = args.library
    inbox = library / args.inbox

    if not inbox.exists():
        sys.exit(f"inbox not found: {inbox}")

    tracks = sorted(inbox.glob("*.mp3"))
    if not tracks:
        sys.exit(f"no mp3 in {inbox}")

    print(f"[analyze] {len(tracks)} tracks in {inbox}")

    catalog = []
    for i, src in enumerate(tracks, 1):
        print(f"  [{i}/{len(tracks)}] {src.name}")
        genre = guess_genre(src.name)
        sba_id = extract_sba_id(src.name)
        duration = ffprobe_duration(src)
        features = analyze_track(src)

        # 移動先決定
        if args.no_move:
            dest_path = src
        else:
            dest_dir = library / genre
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / src.name
            shutil.move(str(src), str(dest_path))

        catalog.append({
            "filename": src.name,
            "path": str(dest_path.relative_to(library)),
            "storyblocks_id": sba_id,
            "genre": genre,
            "duration_sec": round(duration, 1),
            "mood_tag": "",  # 手動記入用
            **features,
        })

    # JSON 出力
    json_path = library / "_catalog.json"
    json_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False))

    # CSV 出力 (Excel で開ける形)
    csv_path = library / "_catalog.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=catalog[0].keys())
        writer.writeheader()
        writer.writerows(catalog)

    # サマリ
    by_genre: dict[str, int] = {}
    for c in catalog:
        by_genre[c["genre"]] = by_genre.get(c["genre"], 0) + 1
    print()
    print(f"[done] catalog: {json_path}")
    print(f"[done] catalog: {csv_path}")
    print(f"[summary] {len(catalog)} tracks, by genre: {by_genre}")
    if not args.no_move:
        print(f"[summary] inbox cleaned: {inbox}")


if __name__ == "__main__":
    main()
