#!/usr/bin/env -S uv run --quiet --with pillow python
"""長尺街歩きレンダラ MVP v0.3 (Step 1+2+3 = 書き出し + overlay + BGM カタログ駆動ミックス)。

入力: 動画 + 場所テロップ + 撮影日 + シリーズID
出力: 4K SDR / HLG HEVC / HLG ProRes 422 HQ
       デフォルトは $DELAX_REPORTS_ROOT/delax-field-archive/<episode-id>/

設計: docs/long-form-spec-v0.md
流用元: scripts/render_short.py (draw_text_with_halo, safe zone)

v0.2 改修 (2026-04-27 マルセイユ 1st レンダ後フィードバック):
- 場所カード alpha 140 → 200 (明るい背景でも字が浮かない)
- 場所カード PRIMARY 192 → 240px / halo offset 6
- フォント統一 → 丸ゴ W4 (バッジと共通)
- バッジ文字色 (40,30,0) → (60,40,10) ダークブラウン
- オープニング演出: 絶景先 → 1〜2秒目に透かしフェードイン
  - 0:00-0:01: 絵だけ
  - 0:01-0:02: バッジ fade in
  - 0:01.5-0:02.5: 場所カード fade in
  - 0:02.5-0:09.0: hold
  - 0:09.0-0:09.8: 場所カード fade out
  - 0:09.8-: バッジのみ常時

使い方:
    python3 scripts/render_long.py \\
        --source ~/src/_workdir/long-form-pipeline/source/マルセイユ.mp4 \\
        --episode-id TEST_marseille_2026-04-02 \\
        --location-primary "マルセイユ" \\
        --location-secondary "Marseille, France · 2026.04.02" \\
        --shoot-date 2026-04-02 \\
        --chapter-count 8 \\
        --output-format sdr-h264
"""
from __future__ import annotations
import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ============================================================
# Output paths
# ============================================================
DEFAULT_OUTPUT_BASE = Path(
    os.environ.get("DELAX_REPORTS_ROOT", str(Path.home() / "Dropbox" / "delax-reports"))
) / "delax-field-archive"


def default_output_path(source: Path, episode_id: str, fmt: str) -> Path:
    ext = {"sdr-h264": "mp4", "hlg-hevc": "mp4", "hlg-prores422hq": "mov"}[fmt]
    return DEFAULT_OUTPUT_BASE / episode_id / f"long_{source.stem}.{ext}"


# ============================================================
# Canvas (4K UHD)
# ============================================================
CANVAS_W, CANVAS_H = 3840, 2160
FPS = 30

# ============================================================
# Fonts (v0.2: 丸ゴ統一 — バッジと場所カードでブランド一貫)
# ============================================================
FONT_ROUND_W4 = "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc"
FONT_PRIMARY = FONT_ROUND_W4    # 場所カード PRIMARY (大)
FONT_SECONDARY = FONT_ROUND_W4  # 場所カード SECONDARY (小)
FONT_BADGE = FONT_ROUND_W4

# ============================================================
# Series badge (左下 / 黄色 / ゆるめ)
# ============================================================
BADGE_TEXT = "デラさんぽ 4K"
BADGE_BG = (255, 200, 0, 235)
BADGE_TEXT_COLOR = (60, 40, 10, 255)   # v0.2: ダークブラウン
BADGE_FONT_SIZE = 64
BADGE_PADDING_X = 40
BADGE_PADDING_Y = 20
BADGE_MARGIN_LEFT = 96
BADGE_MARGIN_BOTTOM = 96
BADGE_RADIUS_RATIO = 0.5

# ============================================================
# Location card (オープニング / 画面下部)
# ============================================================
LOCATION_PRIMARY_FONT = 240        # v0.2: 192 → 240 (1080p で見て存在感ある)
LOCATION_SECONDARY_FONT = 76
LOCATION_PRIMARY_COLOR = (250, 250, 245, 255)
LOCATION_SECONDARY_COLOR = (220, 220, 210, 255)
LOCATION_HALO = (0, 0, 0, 255)
LOCATION_BG = (0, 0, 0, 200)        # v0.2: 140 → 200 (濃く)
LOCATION_BG_PADDING_X = 64
LOCATION_BG_PADDING_Y = 40
LOCATION_GAP = 24
LOCATION_Y = CANVAS_H - 600        # 4K 下から 600px (240px フォント分余裕持たせる)
LOCATION_HALO_OFFSET = 6           # v0.2: 4 → 6 (太字相当)

# ============================================================
# Fade timings (v0.2 オープニング演出)
# ============================================================
BADGE_FADE_IN_START_S = 1.0
BADGE_FADE_IN_DURATION_S = 1.0     # 1.0s → 2.0s で fade in 完了

