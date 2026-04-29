#!/usr/bin/env -S uv run --quiet --with pillow python
"""動画から サムネ候補を抽出 + シリーズバッジ合成 + Read 用 preview JPG 同時生成。

入力: 完成動画 (long_*.mp4) と count
出力: <out-dir>/thumbs/
  - candidate_<NN>.jpg          (フル 4K、最終公開用)
  - candidate_<NN>_badge.jpg    (バッジ合成版、複数候補比較用)
  - _preview/candidate_<NN>.preview.jpg  (1600px、Read tool 用)

抽出ロジック:
  - 動画尺を count+1 等分し、各内分点でフレーム抽出
  - 先頭 5% と末尾 5% は除外 (場所カードや暗転を避ける)
  - フェーズ後の改良点として、librosa BGM cue 点抽出も将来対応

使い方:
  scripts/extract_thumb_candidates.py --source long_video.mp4 --count 12
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CANVAS_W, CANVAS_H = 3840, 2160
FONT_BADGE = "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc"

BADGE_TEXT = "デラさんぽ 4K"
BADGE_BG = (255, 200, 0, 235)
BADGE_TEXT_COLOR = (60, 40, 10, 255)
BADGE_FONT_SIZE = 64
BADGE_PADDING_X = 40
BADGE_PADDING_Y = 20
BADGE_MARGIN_LEFT = 96
BADGE_MARGIN_BOTTOM = 96


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path)
    ])
    return float(out.decode().strip())


def extract_frame(source: Path, t_sec: float, dest: Path) -> None:
    subprocess.run([
        "ffmpeg", "-y", "-ss", f"{t_sec:.3f}", "-i", str(source),
        "-vframes", "1", "-q:v", "2", str(dest)
    ], check=True, stderr=subprocess.DEVNULL)


def composite_badge(src: Path, dest: Path) -> None:
    img = Image.open(src).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = ImageFont.truetype(FONT_BADGE, BADGE_FONT_SIZE)
    text_w = draw.textlength(BADGE_TEXT, font=font)
    badge_w = int(text_w + BADGE_PADDING_X * 2)
    badge_h = BADGE_FONT_SIZE + BADGE_PADDING_Y * 2

    x0 = BADGE_MARGIN_LEFT
    y0 = img.height - BADGE_MARGIN_BOTTOM - badge_h
    x1, y1 = x0 + badge_w, y0 + badge_h
    radius = int(badge_h * 0.5)

    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=BADGE_BG)
    draw.text((x0 + BADGE_PADDING_X, y0 + BADGE_PADDING_Y - 8),
              BADGE_TEXT, fill=BADGE_TEXT_COLOR, font=font)

    out = Image.alpha_composite(img, overlay).convert("RGB")
    out.save(dest, quality=92)


def make_preview(src: Path, dest: Path) -> None:
    """sips で長辺 1600px に縮小 (Read 用)。"""
    subprocess.run([
        "sips", "-Z", "1600", "-s", "format", "jpeg",
        str(src), "--out", str(dest)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, type=Path)
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="省略時: <source の親>/thumbs/")
    args = ap.parse_args()

    if not args.source.exists():
        sys.exit(f"source not found: {args.source}")

    out_dir = args.out_dir or args.source.parent / "thumbs"
    preview_dir = out_dir / "_preview"
    out_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    duration = ffprobe_duration(args.source)
    margin = duration * 0.05
    span = duration - margin * 2
    print(f"[thumbs] duration {duration:.1f}s, extracting {args.count} candidates "
          f"(margin {margin:.1f}s)")

    for i in range(args.count):
        t = margin + span * (i + 1) / (args.count + 1)
        n = f"{i+1:02d}"
        raw = out_dir / f"candidate_{n}.jpg"
        badged = out_dir / f"candidate_{n}_badge.jpg"
        prev = preview_dir / f"candidate_{n}.preview.jpg"

        extract_frame(args.source, t, raw)
        composite_badge(raw, badged)
        make_preview(badged, prev)
        print(f"  [{n}] t={t:.1f}s → {raw.name} / {badged.name}")

    print(f"\n[done] {args.count} candidates in {out_dir}")
    print(f"[done] previews in {preview_dir} (Read tool 用)")


if __name__ == "__main__":
    main()
