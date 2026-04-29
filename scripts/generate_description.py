#!/usr/bin/env -S uv run --quiet --with pyyaml --with anthropic python
"""episode.yaml + chapters メタデータ → YouTube 説明欄 (多言語) 生成。

入力:
  - episodes/<episode-id>/episode.yaml  (必須、--episode-id で指定)
  - chapters_<output-stem>.txt          (FFmpeg metadata 形式、--chapters で指定)
                                        無ければ episode.yaml の creative.chapters を使う

出力:
  - <out-dir>/description_<episode-id>.md          (本体、JP/ES/EN を1ファイルに併記)
  - <out-dir>/description_<episode-id>_<lang>.txt  (各言語版、YouTube 説明欄貼付用)

使い方:
  scripts/generate_description.py --episode-id DWT_EP002                    # デフォルト (テンプレのみ)
  scripts/generate_description.py --episode-id DWT_EP002 --polish-with-llm  # Claude API で polish (要 API key)
  scripts/generate_description.py --episode-id DWT_EP002 --langs jp,en      # ES スキップ

デフォルトはテンプレ生成のみ。Claude Pro/Max サブスクとは別課金になる Anthropic API は使わない。
polish が欲しい場合は Claude Code 内で生成済みの description_*.txt を貼って対話で磨く運用を想定。
明示的に Claude API を使いたい時のみ --polish-with-llm を付与 (要 ANTHROPIC_API_KEY)。
"""
from __future__ import annotations
import argparse
import os
import re
import sys
from pathlib import Path

import yaml


# ============================================================
# Paths
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_BASE = Path(
    os.environ.get("DELAX_REPORTS_ROOT", str(Path.home() / "Dropbox" / "delax-reports"))
) / "delax-field-archive"


# ============================================================
# Helpers
# ============================================================

def fmt_ts(sec: float) -> str:
    total = int(sec)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def load_episode(episode_id: str) -> dict:
    yaml_path = PROJECT_ROOT / "episodes" / episode_id / "episode.yaml"
    if not yaml_path.exists():
        sys.exit(f"episode.yaml not found: {yaml_path}\n"
                 f"先に episodes/_template/episode.yaml をコピーして埋めて")
    return yaml.safe_load(yaml_path.read_text())


def parse_chapters_metadata(path: Path) -> list[tuple[float, str]]:
    """FFmpeg metadata 形式 chapters_*.txt を parse。"""
    chapters = []
    text = path.read_text()
    for block in re.findall(r"\[CHAPTER\](.+?)(?=\[CHAPTER\]|$)", text, re.DOTALL):
        start_m = re.search(r"START=(\d+)", block)
        title_m = re.search(r"title=(.+)", block)
        if start_m and title_m:
            chapters.append((int(start_m.group(1)) / 1000.0, title_m.group(1).strip()))
    return chapters


def build_chapter_block(chapters: list[tuple[float, str]]) -> str:
    """YouTube 仕様 (00:00 必須 / 最低3章 / 各10秒以上)。"""
    if not chapters:
        return "00:00 Opening"

    out = []
    last_t = -10.0
    for i, (t, name) in enumerate(chapters):
        if i == 0 and t > 0.5:
            t = 0.0
        if t - last_t < 10:
            continue
        out.append(f"{fmt_ts(t)} {name}")
        last_t = t

    if not out or not out[0].startswith("0:00") and not out[0].startswith("00:00"):
        out.insert(0, f"00:00 {chapters[0][1]}")
    return "\n".join(out)


# ============================================================
# Template (no-LLM fallback)
# ============================================================

WEATHER_LABEL = {
    "jp": {"clear": "晴れ", "cloudy": "曇り", "rain": "雨", "fog": "霧", "snow": "雪"},
    "es": {"clear": "soleado", "cloudy": "nublado", "rain": "lluvioso", "fog": "neblina", "snow": "nevado"},
    "en": {"clear": "sunny", "cloudy": "cloudy", "rain": "rainy", "fog": "foggy", "snow": "snowy"},
}
WEATHER_EMOJI = {"clear": "☀️", "cloudy": "☁️", "rain": "🌧️", "fog": "🌫️", "snow": "❄️"}