LOCATION_FADE_IN_START_S = 1.5
LOCATION_FADE_IN_DURATION_S = 1.0   # 1.5s → 2.5s で fade in 完了
LOCATION_HOLD_END_S = 9.0           # 2.5s → 9.0s が hold (6.5秒)
LOCATION_FADE_OUT_DURATION_S = 0.8  # 9.0s → 9.8s で fade out


# ============================================================
# Helpers
# ============================================================

def draw_text_with_halo(draw: ImageDraw.ImageDraw, xy, text: str,
                        font: ImageFont.FreeTypeFont, fill, halo, halo_offset: int = 4) -> None:
    x, y = xy
    for dx, dy in ((-halo_offset, 0), (halo_offset, 0), (0, -halo_offset), (0, halo_offset)):
        draw.text((x + dx, y + dy), text, fill=halo, font=font)
    draw.text((x, y), text, fill=fill, font=font)




# ============================================================
# Overlay builders
# ============================================================

def build_series_badge() -> Image.Image:
    """左下バッジ (4K RGBA)。fade in は ffmpeg 側で時間制御。"""
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font = ImageFont.truetype(FONT_BADGE, BADGE_FONT_SIZE)
    text_w = draw.textlength(BADGE_TEXT, font=font)
    badge_w = int(text_w + BADGE_PADDING_X * 2)
    badge_h = BADGE_FONT_SIZE + BADGE_PADDING_Y * 2

    x0 = BADGE_MARGIN_LEFT
    y0 = CANVAS_H - BADGE_MARGIN_BOTTOM - badge_h
    x1 = x0 + badge_w
    y1 = y0 + badge_h

    radius = int(badge_h * BADGE_RADIUS_RATIO)
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=BADGE_BG)
    draw.text((x0 + BADGE_PADDING_X, y0 + BADGE_PADDING_Y - 8),
              BADGE_TEXT, fill=BADGE_TEXT_COLOR, font=font)

    return overlay


def build_location_card(loc_primary: str, loc_secondary: str) -> Image.Image:
    """場所テロップ overlay (4K RGBA)。"""
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    primary_font = ImageFont.truetype(FONT_PRIMARY, LOCATION_PRIMARY_FONT)
    secondary_font = ImageFont.truetype(FONT_SECONDARY, LOCATION_SECONDARY_FONT)
    primary_w = draw.textlength(loc_primary, font=primary_font)
    secondary_w = draw.textlength(loc_secondary, font=secondary_font)

    primary_x = (CANVAS_W - primary_w) / 2
    secondary_x = (CANVAS_W - secondary_w) / 2
    primary_y = LOCATION_Y
    secondary_y = primary_y + LOCATION_PRIMARY_FONT + LOCATION_GAP

    block_h = LOCATION_PRIMARY_FONT + LOCATION_GAP + LOCATION_SECONDARY_FONT
    bg_w = max(primary_w, secondary_w) + LOCATION_BG_PADDING_X * 2
    bg_h = block_h + LOCATION_BG_PADDING_Y * 2
    bg_x0 = (CANVAS_W - bg_w) / 2
    bg_y0 = primary_y - LOCATION_BG_PADDING_Y
    bg_x1 = bg_x0 + bg_w
    bg_y1 = bg_y0 + bg_h

    bg_layer = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    ImageDraw.Draw(bg_layer).rounded_rectangle(
        [bg_x0, bg_y0, bg_x1, bg_y1], radius=24, fill=LOCATION_BG)
    overlay.alpha_composite(bg_layer)

    draw_text_with_halo(draw, (primary_x, primary_y), loc_primary,
                        primary_font, LOCATION_PRIMARY_COLOR, LOCATION_HALO,
                        halo_offset=LOCATION_HALO_OFFSET)
    draw_text_with_halo(draw, (secondary_x, secondary_y), loc_secondary,
                        secondary_font, LOCATION_SECONDARY_COLOR, LOCATION_HALO,
                        halo_offset=LOCATION_HALO_OFFSET)

    return overlay


# ============================================================
# BGM (catalog-driven, ffmpeg acrossfade chain)
# ============================================================
DEFAULT_BGM_LIBRARY = Path.home() / "src" / "_workdir" / "long-form-pipeline" / "bgm-library"
BGM_CROSSFADE_S = 5.0
BGM_INTRO_SILENCE_MAX_MS = 1500   # これ以上の頭余白は acrossfade で破綻しがち
BGM_LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"   # YouTube 推奨ターゲット


