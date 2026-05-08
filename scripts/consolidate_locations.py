#!/usr/bin/env -S uv run --quiet --with pyyaml python
"""4 ソース (chapters.json + captions.srt + episode.yaml + gps.json) を
単一の locations.yaml に正規化する v0.7。

設計判断:
  - **一次ソース = captions.srt** (NHK 文法 cue が既に walking-tour-pipeline で生成済)
  - 各 cue を 1 location として扱い、id / timestamp_start / timestamp_end / primary / secondary
  - chapters.json から該当区間の章を chapters_raw_indices にぶら下げる
  - episode.yaml.geo.landmarks[] と timestamp 近接でマッチ → coord を入れる
  - description_jp / description_en / description_es は **空** で生成 (Claude Code 内で対話的に埋める)
  - role_avant は heuristic で start (最初) / goal (最後) / middle (それ以外) を仮セット

使い方:
    scripts/consolidate_locations.py --episode-id DWT_EP002
    # → episodes/DWT_EP002/locations.yaml が出る
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml


SRT_TIME_RE = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})")

# 地名カタカナ → 現地スペイン語表記の正規化 (extract_avant.py と同じ)
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
    if not text:
        return text
    for ja, native in LOCATION_NORMALIZE.items():
        text = text.replace(ja, native)
    return text


def parse_srt(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", text.strip())
    cues = []
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        ts_idx = 1 if lines[0].strip().isdigit() else 0
        ts_match = SRT_TIME_RE.findall(lines[ts_idx])
        if len(ts_match) < 2:
            continue
        h1, m1, s1, ms1 = ts_match[0]
        h2, m2, s2, ms2 = ts_match[1]
        start = int(h1) * 3600 + int(m1) * 60 + int(s1) + int(ms1) / 1000
        end = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(ms2) / 1000
        body = "\n".join(lines[ts_idx + 1:]).strip()
        body_lines = [l.strip() for l in body.splitlines() if l.strip()]
        primary = normalize_location_text(body_lines[0] if body_lines else "")
        secondary = normalize_location_text(" · ".join(body_lines[1:]) if len(body_lines) > 1 else "")
        cues.append({"start": start, "end": end, "primary": primary, "secondary": secondary})
    return cues


def find_landmark_match(srt_cue: dict, landmarks: list[dict]) -> dict | None:
    """SRT cue の中央時刻に最も近い landmark を返す (60秒以内)。"""
    cue_mid = (srt_cue["start"] + srt_cue["end"]) / 2
    best = None
    best_dist = 60.0
    for lm in landmarks:
        lm_t = float(lm.get("timestamp_sec", 0))
        if srt_cue["start"] <= lm_t <= srt_cue["end"]:
            return lm   # 完全に区間内、即採用
        dist = min(abs(lm_t - srt_cue["start"]), abs(lm_t - srt_cue["end"]))
        if dist < best_dist:
            best_dist = dist
            best = lm
    return best


def find_chapters_in_range(start: float, end: float, chapters_merged: list[dict]) -> list[int]:
    """chapters.json の chapters_merged から start..end の範囲に入るインデックスを返す。
    yaml の可読性のため、長いリストは range 文字列 (例 'A-B') に圧縮してもよい。
    """
    indices = []
    for i, c in enumerate(chapters_merged):
        t = float(c.get("t_s", 0))
        if start <= t <= end:
            indices.append(i)
    return indices


def compress_indices(indices: list[int]) -> list:
    """連続するインデックスを 'A-B' 文字列に圧縮 (yaml の見た目改善)。"""
    if not indices:
        return []
    sorted_idx = sorted(indices)
    out = []
    run_start = sorted_idx[0]
    prev = run_start
    for x in sorted_idx[1:]:
        if x == prev + 1:
            prev = x
            continue
        out.append(f"{run_start}-{prev}" if prev > run_start else str(run_start))
        run_start = prev = x
    out.append(f"{run_start}-{prev}" if prev > run_start else str(run_start))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode-id", required=True, help="例: DWT_EP002")
    ap.add_argument("--episode-yaml", type=Path, default=None,
                    help="省略時: episodes/<EP>/episode.yaml")
    ap.add_argument("--reports-dir", type=Path, default=None,
                    help="省略時: $DELAX_REPORTS_ROOT/delax-field-archive/<EP>/")
    ap.add_argument("--captions-srt", type=Path, default=None,
                    help="省略時: <reports-dir>/captions.srt")
    ap.add_argument("--chapters-json", type=Path, default=None,
                    help="省略時: <reports-dir>/chapters.json")
    ap.add_argument("--out", type=Path, default=None,
                    help="省略時: episodes/<EP>/locations.yaml")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    episode_yaml = args.episode_yaml or repo_root / "episodes" / args.episode_id / "episode.yaml"
    if not episode_yaml.exists():
        sys.exit(f"episode.yaml not found: {episode_yaml}")
    ep = yaml.safe_load(episode_yaml.read_text())
    ep_duration = float(ep.get("capture", {}).get("duration_sec", 0) or 0)

    reports_root = Path(os.environ.get("DELAX_REPORTS_ROOT",
                                       str(Path.home() / "Dropbox" / "delax-reports")))
    reports_dir = args.reports_dir or reports_root / "delax-field-archive" / args.episode_id
    captions_path = args.captions_srt or reports_dir / "captions.srt"
    chapters_path = args.chapters_json or reports_dir / "chapters.json"

    if not captions_path.exists():
        sys.exit(f"captions.srt not found: {captions_path} — run walking-tour-pipeline first")

    cues = parse_srt(captions_path)
    print(f"[srt] loaded {len(cues)} cues from {captions_path.name}")

    landmarks = ep.get("geo", {}).get("landmarks", [])
    print(f"[yaml] {len(landmarks)} landmarks in episode.yaml")

    chapters_merged = []
    if chapters_path.exists():
        ch_data = json.loads(chapters_path.read_text())
        chapters_merged = ch_data.get("chapters_merged", []) or ch_data.get("chapters_raw", [])
        print(f"[chapters] {len(chapters_merged)} merged chapters in {chapters_path.name}")
    else:
        print(f"[chapters] none ({chapters_path} missing)")

    # --- locations を構築 ---
    n = len(cues)
    locations = []
    for i, cue in enumerate(cues):
        # captions.srt は raw concat (52min) ベースなので、clean 動画尺を超える cue は clamp
        end_clamped = min(cue["end"], ep_duration) if ep_duration > 0 else cue["end"]
        start_clamped = min(cue["start"], end_clamped)
        loc = {
            "id": f"L{i+1:02d}",
            "timestamp_start": round(start_clamped, 1),
            "timestamp_end": round(end_clamped, 1),
            "duration_sec": round(end_clamped - start_clamped, 1),
            "primary": cue["primary"],
            "secondary": cue["secondary"],
            "coord": None,
            "chapters_raw_ranges": compress_indices(
                find_chapters_in_range(start_clamped, end_clamped, chapters_merged)),
            "role_avant": "start" if i == 0 else ("goal" if i == n - 1 else "middle"),
            "description_jp": "",
            "description_en": "",
            "description_es": "",
        }
        # episode.yaml landmark とマッチして coord を入れる
        lm = find_landmark_match(cue, landmarks)
        if lm:
            loc["coord"] = lm.get("coord")
            loc["matched_landmark_name"] = lm.get("name")
        locations.append(loc)

    out_yaml = {
        "episode_id": args.episode_id,
        "source_video": ep.get("capture", {}).get("source_video", ""),
        "duration_sec": ep.get("capture", {}).get("duration_sec"),
        "n_locations": len(locations),
        "_note": "description_jp/en/es は Claude Code 内で対話的に埋める。"
                 "matched_landmark_name は SRT cue の時刻に最も近い episode.yaml landmark。",
        "locations": locations,
    }

    out_path = args.out or repo_root / "episodes" / args.episode_id / "locations.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.dump(out_yaml, allow_unicode=True, sort_keys=False, indent=2))
    print(f"✓ {out_path}  ({len(locations)} locations)")
    for loc in locations:
        coord_str = f"{loc['coord']}" if loc["coord"] else "(no coord)"
        print(f"  {loc['id']} {loc['primary']} / {loc['secondary'] or '-'} [{loc['role_avant']}] {coord_str}")


if __name__ == "__main__":
    main()