CHANNEL_URL = "youtube.com/@tacchiradio"


def render_template(ep: dict, lang: str, chapters_block: str) -> str:
    """episode.yaml の値だけで組み立てる decoder-free 版。"""
    title_jp = ep.get("creative", {}).get("episode_title", "(タイトル未定)")
    title_en = ep.get("creative", {}).get("title_en", "(English title TBD)")
    theme = ep.get("creative", {}).get("theme", "")
    location = ep.get("geo", {}).get("location_name", "")
    city = ep.get("geo", {}).get("city", "")
    country = ep.get("geo", {}).get("country", "")
    distance_km = ep.get("geo", {}).get("distance_km", 0)
    elevation_m = ep.get("geo", {}).get("elevation_gain_m", 0)
    weather = ep.get("weather", {}) or {}
    cond = weather.get("condition", "")
    temp = weather.get("temp_c", 0)
    capture = ep.get("capture", {})
    shot_date = capture.get("shot_date", "")
    camera = capture.get("camera", "")
    duration_sec = capture.get("duration_sec", 0)
    duration_min = round(duration_sec / 60, 1) if duration_sec else "?"

    cond_label = WEATHER_LABEL.get(lang, {}).get(cond, cond)
    weather_emoji = WEATHER_EMOJI.get(cond, "🌤️")
    geo_extra = ""
    if distance_km:
        geo_extra = f" (~{distance_km}km, +{elevation_m}m)"

    if lang == "jp":
        hook_parts = [f"{cond_label}の{city}を{duration_min}分歩く、ナレーションなしの街歩き。"]
        if theme:
            hook_parts.append(theme)
        hook = "\n".join(hook_parts)
        meta_block = (
            f"🗓️ 撮影: {shot_date} | {weather_emoji} {cond_label} {temp}°C\n"
            f"🚶 {location}{geo_extra}\n"
            f"🎥 カメラ: {camera}\n"
            f"🎧 ナレーションなし · 環境音 + Lofi BGM\n"
            f"🌐 字幕: 日本語 / Español / English"
        )
        title_line = title_jp
        about = (
            "👤 DELAX について\n"
            "マラガ在住の映像作家。NHKドキュメンタリー制作 25年。\n"
            "ヨーロッパ各地の街をナレーションなしで歩く「DELAX Walking Tour - デラさんぽ」シリーズ配信中。"
        )
        tags_line = f"#{city} #街歩き #WalkingTour #4K #Ambient #Lofi"
    elif lang == "es":
        hook = f"Paseo {cond_label} de {duration_min} minutos por {city}, {country}, sin narración."
        meta_block = (
            f"🗓️ Grabado: {shot_date} | {weather_emoji} {cond_label} {temp}°C\n"
            f"🚶 {location}{geo_extra}\n"
            f"🎥 Cámara: {camera}\n"
            f"🎧 Sin narración · ambiente + Lofi BGM\n"
            f"🌐 Subtítulos: 日本語 / Español / English"
        )
        title_line = title_en
        about = (
            "👤 Sobre DELAX\n"
            "Cineasta japonés afincado en Málaga. 25 años en producción documental NHK.\n"
            "Serie 'DELAX Walking Tour - デラさんぽ' por ciudades europeas, sin narración."
        )
        tags_line = f"#{city} #WalkingTour #4K #Ambient #Lofi #España"
    else:  # en
        hook = f"A {cond_label} {duration_min}-minute walking tour through {city}, {country} (no narration)."
        meta_block = (
            f"🗓️ Filmed: {shot_date} | {weather_emoji} {cond_label} {temp}°C\n"
            f"🚶 {location}{geo_extra}\n"
            f"🎥 Camera: {camera}\n"
            f"🎧 No narration · ambient + Lofi BGM\n"
            f"🌐 Subtitles: 日本語 / Español / English"
        )
        title_line = title_en
        about = (
            "👤 About DELAX\n"
            "Japanese filmmaker based in Málaga. 25 years at NHK documentary production.\n"
            "'DELAX Walking Tour - デラさんぽ' series across European cities — no narration."
        )
        tags_line = f"#{city} #WalkingTour #4K #Ambient #Lofi #Travel"

    return f"""{title_line}

{hook}

{meta_block}

━━━━━━━━━━━━━━━━━━
📍 Chapters
━━━━━━━━━━━━━━━━━━
{chapters_block}

━━━━━━━━━━━━━━━━━━
{about}
━━━━━━━━━━━━━━━━━━

🎵 Music: Storyblocks (licensed)
📺 Channel: {CHANNEL_URL}

{tags_line}
"""