def select_bgm_tracks(library: Path, total_duration_s: float,
                      genres: tuple[str, ...], seed: int | None = None) -> list[dict]:
    """カタログから尺合計が動画尺を超えるまで曲を選ぶ。

    ルール:
      - genre が指定リストに含まれる曲のみ
      - intro_silence_ms < BGM_INTRO_SILENCE_MAX_MS のみ
      - 順序はシャッフル (seed で再現可能)
      - 候補が尺不足なら同じ集合をループ
    """
    catalog_path = library / "_catalog.json"
    if not catalog_path.exists():
        sys.exit(f"BGM catalog not found: {catalog_path} — run scripts/analyze_bgm.py first")

    catalog = json.loads(catalog_path.read_text())
    candidates = [
        c for c in catalog
        if c["genre"] in genres
        and c.get("intro_silence_ms", 0) < BGM_INTRO_SILENCE_MAX_MS
    ]
    if not candidates:
        sys.exit(f"no BGM candidates for genres={genres} (after intro_silence filter)")

    rng = random.Random(seed)
    rng.shuffle(candidates)

    selected: list[dict] = []
    accum = 0.0
    i = 0
    while accum + BGM_CROSSFADE_S < total_duration_s:
        track = candidates[i % len(candidates)]
        selected.append(track)
        # 各曲は次の曲と BGM_CROSSFADE_S だけ重なる → 実効寄与 = duration - crossfade
        accum += track["duration_sec"] - BGM_CROSSFADE_S
        i += 1

    return selected


def build_bgm_filter_chain(tracks: list[dict], video_duration_s: float,
                           input_offset: int) -> tuple[str, str]:
    """BGM の ffmpeg filter_complex 文字列とラベルを返す。

    input_offset: BGM 入力ストリームの先頭インデックス (動画+overlay×2+meta の後)
    戻り値: (filter_str, output_label)
    """
    n = len(tracks)
    if n == 0:
        sys.exit("no bgm tracks selected")

    parts = []
    # まず各 BGM を [aX] にマップ
    for i in range(n):
        parts.append(f"[{input_offset + i}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a{i}]")

    if n == 1:
        chain_out = "a0"
    else:
        prev = "a0"
        for i in range(1, n):
            out = f"m{i}" if i < n - 1 else "amix"
            parts.append(
                f"[{prev}][a{i}]acrossfade=d={BGM_CROSSFADE_S}:c1=tri:c2=tri[{out}]"
            )
            prev = out
        chain_out = "amix"

    # 動画尺で trim + loudnorm
    parts.append(
        f"[{chain_out}]atrim=duration={video_duration_s},asetpts=N/SR/TB,{BGM_LOUDNORM}[aout]"
    )
    return ";".join(parts), "aout"


# ============================================================
# Chapter markers
# ============================================================

def make_chapters_metadata(duration_s: float, count: int, primary_label: str) -> str:
    interval_s = duration_s / count
    lines = [";FFMETADATA1"]
    for i in range(count):
        start_ms = int(i * interval_s * 1000)
        end_ms = int((i + 1) * interval_s * 1000) if i < count - 1 else int(duration_s * 1000)
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={start_ms}")
        lines.append(f"END={end_ms}")
        lines.append(f"title=Ch{i+1:02d} {primary_label}")
    return "\n".join(lines) + "\n"


# ============================================================
# Render
# ============================================================

