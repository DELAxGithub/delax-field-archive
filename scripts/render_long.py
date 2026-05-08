#!/usr/bin/env -S uv run --quiet --with pillow python
"""長尺街歩きレンダラ v0.6 (Step 1+2+3 + cinematic opening modes)。

入力: 動画 + 場所テロップ + 撮影日 + シリーズID
出力: 4K SDR / HLG HEVC / HLG ProRes 422 HQ
       デフォルトは $DELAX_REPORTS_ROOT/delax-field-archive/<episode-id>/

設計: docs/long-form-spec-v0.md
流用元: scripts/render_short.py (draw_text_with_halo, safe zone)

v0.6 (2026-05-08 ブリーフ反映): --opening-mode 追加
- branded   — 現状互換 (黄色バッジ + 場所カード hold 6.5s + 9.8秒オープニング)
- cinematic — hero clip (3-5s) prepend + 細身ラベル fade、バッジは hero 後に登場、heavy 場所カードは出さない
- textless  — hero clip prepend のみ、テキスト一切なし、バッジは hero 後

v0.2 改修 (2026-04-27 マルセイユ 1st レンダ後フィードバック):
- 場所カード alpha 140 → 200 (明るい背景でも字が浮かない)
- 場所カード PRIMARY 192 → 240px / halo offset 6
- フォント統一 → 丸ゴ W4 (バッジと共通)
- バッジ文字色 (40,30,0) → (60,40,10) ダークブラウン
- オープニング演出 (branded): 絶景先 → 1〜2秒目に透かしフェードイン
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
# Cinematic opening (v0.6, 細身フォント / hero clip prepend)
# ============================================================
FONT_THIN_CANDIDATES = [
    "/System/Library/Fonts/HelveticaNeue.ttc",   # macOS 標準
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNSDisplay.ttf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
]
OPENING_LABEL_FONT_SIZE = 96
OPENING_LABEL_COLOR = (245, 245, 240, 235)
OPENING_LABEL_HALO = (0, 0, 0, 180)
OPENING_LABEL_HALO_OFFSET = 2
OPENING_LABEL_Y_RATIO = 0.83   # 4K canvas 下方
OPENING_LABEL_FADE_IN_START_S = 0.6
OPENING_LABEL_FADE_IN_DURATION_S = 1.0
# label の hold 終了は hero_duration - 1.0 (動的、render() 内で計算)
OPENING_LABEL_FADE_OUT_DURATION_S = 0.8

DEFAULT_HERO_DURATION_S = 4.0
BADGE_FADE_AFTER_HERO_GAP_S = 0.3   # hero 終わってから 0.3s 後に badge fade in 開始


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


def _resolve_thin_font() -> str:
    for path in FONT_THIN_CANDIDATES:
        if Path(path).exists():
            return path
    return FONT_ROUND_W4   # フォールバック


def build_opening_label(text: str) -> Image.Image:
    """cinematic mode の細身ラベル overlay (4K RGBA)。textless 時は呼ばれない。"""
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    if not text:
        return overlay
    draw = ImageDraw.Draw(overlay)
    font_path = _resolve_thin_font()
    font = ImageFont.truetype(font_path, OPENING_LABEL_FONT_SIZE)
    text_w = draw.textlength(text, font=font)
    x = (CANVAS_W - text_w) / 2
    y = int(CANVAS_H * OPENING_LABEL_Y_RATIO)
    draw_text_with_halo(draw, (x, y), text, font,
                        OPENING_LABEL_COLOR, OPENING_LABEL_HALO,
                        halo_offset=OPENING_LABEL_HALO_OFFSET)
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
    # crossfade より短い曲を許すと accum の増分が負になり無限ループに陥る。
    # crossfade × 1.5 を最小尺として弾く。
    MIN_TRACK_DURATION_S = BGM_CROSSFADE_S * 1.5
    candidates = [
        c for c in catalog
        if c["genre"] in genres
        and c.get("intro_silence_ms", 0) < BGM_INTRO_SILENCE_MAX_MS
        and c.get("duration_sec", 0) >= MIN_TRACK_DURATION_S
    ]
    if not candidates:
        sys.exit(
            f"no BGM candidates for genres={genres} "
            f"(after intro_silence + min_duration={MIN_TRACK_DURATION_S}s filters)"
        )

    rng = random.Random(seed)
    rng.shuffle(candidates)

    selected: list[dict] = []
    accum = 0.0
    # ループ上限: フィルタを通った時点で平均尺は MIN_TRACK_DURATION_S 以上なので
    # 最悪ケースでも total_duration_s / MIN_TRACK_DURATION_S 反復で尺を満たすが、
    # 念のため余裕を持って 10000 を上限とする。これを超えたら catalog/filter のバグ。
    MAX_ITER = 10000
    for i in range(MAX_ITER):
        if accum + BGM_CROSSFADE_S >= total_duration_s:
            break
        track = candidates[i % len(candidates)]
        selected.append(track)
        # 各曲は次の曲と BGM_CROSSFADE_S だけ重なる → 実効寄与 = duration - crossfade
        accum += track["duration_sec"] - BGM_CROSSFADE_S
    else:
        sys.exit(
            f"BGM selection exceeded {MAX_ITER} iterations without filling "
            f"video_duration_s={total_duration_s}. catalog/filter の不整合の可能性。"
        )

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
           badge_png: Path, location_png: Path | None, chapters_meta: Path,
           bgm_tracks: list[dict] | None,
           bgm_library: Path,
           video_duration_s: float,
           opening_mode: str = "branded",
           hero_offset_s: float = 0.0,
           hero_duration_s: float = 0.0,
           label_png: Path | None = None,
           hide_badge_during_opening: bool = False) -> None:
    """video_duration_s は最終出力尺 (cinematic/textless では prepend 後の尺)。

    opening_mode:
      - branded:   現状互換 (badge fade@1.0, loc card 1.5..9.8s)
      - cinematic: hero clip prepend (hero_duration_s) + 細身ラベル fade、loc card は出さない、
                   badge は hero 後に fade in
      - textless:  hero clip prepend のみ、ラベル/loc card なし、badge は hero 後に fade in
    """
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

    # ---- Inputs と video_filter を mode 別に組み立てる ----
    # 入力レイアウト:
    #   branded:   0=source, 1=badge, 2=loc, 3=meta, 4..=BGM
    #   cinematic: 0=source, 1=badge, 2=label, 3=meta, 4..=BGM
    #   textless:  0=source, 1=badge, 2=meta, 3..=BGM
    inputs = ["-i", str(source),
              "-loop", "1", "-framerate", str(FPS), "-i", str(badge_png)]

    if opening_mode == "branded":
        if location_png is None:
            sys.exit("branded mode requires location_png")
        inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(location_png)]
        inputs += ["-i", str(chapters_meta)]
        bgm_input_offset = 4

        video_filter = (
            f"[1:v]format=rgba,"
            f"fade=t=in:st={BADGE_FADE_IN_START_S}:d={BADGE_FADE_IN_DURATION_S}:alpha=1[badge_a];"
            f"[2:v]format=rgba,"
            f"fade=t=in:st={LOCATION_FADE_IN_START_S}:d={LOCATION_FADE_IN_DURATION_S}:alpha=1,"
            f"fade=t=out:st={LOCATION_HOLD_END_S}:d={LOCATION_FADE_OUT_DURATION_S}:alpha=1[loc_a];"
            f"[0:v][badge_a]overlay=0:0:shortest=1[v1];"
            f"[v1][loc_a]overlay=0:0:shortest=1[outv]"
        )

    elif opening_mode in ("cinematic", "textless"):
        hero_end = hero_offset_s + hero_duration_s
        # badge fade in は hero 後 (hide_badge_during_opening=True が前提)
        badge_fade_start = hero_duration_s + BADGE_FADE_AFTER_HERO_GAP_S if hide_badge_during_opening else BADGE_FADE_IN_START_S
        # 動画の concat: hero クリップ → 元動画 (t=0 から)
        video_concat = (
            f"[0:v]trim=start={hero_offset_s}:end={hero_end},setpts=PTS-STARTPTS[hero_v];"
            f"[0:v]setpts=PTS-STARTPTS[main_v];"
            f"[hero_v][main_v]concat=n=2:v=1:a=0[v_concat];"
        )

        if opening_mode == "cinematic":
            if label_png is None:
                sys.exit("cinematic mode requires label_png")
            inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(label_png)]
            inputs += ["-i", str(chapters_meta)]
            bgm_input_offset = 4

            label_hold_end = max(hero_duration_s - 1.0, OPENING_LABEL_FADE_IN_START_S + OPENING_LABEL_FADE_IN_DURATION_S + 0.2)

            video_filter = (
                video_concat
                + f"[1:v]format=rgba,fade=t=in:st={badge_fade_start}:d={BADGE_FADE_IN_DURATION_S}:alpha=1[badge_a];"
                + f"[2:v]format=rgba,"
                + f"fade=t=in:st={OPENING_LABEL_FADE_IN_START_S}:d={OPENING_LABEL_FADE_IN_DURATION_S}:alpha=1,"
                + f"fade=t=out:st={label_hold_end}:d={OPENING_LABEL_FADE_OUT_DURATION_S}:alpha=1[label_a];"
                + f"[v_concat][label_a]overlay=0:0:shortest=1[v1];"
                + f"[v1][badge_a]overlay=0:0:shortest=1[outv]"
            )
        else:  # textless
            inputs += ["-i", str(chapters_meta)]
            bgm_input_offset = 3

            video_filter = (
                video_concat
                + f"[1:v]format=rgba,fade=t=in:st={badge_fade_start}:d={BADGE_FADE_IN_DURATION_S}:alpha=1[badge_a];"
                + f"[v_concat][badge_a]overlay=0:0:shortest=1[outv]"
            )
    else:
        sys.exit(f"unknown opening_mode: {opening_mode}")

    if bgm_tracks:
        for t in bgm_tracks:
            inputs += ["-i", str(bgm_library / t["path"])]
        bgm_filter, bgm_label = build_bgm_filter_chain(bgm_tracks, video_duration_s, bgm_input_offset)
        filter_complex = video_filter + ";" + bgm_filter
        audio_map = ["-map", f"[{bgm_label}]"]
        print(f"[bgm] {len(bgm_tracks)} tracks, total ≈ "
              f"{sum(t['duration_sec'] for t in bgm_tracks):.1f}s "
              f"(target {video_duration_s:.1f}s)")
    elif opening_mode in ("cinematic", "textless"):
        # BGM オフ + cinematic/textless は元音声も hero 部分で concat 必要
        audio_concat = (
            f";[0:a]atrim=start={hero_offset_s}:end={hero_offset_s + hero_duration_s},asetpts=PTS-STARTPTS[hero_a];"
            f"[0:a]asetpts=PTS-STARTPTS[main_a];"
            f"[hero_a][main_a]concat=n=2:v=0:a=1[aout]"
        )
        filter_complex = video_filter + audio_concat
        audio_map = ["-map", "[aout]"]
    else:
        filter_complex = video_filter
        audio_map = ["-map", "0:a?"]

    # chapters_meta は inputs の中で source の次の次... mode によって位置が変わるので index を記録
    # (branded: index=3, cinematic: index=3, textless: index=2)
    meta_index = bgm_input_offset - 1   # bgm_input_offset の直前が meta
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "info",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]", *audio_map, "-map_metadata", str(meta_index),
        *v_codec, *v_extra,
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(output),
    ]
    print(f"[ffmpeg] {source.name} → {output} (mode={opening_mode})")
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
    # Cinematic opening (v0.6 新設)
    ap.add_argument("--opening-mode", choices=["branded", "cinematic", "textless"],
                    default="branded",
                    help="branded=現状互換 / cinematic=hero clip prepend + 細身ラベル / textless=hero clip のみ")
    ap.add_argument("--hero-source-offset", type=float, default=None,
                    help="cinematic/textless: 元動画内のドラマチックカット開始秒")
    ap.add_argument("--hero-duration", type=float, default=DEFAULT_HERO_DURATION_S,
                    help=f"cinematic/textless: hero クリップ尺 (デフォルト {DEFAULT_HERO_DURATION_S}s)")
    ap.add_argument("--opening-label", default="",
                    help="cinematic mode のみ。空文字なら textless と同じ挙動")
    ap.add_argument("--badge-during-opening", action="store_true",
                    help="cinematic/textless でも badge を従来通り (1.0s) から fade in")
    args = ap.parse_args()

    if not args.source.exists():
        sys.exit(f"source not found: {args.source}")

    if args.opening_mode in ("cinematic", "textless"):
        if args.hero_source_offset is None:
            sys.exit(f"--opening-mode={args.opening_mode} requires --hero-source-offset")
        if args.hero_duration <= 0:
            sys.exit("--hero-duration must be positive")

    output = args.output or default_output_path(args.source, args.episode_id, args.output_format)
    output.parent.mkdir(parents=True, exist_ok=True)

    source_duration_s = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(args.source)
    ]).decode().strip())

    # cinematic/textless: 出力尺は元尺 + hero (prepend するため)
    if args.opening_mode in ("cinematic", "textless"):
        if args.hero_source_offset + args.hero_duration > source_duration_s:
            sys.exit(f"hero clip range ({args.hero_source_offset}..{args.hero_source_offset + args.hero_duration}s) "
                     f"exceeds source duration {source_duration_s:.1f}s")
        total_duration_s = source_duration_s + args.hero_duration
    else:
        total_duration_s = source_duration_s

    badge = build_series_badge()
    badge_path = output.parent / f"_badge_{output.stem}.png"
    badge.save(badge_path)

    location_path: Path | None = None
    label_path: Path | None = None
    if args.opening_mode == "branded":
        location = build_location_card(args.location_primary, args.location_secondary)
        location_path = output.parent / f"_location_{output.stem}.png"
        location.save(location_path)
    elif args.opening_mode == "cinematic":
        label_text = args.opening_label  # 空文字なら build_opening_label が透明 PNG を返す
        label = build_opening_label(label_text)
        label_path = output.parent / f"_label_{output.stem}.png"
        label.save(label_path)

    chapters_meta = make_chapters_metadata(total_duration_s, args.chapter_count, args.location_primary)
    chapters_path = output.parent / f"_chapters_{output.stem}.txt"
    chapters_path.write_text(chapters_meta)

    print(f"[duration] source={source_duration_s:.2f}s, output={total_duration_s:.2f}s, "
          f"chapters: {args.chapter_count}, mode={args.opening_mode}")
    overlay_files = [badge_path.name]
    if location_path:
        overlay_files.append(location_path.name)
    if label_path:
        overlay_files.append(label_path.name)
    print(f"[overlays] {' / '.join(overlay_files)}")

    bgm_tracks = None
    if not args.no_bgm:
        genres = tuple(g.strip() for g in args.bgm_genre.split(",") if g.strip())
        bgm_tracks = select_bgm_tracks(args.bgm_library, total_duration_s, genres, args.bgm_seed)

    render(args.source, output, args.output_format, badge_path, location_path, chapters_path,
           bgm_tracks, args.bgm_library, total_duration_s,
           opening_mode=args.opening_mode,
           hero_offset_s=args.hero_source_offset or 0.0,
           hero_duration_s=args.hero_duration if args.opening_mode != "branded" else 0.0,
           label_png=label_path,
           hide_badge_during_opening=(args.opening_mode != "branded" and not args.badge_during_opening))

    if not args.keep_overlays:
        badge_path.unlink(missing_ok=True)
        if location_path:
            location_path.unlink(missing_ok=True)
        if label_path:
            label_path.unlink(missing_ok=True)
        chapters_path.unlink(missing_ok=True)
    print(f"✓ {output}")


if __name__ == "__main__":
    main()