# ============================================================
# LLM (Claude API) version - optional polish
# ============================================================

def llm_polish(template: str, ep: dict, lang: str) -> str:
    """Claude API でテンプレを自然な文体に磨く。失敗したらテンプレを返す。"""
    try:
        import anthropic
    except ImportError:
        return template

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return template

    notes = ep.get("creative", {}).get("notes", "")
    theme = ep.get("creative", {}).get("theme", "")

    lang_label = {"jp": "Japanese", "es": "Spanish", "en": "English"}.get(lang, lang)
    system = f"You are a professional YouTube description writer for ambient walking tour videos. Output only in {lang_label}. Preserve markdown structure, section dividers (━━━), emoji, and chapter timestamps EXACTLY. Polish only the prose paragraphs (hook, about). Do not add or remove sections."

    user = f"""Polish the following YouTube description draft. Keep all timestamps, section dividers, hashtags, and structural elements unchanged. Make the prose paragraphs more engaging and natural.

Episode theme: {theme}
Creator notes: {notes}

DRAFT:
---
{template}
---

Output the polished version only, nothing else."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text
    except Exception as e:
        print(f"[llm] polish failed ({e}), using template", file=sys.stderr)
        return template


# ============================================================
# Main
# ============================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode-id", required=True)
    ap.add_argument("--chapters", type=Path, default=None,
                    help="FFmpeg metadata chapters file. 省略時は episode.yaml の creative.chapters を使う")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help=f"省略時: {DEFAULT_OUTPUT_BASE}/<episode-id>/")
    ap.add_argument("--langs", default="jp,es,en",
                    help="生成言語 (カンマ区切り)。デフォルト全部")
    ap.add_argument("--polish-with-llm", action="store_true",
                    help="Claude API でテンプレを自然文に磨く (要 ANTHROPIC_API_KEY、サブスクとは別課金)。"
                         "デフォルトはテンプレのみで Claude Code 内対話 polish 想定")
    ap.add_argument("--no-llm", action="store_true",
                    help="(後方互換、デフォルト動作なので実質 no-op)")
    args = ap.parse_args()

    ep = load_episode(args.episode_id)

    out_dir = args.out_dir or DEFAULT_OUTPUT_BASE / args.episode_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # chapters 取得
    if args.chapters and args.chapters.exists():
        ch_pairs = parse_chapters_metadata(args.chapters)
    else:
        ch_pairs = [(c["timestamp_sec"], c["label"])
                    for c in ep.get("creative", {}).get("chapters", []) if c.get("label")]
    chapters_block = build_chapter_block(ch_pairs)

    langs = [l.strip() for l in args.langs.split(",") if l.strip()]

    combined = []
    for lang in langs:
        template = render_template(ep, lang, chapters_block)
        polished = llm_polish(template, ep, lang) if args.polish_with_llm else template
        per_lang_path = out_dir / f"description_{args.episode_id}_{lang}.txt"
        per_lang_path.write_text(polished)
        print(f"[gen] {lang} → {per_lang_path.name}")
        combined.append(f"# === {lang.upper()} ===\n\n{polished}")

    md_path = out_dir / f"description_{args.episode_id}.md"
    md_path.write_text("\n\n".join(combined))
    print(f"[gen] combined → {md_path.name}")
    print(f"[gen] dir: {out_dir}")


if __name__ == "__main__":
    main()
