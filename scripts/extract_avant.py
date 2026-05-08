#!/usr/bin/env -S uv run --quiet --with pillow --with numpy --with pyyaml python
"""ダイジェスト型アバン (場所ごとカット連結) を AI 推薦で生成する v0.6.1。

入力: 完成 / クリーンレンダ済み長尺 mp4
処理:
  1. 動画尺を均等サンプリング (デフォルト 5秒間隔) で候補 timestamp 列挙
  2. 各候補で 1フレーム抽出 → 480p に縮小 → 視覚インパクトスコア計算
     - color_std:    RGB ばらつき (画の彩り)
     - edge_density: 隣接ピクセル差 (構成の細密さ)
     - hist_entropy: 輝度ヒストグラムのエントロピー (構図の情報量)
  3. z-score 化して合算 → 高スコア順にソート
  4. 互いに最低 MIN_GAP_S (デフォルト 60s) 離す制約で N=10 個選定
  5. ffmpeg filter_complex で 各 timestamp から CLIP_DUR 秒切り出し → concat
出力:
  - <out>/avant_<stem>.mp4               (20秒、4K SDR H.264)
  - <out>/avant_<stem>_picks.json        (選定 timestamp と score、再現性)
  - <out>/_preview/avant_pick_<NN>.preview.jpg  (Read 用)

使い方:
    scripts/extract_avant.py \\
        --source ~/.../long_DWT_EP002_clean.mp4 \\
        --episode-id DWT_EP002 \\
        --count 10 \\
        --clip-dur 2.0
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import numpy as np


# ============================================================
# Avant location label (4K, 細身、半透明黒帯、控えめ)
# ============================================================
CANVAS_W, CANVAS_H = 3840, 2160
FONT_LABEL = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
FONT_LABEL_FALLBACK = "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc"
LABEL_PRIMARY_FONT_SIZE = 96
LABEL_SECONDARY_FONT_SIZE = 56
LABEL_GAP = 14
LABEL_BG = (0, 0, 0, 160)
LABEL_BG_PADDING_X = 48
LABEL_BG_PADDING_Y = 28
LABEL_PRIMARY_COLOR = (245, 245, 240, 240)
LABEL_SECONDARY_COLOR = (210, 210, 200, 220)
LABEL_BOTTOM_MARGIN = 280


def _resolve_label_font() -> str:
    return FONT_LABEL if Path(FONT_LABEL).exists() else FONT_LABEL_FALLBACK


def build_avant_label(primary: str, secondary: str = "") -> Image.Image:
    """場所テロップ overlay (4K RGBA、画面下方、半透明黒帯)。primary 空なら透明 PNG。"""
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    if not primary:
        return overlay
    draw = ImageDraw.Draw(overlay)
    font_path = _resolve_label_font()
    primary_font = ImageFont.truetype(font_path, LABEL_PRIMARY_FONT_SIZE)
    secondary_font = ImageFont.truetype(font_path, LABEL_SECONDARY_FONT_SIZE)
    primary_w = draw.textlength(primary, font=primary_font)
    secondary_w = draw.textlength(secondary, font=secondary_font) if secondary else 0
    block_h = LABEL_PRIMARY_FONT_SIZE + (LABEL_GAP + LABEL_SECONDARY_FONT_SIZE if secondary else 0)
    bg_w = max(primary_w, secondary_w) + LABEL_BG_PADDING_X * 2
    bg_h = block_h + LABEL_BG_PADDING_Y * 2
    bg_y0 = CANVAS_H - LABEL_BOTTOM_MARGIN - bg_h
    bg_x0 = (CANVAS_W - bg_w) / 2
    bg_layer = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    ImageDraw.Draw(bg_layer).rounded_rectangle(
        [bg_x0, bg_y0, bg_x0 + bg_w, bg_y0 + bg_h], radius=18, fill=LABEL_BG)
    overlay.alpha_composite(bg_layer)
    primary_x = (CANVAS_W - primary_w) / 2
    primary_y = bg_y0 + LABEL_BG_PADDING_Y
    draw.text((primary_x, primary_y), primary, fill=LABEL_PRIMARY_COLOR, font=primary_font)
    if secondary:
        secondary_x = (CANVAS_W - secondary_w) / 2
        secondary_y = primary_y + LABEL_PRIMARY_FONT_SIZE + LABEL_GAP
        draw.text((secondary_x, secondary_y), secondary, fill=LABEL_SECONDARY_COLOR, font=secondary_font)
    return overlay


# ============================================================
# SRT parser (timestamp -> caption lookup)
# ============================================================
SRT_TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")


def parse_srt(path: Path) -> list[dict]:
    """SRT ファイルを cue list に変換: [{'start': sec, 'end': sec, 'text': str}, ...]"""
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", text.strip())
    cues = []
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        # 1行目はインデックス、2行目がタイムコード、それ以降が本文
        ts_line_idx = 1 if lines[0].strip().isdigit() else 0
        if ts_line_idx >= len(lines):
            continue
        ts_match = SRT_TIME_RE.findall(lines[ts_line_idx])
        if len(ts_match) < 2:
            continue
        h1, m1, s1, ms1 = ts_match[0]
        h2, m2, s2, ms2 = ts_match[1]
        start = int(h1) * 3600 + int(m1) * 60 + int(s1) + int(ms1) / 1000
        end = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(ms2) / 1000
        body = "\n".join(lines[ts_line_idx + 1:]).strip()
        cues.append({"start": start, "end": end, "text": body})
    return cues


# 地名カタカナ → 現地スペイン語表記の正規化マップ
# walking-tour-pipeline の Nominatim が municipality を日本語で返すため、
# 場所テロップでは現地語 (Málaga, Andalucía 等) に統一する
LOCATION_NORMALIZE = {
    "マラガ": "Málaga",
    "アンダルシア州": "Andalucía",
    "アンダルシア": "Andalucía",
    "スペイン": "España",
    "セビーリャ": "Sevilla",
    "セビージャ": "Sevilla",
    "コルドバ": "Córdoba",
    "グラナダ": "Granada",
    "カディス": "Cádiz",
    "ロンダ": "Ronda",
    "マルベーリャ": "Marbella",
}


def normalize_location_text(text: str) -> str:
    """カタカナ municipality 名を現地表記に置換 (場所テロップ統一用)。"""
    if not text:
        return text
    for ja, native in LOCATION_NORMALIZE.items():
        text = text.replace(ja, native)
    return text


def lookup_caption_at(t: float, cues: list[dict]) -> tuple[str, str]:
    """t 秒を含む / または最も近い cue から (primary, secondary) を返す。
    地名は現地スペイン語表記に正規化する。"""
    for c in cues:
        if c["start"] <= t <= c["end"]:
            p, s = _split_primary_secondary(c["text"])
            return (normalize_location_text(p), normalize_location_text(s))
    # 含む cue が無ければ最近接
    if not cues:
        return ("", "")
    nearest = min(cues, key=lambda c: min(abs(c["start"] - t), abs(c["end"] - t)))
    p, s = _split_primary_secondary(nearest["text"])
    return (normalize_location_text(p), normalize_location_text(s))


def _split_primary_secondary(text: str) -> tuple[str, str]:
    """SRT cue body の改行 → (1行目, 2行目以降結合)"""
    if not text:
        return ("", "")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return ("", "")
    primary = lines[0]
    secondary = " · ".join(lines[1:]) if len(lines) > 1 else ""
    return (primary, secondary)


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(path)
    ])
    return float(out.decode().strip())


def extract_thumb(source: Path, t_sec: float, dest: Path, scale_w: int = 480) -> bool:
    r = subprocess.run([
        "ffmpeg", "-y", "-ss", f"{t_sec:.3f}", "-i", str(source),
        "-vframes", "1", "-vf", f"scale={scale_w}:-2",
        "-q:v", "5", str(dest)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return r.returncode == 0 and dest.exists()


def score_frame(img: Image.Image) -> dict:
    """visual interest score の3成分を返す (大きいほど派手・情報量多い)。"""
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    # color std: RGB チャネルそれぞれの空間 stddev の平均
    color_std = float(arr.std(axis=(0, 1)).mean())
    # edge density: グレースケール隣接差分の平均絶対値
    gray = arr.mean(axis=2)
    dx = np.abs(np.diff(gray, axis=1)).mean()
    dy = np.abs(np.diff(gray, axis=0)).mean()
    edge_density = float((dx + dy) / 2.0)
    # histogram entropy: 輝度 256bin のシャノンエントロピー
    hist, _ = np.histogram(gray, bins=64, range=(0, 256), density=True)
    p = hist[hist > 0]
    hist_entropy = float(-(p * np.log2(p)).sum())
    return {
        "color_std": color_std,
        "edge_density": edge_density,
        "hist_entropy": hist_entropy,
    }


def zscore(values: list[float]) -> list[float]:
    arr = np.array(values, dtype=np.float64)
    mu = arr.mean()
    sigma = arr.std()
    if sigma < 1e-9:
        return [0.0] * len(values)
    return ((arr - mu) / sigma).tolist()


def pick_with_spread(candidates: list[dict], n: int, min_gap_s: float) -> list[dict]:
    """高スコア順に最低 min_gap_s 離れる制約で n 個選ぶ。"""
    sorted_c = sorted(candidates, key=lambda c: c["score"], reverse=True)
    picks: list[dict] = []
    for c in sorted_c:
        if all(abs(c["t"] - p["t"]) >= min_gap_s for p in picks):
            picks.append(c)
            if len(picks) >= n:
                break
    picks.sort(key=lambda c: c["t"])   # 時系列順に
    return picks


def pick_per_landmark(candidates: list[dict], landmarks: list[dict],
                      window_s: float, clip_dur: float, source_dur: float) -> list[dict]:
    """各 landmark の timestamp_sec ± window_s 内で最高スコアの候補を採用する。

    landmarks が末尾 (t + clip_dur > source_dur) の場合は最終 frame に近づける。
    候補が見つからない landmark はスキップ (warning)。
    """
    picks: list[dict] = []
    for lm in landmarks:
        lm_t = float(lm.get("timestamp_sec", 0))
        # window 範囲 [t-window, t+window] の候補
        in_window = [c for c in candidates
                     if lm_t - window_s <= c["t"] <= lm_t + window_s
                     and c["t"] + clip_dur <= source_dur]
        if not in_window:
            print(f"  ! landmark {lm.get('name', '?')} (t={lm_t:.0f}s): no candidate in ±{window_s:.0f}s window",
                  file=sys.stderr)
            continue
        best = max(in_window, key=lambda c: c["score"])
        picks.append({**best, "landmark": lm.get("name", "")})
    return picks


def load_landmarks_from_yaml(yaml_path: Path) -> list[dict]:
    """yaml ファイルから geo.landmarks リストを返す。yaml ライブラリで読む。"""
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML required for --landmarks-yaml (uv adds via --with pyyaml)")
    data = yaml.safe_load(yaml_path.read_text())
    return data.get("geo", {}).get("landmarks", [])


def render_avant(source: Path, picks: list[dict], clip_dur: float,
                 output: Path, output_w: int = 3840,
                 xfade_ms: int = 0,
                 label_pngs: list[Path] | None = None,
                 bgm_path: Path | None = None,
                 bgm_fade_ms: int = 800) -> None:
    """ffmpeg filter_complex で picks を順次切り出し → (label overlay) → (xfade) → concat → mp4。

    xfade_ms > 0 の時はクロスフェード接続 (各 clip の出力尺は clip_dur のまま、
    重なり部分が xfade_ms ぶん潰れる)。

    label_pngs: 各 clip の場所テロップ PNG (4K RGBA)。len は picks と同じ。
    bgm_path: 指定があれば BGM mp3 を amix (元音声は drop)。
    """
    n = len(picks)
    xfade = xfade_ms / 1000.0
    parts: list[str] = []

    # ---- 各 clip の trim + scale + (label overlay) ----
    for i, p in enumerate(picks):
        parts.append(
            f"[0:v]trim=start={p['t']:.3f}:end={p['t'] + clip_dur:.3f},"
            f"setpts=PTS-STARTPTS,fps=30,scale={output_w}:-2:flags=lanczos,"
            f"format=yuv420p,settb=AVTB[c{i}_raw]"
        )
        if label_pngs and label_pngs[i] is not None:
            # Label PNG は input index = 1 + i (source=0, labels=1..n)
            label_idx = 1 + i
            label_fade_in = 0.4
            label_fade_out_start = max(clip_dur - 0.6, 0.5)
            parts.append(
                f"[{label_idx}:v]format=rgba,scale={output_w}:-2:flags=lanczos,"
                f"fade=t=in:st=0.3:d={label_fade_in}:alpha=1,"
                f"fade=t=out:st={label_fade_out_start}:d=0.5:alpha=1[lbl{i}]"
            )
            parts.append(
                f"[c{i}_raw][lbl{i}]overlay=0:0:shortest=1,format=yuv420p[c{i}]"
            )
        else:
            parts.append(f"[c{i}_raw]copy[c{i}]")
        # 音声: BGM 使う時はソース音声不要、a{i} を作らない (未接続エラー回避)
        if not bgm_path:
            parts.append(
                f"[0:a]atrim=start={p['t']:.3f}:end={p['t'] + clip_dur:.3f},"
                f"asetpts=PTS-STARTPTS[a{i}]"
            )

    # ---- 動画の連結: xfade or hard concat ----
    if xfade_ms > 0 and n > 1:
        # xfade を順次チェイン: [c0][c1]xfade=offset=(clip_dur - xfade)[v01];
        #                      [v01][c2]xfade=offset=(2*clip_dur - 2*xfade)[v012]; ...
        prev = "c0"
        for i in range(1, n):
            offset = i * clip_dur - i * xfade
            out = "outv" if i == n - 1 else f"vx{i}"
            parts.append(
                f"[{prev}][c{i}]xfade=transition=fade:duration={xfade}:offset={offset:.3f}[{out}]"
            )
            prev = out
        # 出力尺: n*clip_dur - (n-1)*xfade
        total_v_dur = n * clip_dur - (n - 1) * xfade
    else:
        v_streams = "".join(f"[c{i}]" for i in range(n))
        parts.append(f"{v_streams}concat=n={n}:v=1:a=0[outv]")
        total_v_dur = n * clip_dur

    # ---- 音声 ----
    inputs_extra: list[str] = []
    if bgm_path:
        # BGM only (元音声 drop)。afade in/out + atrim で出力尺に合わせる
        bgm_input_idx = 1 + (len(picks) if label_pngs else 0)
        bgm_fade = bgm_fade_ms / 1000.0
        fade_out_start = max(total_v_dur - bgm_fade, 0.0)
        parts.append(
            f"[{bgm_input_idx}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"atrim=duration={total_v_dur:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d={bgm_fade},afade=t=out:st={fade_out_start:.3f}:d={bgm_fade},"
            f"loudnorm=I=-16:TP=-1.5:LRA=11[outa]"
        )
        audio_map = ["-map", "[outa]"]
    else:
        # 元音声 concat (xfade 時も音声はハードカット concat、単純化)
        a_streams = "".join(f"[a{i}]" for i in range(n))
        parts.append(f"{a_streams}concat=n={n}:v=0:a=1[outa]")
        audio_map = ["-map", "[outa]"]

    filter_complex = ";".join(parts)

    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "info",
        "-i", str(source),
    ]
    if label_pngs:
        for lp in label_pngs:
            if lp is None:
                # 透明 PNG を渡す必要がある場合の fallback
                continue
            cmd += ["-loop", "1", "-framerate", "30", "-t", f"{clip_dur:.3f}", "-i", str(lp)]
    if bgm_path:
        cmd += ["-i", str(bgm_path)]
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[outv]", *audio_map,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k",
        str(output),
    ]
    print(f"[ffmpeg] avant render → {output} "
          f"(n={n} clip_dur={clip_dur} xfade={xfade}s "
          f"bgm={'on' if bgm_path else 'off'} "
          f"labels={'on' if label_pngs else 'off'})")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("--- ffmpeg stderr (last 3KB) ---", file=sys.stderr)
        print(r.stderr[-3000:], file=sys.stderr)
        print("--- filter_complex ---", file=sys.stderr)
        print(filter_complex, file=sys.stderr)
        sys.exit(f"ffmpeg failed (exit {r.returncode})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, type=Path,
                    help="完成 / クリーン長尺 mp4")
    ap.add_argument("--episode-id", default="UNKNOWN")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="省略時: <source の親>/avant/")
    ap.add_argument("--count", type=int, default=10, help="選定カット数")
    ap.add_argument("--clip-dur", type=float, default=3.0, help="各カット秒 (v0.6.2 default 3s)")
    ap.add_argument("--sample-every-s", type=float, default=5.0,
                    help="スコア計算用サンプル間隔")
    ap.add_argument("--xfade-ms", type=int, default=400,
                    help="クロスフェード (ms)。0 でハードカット")
    ap.add_argument("--captions-srt", type=Path, default=None,
                    help="場所テロップ駆動: SRT を読んで各 clip 開始時の cue を overlay")
    ap.add_argument("--no-labels", action="store_true",
                    help="--captions-srt 指定時でもラベル overlay を出さない")
    ap.add_argument("--bgm", type=Path, default=None,
                    help="BGM mp3/wav。指定時は元音声 drop で BGM のみ")
    ap.add_argument("--bgm-fade-ms", type=int, default=800,
                    help="BGM の fade in/out (ms)")
    ap.add_argument("--min-gap-s", type=float, default=60.0,
                    help="picks 間の最低時間距離")
    ap.add_argument("--margin-pct", type=float, default=5.0,
                    help="先頭/末尾を除外するパーセンテージ")
    ap.add_argument("--landmarks-yaml", type=Path, default=None,
                    help="landmark 駆動モード: episode.yaml から geo.landmarks[] を読み、"
                         "各 landmark の ±window 内で最高スコアフレームを採用 (--count 無視)")
    ap.add_argument("--landmark-window-s", type=float, default=45.0,
                    help="landmark 駆動時の探索 window (±N秒)")
    ap.add_argument("--output-width", type=int, default=3840)
    ap.add_argument("--keep-thumbs", action="store_true",
                    help="スコア計算用 480p サムネを残す")
    args = ap.parse_args()

    if not args.source.exists():
        sys.exit(f"source not found: {args.source}")

    out_dir = args.out_dir or args.source.parent / "avant"
    out_dir.mkdir(parents=True, exist_ok=True)
    preview_dir = out_dir / "_preview"
    preview_dir.mkdir(exist_ok=True)
    thumbs_dir = out_dir / "_thumbs"
    thumbs_dir.mkdir(exist_ok=True)

    duration = ffprobe_duration(args.source)
    margin = duration * args.margin_pct / 100.0
    span = duration - margin * 2.0
    n_samples = max(int(span / args.sample_every_s), args.count * 3)
    print(f"[avant] duration={duration:.1f}s margin={margin:.1f}s "
          f"sampling {n_samples} frames every {span/n_samples:.1f}s")

    candidates: list[dict] = []
    for i in range(n_samples):
        t = margin + span * (i + 0.5) / n_samples
        thumb_path = thumbs_dir / f"thumb_{i:04d}_t{int(t):05d}.jpg"
        if not extract_thumb(args.source, t, thumb_path):
            continue
        try:
            with Image.open(thumb_path) as img:
                s = score_frame(img)
        except Exception as e:
            print(f"  ! score failed at t={t:.1f}: {e}", file=sys.stderr)
            continue
        candidates.append({"t": t, **s, "thumb": str(thumb_path)})
        if (i + 1) % 50 == 0:
            print(f"  ... {i+1}/{n_samples} sampled")

    if not candidates:
        sys.exit("no candidates — check ffmpeg / source")

    # z-score 合算 (3成分等重み)
    z_color = zscore([c["color_std"] for c in candidates])
    z_edge = zscore([c["edge_density"] for c in candidates])
    z_hist = zscore([c["hist_entropy"] for c in candidates])
    for i, c in enumerate(candidates):
        c["score"] = z_color[i] + z_edge[i] + z_hist[i]

    if args.landmarks_yaml:
        landmarks = load_landmarks_from_yaml(args.landmarks_yaml)
        if not landmarks:
            sys.exit(f"no landmarks found in {args.landmarks_yaml}")
        print(f"[landmarks] {len(landmarks)} entries loaded from {args.landmarks_yaml}")
        picks = pick_per_landmark(candidates, landmarks, args.landmark_window_s,
                                  args.clip_dur, duration)
        if len(picks) < 2:
            sys.exit(f"only {len(picks)} landmarks matched candidates — widen --landmark-window-s")
    else:
        picks = pick_with_spread(candidates, args.count, args.min_gap_s)
        if len(picks) < args.count:
            print(f"⚠ only {len(picks)} picks (requested {args.count}). "
                  f"Try smaller --min-gap-s.", file=sys.stderr)

    # picks の preview を保存 (Read 用)
    for i, p in enumerate(picks):
        prev = preview_dir / f"avant_pick_{i+1:02d}.preview.jpg"
        subprocess.run([
            "sips", "-Z", "1600", "-s", "format", "jpeg",
            p["thumb"], "--out", str(prev)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        lm = f" [{p['landmark']}]" if p.get("landmark") else ""
        print(f"  [{i+1:02d}] t={p['t']:.1f}s score={p['score']:.2f}{lm} "
              f"(color={p['color_std']:.1f} edge={p['edge_density']:.1f} "
              f"entropy={p['hist_entropy']:.2f})")

    # メタ JSON 保存
    picks_json = out_dir / f"avant_{args.source.stem}_picks.json"
    picks_json.write_text(json.dumps({
        "source": str(args.source),
        "episode_id": args.episode_id,
        "count": args.count,
        "clip_dur": args.clip_dur,
        "min_gap_s": args.min_gap_s,
        "picks": [{k: v for k, v in p.items() if k != "thumb"} for p in picks],
    }, indent=2, ensure_ascii=False))
    print(f"[meta] {picks_json}")

    # captions.srt 駆動の label PNG 生成
    label_pngs: list[Path] | None = None
    if args.captions_srt and not args.no_labels:
        if not args.captions_srt.exists():
            sys.exit(f"captions.srt not found: {args.captions_srt}")
        cues = parse_srt(args.captions_srt)
        print(f"[srt] loaded {len(cues)} cues from {args.captions_srt.name}")
        labels_dir = out_dir / "_labels"
        labels_dir.mkdir(exist_ok=True)
        label_pngs = []
        for i, p in enumerate(picks):
            primary, secondary = lookup_caption_at(p["t"], cues)
            label_img = build_avant_label(primary, secondary)
            lp = labels_dir / f"label_{i+1:02d}.png"
            label_img.save(lp)
            label_pngs.append(lp)
            print(f"  [{i+1:02d}] caption: {primary} / {secondary or '(no secondary)'}")

    # ffmpeg で連結レンダ
    output = out_dir / f"avant_{args.source.stem}.mp4"
    render_avant(args.source, picks, args.clip_dur, output, args.output_width,
                 xfade_ms=args.xfade_ms,
                 label_pngs=label_pngs,
                 bgm_path=args.bgm,
                 bgm_fade_ms=args.bgm_fade_ms)

    if not args.keep_thumbs:
        shutil.rmtree(thumbs_dir, ignore_errors=True)
    n_picks = len(picks)
    total_dur = n_picks * args.clip_dur - (n_picks - 1) * (args.xfade_ms / 1000.0 if args.xfade_ms > 0 else 0)
    print(f"✓ {output}  ({n_picks} cuts × {args.clip_dur}s "
          f"{f'with {args.xfade_ms}ms xfade' if args.xfade_ms else 'hard cut'} "
          f"= {total_dur:.1f}s)")


if __name__ == "__main__":
    main()