def render(source: Path, output: Path, fmt: str,
           badge_png: Path, location_png: Path, chapters_meta: Path,
           bgm_tracks: list[dict] | None,
           bgm_library: Path,
           video_duration_s: float) -> None:
    if fmt == "sdr-h264":
        v_codec = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "fast"]
        v_extra = []
    elif fmt == "hlg-hevc":
        v_codec = ["-c:v", "libx265", "-pix_fmt", "yuv420p10le", "-crf", "20", "-preset", "slow",
                   "-tag:v", "hvc1"]
        v_extra = ["-x265-params",
                   "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc:hdr-opt=1:repeat-headers=1"]
    elif fmt == "hlg-prores422hq":
        v_codec = ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"]
        v_extra = ["-color_primaries", "bt2020", "-color_trc", "arib-std-b67", "-colorspace", "bt2020nc"]
    else:
        sys.exit(f"unknown format: {fmt}")

    # PNG オーバーレイは fade フィルタで時間制御するため、video stream 化する
    # (-loop 1 -framerate で PNG を連続フレーム化)
    video_filter = (
        f"[1:v]format=rgba,"
        f"fade=t=in:st={BADGE_FADE_IN_START_S}:d={BADGE_FADE_IN_DURATION_S}:alpha=1[badge_a];"
        f"[2:v]format=rgba,"
        f"fade=t=in:st={LOCATION_FADE_IN_START_S}:d={LOCATION_FADE_IN_DURATION_S}:alpha=1,"
        f"fade=t=out:st={LOCATION_HOLD_END_S}:d={LOCATION_FADE_OUT_DURATION_S}:alpha=1[loc_a];"
        f"[0:v][badge_a]overlay=0:0:shortest=1[v1];"
        f"[v1][loc_a]overlay=0:0:shortest=1[outv]"
    )

    inputs = [
        "-i", str(source),
        "-loop", "1", "-framerate", str(FPS), "-i", str(badge_png),
        "-loop", "1", "-framerate", str(FPS), "-i", str(location_png),
        "-i", str(chapters_meta),
    ]

    if bgm_tracks:
        bgm_input_offset = 4   # 0=source, 1=badge, 2=loc, 3=meta, 4..=BGM
        for t in bgm_tracks:
            inputs += ["-i", str(bgm_library / t["path"])]
        bgm_filter, bgm_label = build_bgm_filter_chain(bgm_tracks, video_duration_s, bgm_input_offset)
        filter_complex = video_filter + ";" + bgm_filter
        audio_map = ["-map", f"[{bgm_label}]"]
        print(f"[bgm] {len(bgm_tracks)} tracks, total ≈ "
              f"{sum(t['duration_sec'] for t in bgm_tracks):.1f}s "
              f"(target {video_duration_s:.1f}s)")
    else:
        filter_complex = video_filter
        audio_map = ["-map", "0:a?"]

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "info",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", *audio_map, "-map_metadata", "3",
        *v_codec, *v_extra,
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output),
    ]
    print(f"[ffmpeg] {source.name} → {output}")
    subprocess.run(cmd, check=True)


# ============================================================
# Entry point
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", "-s", required=True, type=Path)
    ap.add_argument("--output", "-o", type=Path, default=None,
                    help=f"省略時: {DEFAULT_OUTPUT_BASE}/<episode-id>/long_<source-stem>.<ext>")
    ap.add_argument("--episode-id", default="TEST")
    ap.add_argument("--location-primary", required=True)
    ap.add_argument("--location-secondary", required=True)
    ap.add_argument("--shoot-date", required=True, help="撮影日 YYYY-MM-DD")
    ap.add_argument("--chapter-count", type=int, default=14)
    ap.add_argument("--output-format", choices=["sdr-h264", "hlg-hevc", "hlg-prores422hq"],
                    default="sdr-h264")
    ap.add_argument("--keep-overlays", action="store_true")
    # BGM オプション (v0.3 新設)
    ap.add_argument("--bgm-library", type=Path, default=DEFAULT_BGM_LIBRARY)
    ap.add_argument("--bgm-genre", default="lofi",
                    help="カンマ区切り (例: lofi,ambient)。--no-bgm で無効化")
    ap.add_argument("--bgm-seed", type=int, default=None,
                    help="シャッフル seed (再現用)")
    ap.add_argument("--no-bgm", action="store_true",
                    help="BGM オフ (元音声をそのまま使う)")
    args = ap.parse_args()

    if not args.source.exists():
        sys.exit(f"source not found: {args.source}")

    output = args.output or default_output_path(args.source, args.episode_id, args.output_format)
    output.parent.mkdir(parents=True, exist_ok=True)

    duration_s = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(args.source)
    ]).decode().strip())

    badge = build_series_badge()
    badge_path = output.parent / f"_badge_{output.stem}.png"
    badge.save(badge_path)

    location = build_location_card(args.location_primary, args.location_secondary)
    location_path = output.parent / f"_location_{output.stem}.png"
    location.save(location_path)

    chapters_meta = make_chapters_metadata(duration_s, args.chapter_count, args.location_primary)
    chapters_path = output.parent / f"_chapters_{output.stem}.txt"
    chapters_path.write_text(chapters_meta)

    print(f"[duration] {duration_s:.2f}s, chapters: {args.chapter_count}")
    print(f"[overlays] {badge_path.name} / {location_path.name}")

    bgm_tracks = None
    if not args.no_bgm:
        genres = tuple(g.strip() for g in args.bgm_genre.split(",") if g.strip())
        bgm_tracks = select_bgm_tracks(args.bgm_library, duration_s, genres, args.bgm_seed)

    render(args.source, output, args.output_format, badge_path, location_path, chapters_path,
           bgm_tracks, args.bgm_library, duration_s)

    if not args.keep_overlays:
        badge_path.unlink(missing_ok=True)
        location_path.unlink(missing_ok=True)
        chapters_path.unlink(missing_ok=True)
    print(f"✓ {output}")


if __name__ == "__main__":
    main()
