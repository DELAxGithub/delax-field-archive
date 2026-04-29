#!/usr/bin/env -S uv run --quiet --with pillow python
"""9:16 ショート動画レンダラ (MVP / レイアウト A + 末尾 CTA overlay 対応版)。

入力: 動画ソース + 場所テロップ (CLI 引数)
出力: 1080x1920 / 30fps mp4 — デフォルトは $DELAX_REPORTS_ROOT/delax-field-archive/

設計: docs/short-render-spec.md
流用元: ~/src/90_サイドワーク/たっちレディオショート/pipeline/scripts/lipsync_3char.py
       (draw_text_with_halo / safe zone 値)

使い方:
    python3 scripts/render_short.py \\
        --source /Volumes/Sony_Vlog/2026-04-25/C0122.MP4 \\
        --episode-id DWT_EP002 \\
        --start 5 --duration 30 \\
        --location-primary "マラガ" \\
        --location-secondary "Málaga, España · 2026.04.25" \\
        --cta-text "Full Tour ↗"
    # → ~/Dropbox/delax-reports/delax-field-archive/DWT_EP002/short_C0122.mp4
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 出力先ポリシー: 重量級生成物は ~/Dropbox/delax-reports/<project>/<id>/ (DELAX 共通規約)。
# $DELAX_REPORTS_ROOT で上書き可。未設定時は ~/Dropbox/delax-reports/。
DEFAULT_OUTPUT_BASE = Path(
    os.environ.get("DELAX_REPORTS_ROOT", str(Path.home() / "Dropbox" / "delax-reports"))
) / "delax-field-archive"


def default_output_path(source: Path, episode_id: str | None) -> Path:
    sub = episode_id if episode_id else "_unsorted"
    return DEFAULT_OUTPUT_BASE / sub / f"short_{source.stem}.mp4"


CANVAS_W, CANVAS_H = 1080, 1920
FPS = 30

# Multi-platform safe zone (YouTube Shorts / IG Reels / TikTok)
SAFE_TOP_Y = 210
SAFE_BOTTOM_Y = 1550
SAFE_LEFT_X = 60
SAFE_RIGHT_X = 916

# Header band (装飾 / 上部 0..210 OK)
HEADER_H = 130
HEADER_BG = (20, 20, 20, 255)
HEADER_TEXT_COLOR = (245, 245, 240, 255)
HEADER_FONT_SIZE = 50

# Episode chip
EP_CHIP_BG = (200, 200, 200, 255)
EP_CHIP_TEXT = (20, 20, 20, 255)
EP_CHIP_FONT_SIZE = 36
EP_CHIP_PADDING_X = 22
EP_CHIP_MARGIN_R = 60

# Location card (NHK ふれあい街歩き 文法、safe zone 内)
LOCATION_Y = 1320
LOCATION_PRIMARY_FONT = 84
LOCATION_SECONDARY_FONT = 34
LOCATION_PRIMARY_COLOR = (250, 250, 245, 255)
LOCATION_SECONDARY_COLOR = (210, 210, 205, 255)
LOCATION_HALO = (0, 0, 0, 255)
LOCATION_BG = (0, 0, 0, 140)
LOCATION_BG_PADDING_X = 32
LOCATION_BG_PADDING_Y = 22
LOCATION_GAP = 14

FONT_BOLD = "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc"
FONT_LIGHT = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"

# CTA overlay (末尾 N秒に表示する本編誘導)
CTA_FONT_SIZE = 92
CTA_TEXT_COLOR = (255, 200, 0, 255)   # バッジと同じ単色黄色
CTA_HALO = (40, 30, 0, 255)
CTA_BG = (0, 0, 0, 220)
CTA_PADDING_X = 56
CTA_PADDING_Y = 36
CTA_Y = 760   # 中央やや上、location card と被らない位置 (location_y=1320)
CTA_RADIUS = 24
CTA_HALO_OFFSET = 4
CTA_DEFAULT_DURATION_S = 5.0


def draw_text_with_halo(draw: ImageDraw.ImageDraw, xy, text: str,
                        font: ImageFont.FreeTypeFont, fill, halo, halo_offset: int = 2) -> None:
    """流用元: tachi-shorts/lipsync_3char.py:293."""
    x, y = xy
    for dx, dy in ((-halo_offset, 0), (halo_offset, 0), (0, -halo_offset), (0, halo_offset)):
        draw.text((x + dx, y + dy), text, fill=halo, font=font)
    draw.text((x, y), text, fill=fill, font=font)


def build_overlay(series_label: str, ep_chip: str,
                  loc_primary: str, loc_secondary: str) -> Image.Image:
    """1080x1920 RGBA overlay PNG を組み立てる。"""
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # ── Header band
    draw.rectangle([0, 0, CANVAS_W, HEADER_H], fill=HEADER_BG)
    header_font = ImageFont.truetype(FONT_BOLD, HEADER_FONT_SIZE)
    label_y = (HEADER_H - HEADER_FONT_SIZE) // 2 - 4
    draw.text((SAFE_LEFT_X, label_y), series_label, fill=HEADER_TEXT_COLOR, font=header_font)

    # ── Episode chip (top-right inside header)
    chip_font = ImageFont.truetype(FONT_BOLD, EP_CHIP_FONT_SIZE)
    chip_text_w = draw.textlength(ep_chip, font=chip_font)
    chip_w = int(chip_text_w + EP_CHIP_PADDING_X * 2)
    chip_h = EP_CHIP_FONT_SIZE + 18
    chip_x1 = CANVAS_W - EP_CHIP_MARGIN_R
    chip_x0 = chip_x1 - chip_w
    chip_y0 = (HEADER_H - chip_h) // 2
    chip_y1 = chip_y0 + chip_h
    draw.rounded_rectangle([chip_x0, chip_y0, chip_x1, chip_y1],
                           radius=chip_h // 2, fill=EP_CHIP_BG)
    draw.text((chip_x0 + EP_CHIP_PADDING_X,
               chip_y0 + (chip_h - EP_CHIP_FONT_SIZE) // 2 - 3),
              ep_chip, fill=EP_CHIP_TEXT, font=chip_font)

    # ── Location card
    primary_font = ImageFont.truetype(FONT_BOLD, LOCATION_PRIMARY_FONT)
    secondary_font = ImageFont.truetype(FONT_LIGHT, LOCATION_SECONDARY_FONT)
    primary_w = draw.textlength(loc_primary, font=primary_font)
    secondary_w = draw.textlength(loc_secondary, font=secondary_font)
    block_h = LOCATION_PRIMARY_FONT + LOCATION_GAP + LOCATION_SECONDARY_FONT

    primary_x = (CANVAS_W - primary_w) / 2
    secondary_x = (CANVAS_W - secondary_w) / 2
    primary_y = LOCATION_Y
    secondary_y = primary_y + LOCATION_PRIMARY_FONT + LOCATION_GAP

    bg_w = max(primary_w, secondary_w) + LOCATION_BG_PADDING_X * 2
    bg_h = block_h + LOCATION_BG_PADDING_Y * 2
    bg_x0 = (CANVAS_W - bg_w) / 2
    bg_y0 = primary_y - LOCATION_BG_PADDING_Y
    bg_x1 = bg_x0 + bg_w
    bg_y1 = bg_y0 + bg_h

    bg_layer = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    ImageDraw.Draw(bg_layer).rounded_rectangle(
        [bg_x0, bg_y0, bg_x1, bg_y1], radius=14, fill=LOCATION_BG)
    overlay.alpha_composite(bg_layer)

    draw_text_with_halo(draw, (primary_x, primary_y), loc_primary,
                        primary_font, LOCATION_PRIMARY_COLOR, LOCATION_HALO)
    draw_text_with_halo(draw, (secondary_x, secondary_y), loc_secondary,
                        secondary_font, LOCATION_SECONDARY_COLOR, LOCATION_HALO)

    return overlay


def build_cta_overlay(cta_text: str) -> Image.Image:
    """末尾 N秒に表示する CTA overlay (黄色テキスト・黒帯背景・中央)。"""
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.truetype(FONT_BOLD, CTA_FONT_SIZE)
    text_w = draw.textlength(cta_text, font=font)
    bg_w = int(text_w + CTA_PADDING_X * 2)
    bg_h = CTA_FONT_SIZE + CTA_PADDING_Y * 2
    bg_x0 = (CANVAS_W - bg_w) / 2
    bg_y0 = CTA_Y
    bg_x1 = bg_x0 + bg_w
    bg_y1 = bg_y0 + bg_h
    bg_layer = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    ImageDraw.Draw(bg_layer).rounded_rectangle(
        [bg_x0, bg_y0, bg_x1, bg_y1], radius=CTA_RADIUS, fill=CTA_BG)
    overlay.alpha_composite(bg_layer)
    text_x = (CANVAS_W - text_w) / 2
    text_y = CTA_Y + CTA_PADDING_Y - 8
    draw_text_with_halo(draw, (text_x, text_y), cta_text,
                        font, CTA_TEXT_COLOR, CTA_HALO, halo_offset=CTA_HALO_OFFSET)
    return overlay


def render(source: Path, output: Path, start_s: float, duration_s: float,
           overlay_png: Path, cta_png: Path | None, cta_duration_s: float) -> None:
    inputs = [
        "-ss", str(start_s),
        "-i", str(source),
        "-loop", "1", "-framerate", str(FPS), "-i", str(overlay_png),
    ]
    if cta_png:
        inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(cta_png)]
        cta_start = max(0.0, duration_s - cta_duration_s)
        # PNG オーバーレイは fade フィルタで時間制御するため、video stream 化する
        filter_complex = (
            f"[0:v]crop=ih*9/16:ih,scale={CANVAS_W}:{CANVAS_H},fps={FPS}[v];"
            f"[v][1:v]overlay=0:0[v1];"
            f"[2:v]format=rgba,fade=t=in:st={cta_start}:d=0.5:alpha=1[cta];"
            f"[v1][cta]overlay=0:0:enable='gte(t,{cta_start})'[outv]"
        )
    else:
        filter_complex = (
            f"[0:v]crop=ih*9/16:ih,scale={CANVAS_W}:{CANVAS_H},fps={FPS}[v];"
            f"[v][1:v]overlay=0:0[outv]"
        )

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        *inputs,
        "-t", str(duration_s),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        str(output),
    ]
    print(f"[ffmpeg] {source.name} → {output} (start={start_s}s, dur={duration_s}s"
          f"{', cta=on' if cta_png else ''})")
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", "-s", required=True, type=Path)
    ap.add_argument("--output", "-o", type=Path, default=None,
                    help=f"省略時: {DEFAULT_OUTPUT_BASE}/<episode-id|_unsorted>/short_<source-stem>.mp4")
    ap.add_argument("--episode-id", default=None,
                    help="エピソード ID (例: DWT_EP002)。未指定時は _unsorted/")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--duration", "-d", type=float, default=30.0)
    ap.add_argument("--location-primary", required=True)
    ap.add_argument("--location-secondary", required=True)
    ap.add_argument("--series-label", default="DELAX Walking Tour")
    ap.add_argument("--ep-chip", default="TEST")
    ap.add_argument("--cta-text", default=None,
                    help="末尾に表示する本編誘導テキスト (例: 'Full Tour ↗')")
    ap.add_argument("--cta-duration-s", type=float, default=CTA_DEFAULT_DURATION_S,
                    help="CTA を表示する秒数 (動画末尾から)")
    ap.add_argument("--keep-overlay", action="store_true")
    args = ap.parse_args()

    if not args.source.exists():
        sys.exit(f"source not found: {args.source}")

    output = args.output or default_output_path(args.source, args.episode_id)
    output.parent.mkdir(parents=True, exist_ok=True)

    overlay = build_overlay(args.series_label, args.ep_chip,
                            args.location_primary, args.location_secondary)
    overlay_path = output.parent / f"_overlay_{output.stem}.png"
    overlay.save(overlay_path)
    print(f"[overlay] {overlay_path}")

    cta_path = None
    if args.cta_text:
        cta_overlay = build_cta_overlay(args.cta_text)
        cta_path = output.parent / f"_cta_{output.stem}.png"
        cta_overlay.save(cta_path)
        print(f"[cta] {cta_path} (last {args.cta_duration_s}s)")

    render(args.source, output, args.start, args.duration,
           overlay_path, cta_path, args.cta_duration_s)

    if not args.keep_overlay:
        overlay_path.unlink(missing_ok=True)
        if cta_path:
            cta_path.unlink(missing_ok=True)
    print(f"✓ {output}")


if __name__ == "__main__":
    main()
