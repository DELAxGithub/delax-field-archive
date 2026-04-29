#!/usr/bin/env -S uv run --quiet --with pyyaml python
"""ショート動画用キャプション生成 (YouTube Shorts / Instagram Reels / TikTok)。

入力: episode.yaml + (本編 YouTube URL は episode.yaml の publish.youtube_url から取得)
出力: <out-dir>/shorts/
  - shorts_<episode-id>_youtube.txt  (#shorts タグ必須、説明欄に full URL)
  - shorts_<episode-id>_instagram.txt (link in bio 誘導)
  - shorts_<episode-id>_tiktok.txt   (link in bio 誘導、TikTok 向けハッシュタグ)

3プラットフォームで動画ファイル本体は同一 (1080x1920 9:16)、メタデータだけ差別化。

使い方:
  scripts/generate_shorts_caption.py --episode-id TEST_marseille2_2026-04-02
  scripts/generate_shorts_caption.py --episode-id ... --hook "旧市街の path"   # シーン description 上書き
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_BASE = Path(
    os.environ.get("DELAX_REPORTS_ROOT", str(Path.home() / "Dropbox" / "delax-reports"))
) / "delax-field-archive"


def load_episode(episode_id: str) -> dict:
    p = PROJECT_ROOT / "episodes" / episode_id / "episode.yaml"
    if not p.exists():
        sys.exit(f"episode.yaml not found: {p}")
    return yaml.safe_load(p.read_text())


def build_youtube_shorts(ep: dict, full_url: str, hook: str) -> str:
    """YouTube Shorts: #shorts タグ必須、説明欄に full URL クリッカブル"""
    title = ep.get("creative", {}).get("episode_title", "")
    title_en = ep.get("creative", {}).get("title_en", "")
    city = ep.get("geo", {}).get("city", "")

    return f"""{title} #Shorts

{hook}

🎬 Full walking tour ↓
{full_url}

🎵 Lofi BGM · No narration
📺 DELAX Walking Tour - デラさんぽ

#Shorts #{city} #WalkingTour #4K #Ambient #Lofi #Travel #Europe
"""


def build_instagram_reels(ep: dict, full_url: str, hook: str) -> str:
    """Instagram Reels: link in bio 誘導、英日混在 (グローバル + 日本フォロワー)"""
    title = ep.get("creative", {}).get("episode_title", "")
    city = ep.get("geo", {}).get("city", "")
    country = ep.get("geo", {}).get("country", "")

    return f"""{title} 🌅

{hook}

🚶‍♂️ {city}, {country}
🎵 Lofi BGM · no narration
📺 4K Walking Tour

Full 16-min version on YouTube ↗ link in bio
@tacchiradio

#{city} #{city.lower()}walk #WalkingTour #4KTravel #LofiVibes #France #SouthOfFrance #Travel #Reels #街歩き #マルセイユ
"""


def build_tiktok(ep: dict, full_url: str, hook: str) -> str:
    """TikTok: fyp 狙い、link in bio 誘導、短めキャプション"""
    title = ep.get("creative", {}).get("episode_title", "")
    city = ep.get("geo", {}).get("city", "")

    return f"""{title} 🌿 {city} walking tour

Full 16-min version → link in bio
@tacchiradio

#fyp #{city} #WalkingTour #4K #Travel #France #Lofi #ASMRwalk #TravelTok #街歩き
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode-id", required=True)
    ap.add_argument("--full-url", default=None,
                    help="本編 YouTube URL。省略時は episode.yaml の publish.youtube_url を使う")
    ap.add_argument("--hook", default=None,
                    help="シーン description (省略時は episode.yaml の theme を使う)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help=f"省略時: {DEFAULT_OUTPUT_BASE}/<episode-id>/shorts/")
    args = ap.parse_args()

    ep = load_episode(args.episode_id)

    full_url = args.full_url or ep.get("publish", {}).get("youtube_url", "")
    if not full_url:
        sys.exit(f"YouTube URL not found in episode.yaml (publish.youtube_url) — pass --full-url")

    hook = args.hook or ep.get("creative", {}).get("theme", "")

    out_dir = args.out_dir or DEFAULT_OUTPUT_BASE / args.episode_id / "shorts"
    out_dir.mkdir(parents=True, exist_ok=True)

    captions = {
        "youtube": build_youtube_shorts(ep, full_url, hook),
        "instagram": build_instagram_reels(ep, full_url, hook),
        "tiktok": build_tiktok(ep, full_url, hook),
    }

    for platform, text in captions.items():
        p = out_dir / f"shorts_{args.episode_id}_{platform}.txt"
        p.write_text(text)
        print(f"[caption] {platform} → {p.name}")

    print(f"[done] {out_dir}")


if __name__ == "__main__":
    main()
