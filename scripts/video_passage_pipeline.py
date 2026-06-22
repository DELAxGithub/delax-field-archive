#!/usr/bin/env -S uv run --quiet --with pillow python
"""Agent-neutral Video Passage review, render, and YouTube handoff pipeline.

The JSON manifest is the single source of truth. Any coding agent can edit it;
rendering is allowed only after the current content has been approved.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parent.parent
JP_FONT = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
EN_FONT = "/System/Library/Fonts/Avenir Next.ttc"
PUNCTUATION_RE = re.compile(r"[、。，．。,.]")
SRT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+"
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def probe_duration(source: Path) -> float:
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1", str(source),
    ]).decode().strip())


def parse_srt(path: Path) -> list[dict]:
    cues = []
    text = path.read_text(encoding="utf-8").strip()
    for block in re.split(r"\n\s*\n", text):
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        match = SRT_TIME_RE.fullmatch(lines[1].strip())
        if not match:
            continue
        values = [int(value) for value in match.groups()]
        start = values[0] * 3600 + values[1] * 60 + values[2] + values[3] / 1000
        end = values[4] * 3600 + values[5] * 60 + values[6] + values[7] / 1000
        labels = [line.strip() for line in lines[2:] if line.strip()]
        cues.append({
            "id": f"cue-{len(cues) + 1:03d}",
            "start_s": start,
            "end_s": end,
            "place": labels[0] if labels else "",
            "road": labels[1] if len(labels) > 1 else "",
            "eyebrow": "",
            "copy_horizontal": "",
            "copy_vertical": [],
            "review_note": "",
        })
    return cues


def load_gps_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [{
        "time_s": float(row["sample_time_s"]),
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
        "alt_m": float(row["alt_m"]) if row.get("alt_m") else None,
    } for row in rows]


def haversine_m(a: dict, b: dict) -> float:
    radius = 6_371_000
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = math.radians(b["lat"] - a["lat"])
    dl = math.radians(b["lon"] - a["lon"])
    value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def add_speed(rows: list[dict]) -> list[dict]:
    for index, row in enumerate(rows):
        if index == 0:
            row["speed_kmh"] = 0.0
            continue
        elapsed = row["time_s"] - rows[index - 1]["time_s"]
        row["speed_kmh"] = (
            haversine_m(rows[index - 1], row) / elapsed * 3.6 if elapsed > 0 else 0.0
        )
    return rows


def content_payload(manifest: dict) -> dict:
    return {
        "schema_version": manifest["schema_version"],
        "project": {
            "episode_id": manifest["project"]["episode_id"],
            "title": manifest["project"]["title"],
            "location_label": manifest["project"].get("location_label", ""),
        },
        "source": manifest["source"],
        "design": manifest["design"],
        "telemetry": manifest["telemetry"],
        "cues": manifest["cues"],
    }


def content_hash(manifest: dict) -> str:
    encoded = json.dumps(
        content_payload(manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def validation_errors(manifest: dict) -> list[str]:
    errors = []
    if not Path(manifest["source"]["video"]).exists():
        errors.append("source.video does not exist")
    cues = manifest.get("cues", [])
    if not cues:
        errors.append("cues is empty")
    previous_end = -1.0
    for cue in cues:
        prefix = cue.get("id", "cue")
        if cue["start_s"] < previous_end - 0.001:
            errors.append(f"{prefix}: cue times overlap or are out of order")
        if cue["end_s"] <= cue["start_s"]:
            errors.append(f"{prefix}: end_s must be after start_s")
        previous_end = cue["end_s"]
        horizontal = cue.get("copy_horizontal", "")
        vertical = cue.get("copy_vertical", [])
        if not horizontal.strip():
            errors.append(f"{prefix}: copy_horizontal is empty")
        if PUNCTUATION_RE.search(horizontal):
            errors.append(f"{prefix}: punctuation is not allowed")
        if len(vertical) not in (1, 2) or any(not line.strip() for line in vertical):
            errors.append(f"{prefix}: copy_vertical must contain one or two non-empty lines")
        if PUNCTUATION_RE.search("".join(vertical)):
            errors.append(f"{prefix}: punctuation is not allowed in vertical copy")
        if " ".join(vertical).replace("  ", " ").strip() != horizontal.strip():
            errors.append(f"{prefix}: vertical copy must preserve the horizontal wording")
    return errors


def save_manifest(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_init(args) -> None:
    source = args.source.resolve()
    gps_csv = args.gps_csv.resolve()
    srt = args.srt.resolve()
    if not source.exists() or not gps_csv.exists() or not srt.exists():
        sys.exit("source, gps-csv, and srt must exist")
    rows = add_speed(load_gps_csv(gps_csv))
    manifest = {
        "schema_version": 1,
        "project": {
            "episode_id": args.episode_id,
            "title": args.title or source.stem,
            "location_label": args.location_label,
            "created_at": utc_now(),
        },
        "source": {
            "video": str(source),
            "duration_s": probe_duration(source),
            "gps_csv": str(gps_csv),
            "gpx": str(args.gpx.resolve()) if args.gpx else "",
            "fit": str(args.fit.resolve()) if args.fit else "",
        },
        "design": {
            "preset": "video-passage-v1",
            "horizontal": {"width": 3840, "height": 2160},
            "vertical": {"width": 1080, "height": 1920},
            "font_jp": JP_FONT,
            "font_en": EN_FONT,
            "show_place": True,
            "show_road": False,
            "show_route": True,
            "show_speed": True,
            "show_heart_rate": False,
        },
        "telemetry": rows,
        "cues": parse_srt(srt),
        "approval": {
            "status": "draft",
            "approved_at": None,
            "approved_by": None,
            "content_hash": None,
        },
        "outputs": {},
    }
    save_manifest(args.manifest, manifest)
    print(f"[init] {args.manifest}")
    if not args.fit:
        print("[FIT] not supplied: heart rate and cadence will be omitted")
    else:
        print("[FIT] supplied, but FIT decoding/synchronization is not implemented yet")


def nearest_telemetry(manifest: dict, time_s: float) -> dict:
    rows = manifest["telemetry"]
    return min(rows, key=lambda row: abs(row["time_s"] - time_s))


def route_svg(manifest: dict, cue: dict) -> str:
    rows = manifest["telemetry"]
    if not rows:
        return ""
    min_lon = min(row["lon"] for row in rows)
    max_lon = max(row["lon"] for row in rows)
    min_lat = min(row["lat"] for row in rows)
    max_lat = max(row["lat"] for row in rows)
    lon_span = max(max_lon - min_lon, 1e-9)
    lat_span = max(max_lat - min_lat, 1e-9)

    def point(row):
        return (
            8 + (row["lon"] - min_lon) / lon_span * 184,
            92 - (row["lat"] - min_lat) / lat_span * 84,
        )

    sampled = rows[::max(1, len(rows) // 80)]
    if sampled[-1] is not rows[-1]:
        sampled.append(rows[-1])
    path = " ".join(
        f"{'M' if index == 0 else 'L'}{x:.1f} {y:.1f}"
        for index, row in enumerate(sampled)
        for x, y in [point(row)]
    )
    current = nearest_telemetry(manifest, (cue["start_s"] + cue["end_s"]) / 2)
    cx, cy = point(current)
    return (
        f'<svg class="route" viewBox="0 0 200 100">'
        f'<path d="{path}"/><circle cx="{cx:.1f}" cy="{cy:.1f}" r="3"/></svg>'
    )


def extract_review_frames(manifest: dict, review_dir: Path) -> None:
    frames_dir = review_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    source = manifest["source"]["video"]
    for cue in manifest["cues"]:
        frame = frames_dir / f"{cue['id']}.jpg"
        midpoint = (cue["start_s"] + cue["end_s"]) / 2
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{midpoint:.3f}", "-i", source, "-frames:v", "1",
            "-q:v", "3", str(frame),
        ], check=True)


def review_html(manifest: dict, manifest_path: Path) -> str:
    data = json.dumps(manifest, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Video Passage Review</title>
<style>
:root{{--fg:#fff;--sub:rgba(255,255,255,.72)}}*{{box-sizing:border-box}}body{{margin:0;background:#0b0c0e;color:#fff;font-family:"Avenir Next","Helvetica Neue","Hiragino Sans",sans-serif}}main{{width:min(1480px,calc(100% - 36px));margin:28px auto 60px}}h1{{font-size:34px;font-weight:300;letter-spacing:.08em;margin:0 0 7px}}.meta{{color:#858a92;font-size:13px;margin-bottom:18px}}nav{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px}}button{{border:1px solid #383c43;background:transparent;color:#aaa;padding:8px 15px;cursor:pointer}}button.active{{border-color:#fff;color:#fff}}.grid{{display:grid;grid-template-columns:minmax(0,16fr) minmax(280px,5fr);gap:20px}}article{{border-top:1px solid #292c31;padding-top:9px}}h2{{font-size:11px;color:#737881;font-weight:400;letter-spacing:.18em}}.stage{{position:relative;overflow:hidden;background:#111}}.h{{aspect-ratio:16/9}}.v{{aspect-ratio:9/16}}.stage>img{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}.stage:after{{content:"";position:absolute;inset:0;background:linear-gradient(#0003,transparent 30%,transparent 62%,#0006)}}.place{{position:absolute;z-index:2;left:4.7%;top:5.5%;font-size:clamp(18px,2.1vw,35px);font-weight:300;letter-spacing:.07em;text-shadow:0 1px 6px #000}}.place small{{display:block;font-size:.34em;margin-top:.45em;letter-spacing:.15em;color:var(--sub)}}.route{{position:absolute;z-index:2;right:4.5%;top:4%;width:19%;filter:drop-shadow(0 1px 4px #000)}}.route path{{fill:none;stroke:#fffd;stroke-width:1.4;vector-effect:non-scaling-stroke}}.route circle{{fill:#fff;stroke:#fff6;stroke-width:5}}.stats{{position:absolute;z-index:2;right:4.7%;top:24%;text-align:right;font-size:clamp(8px,.72vw,12px);line-height:1.7;letter-spacing:.1em;color:var(--sub)}}.copy{{position:absolute;z-index:2;left:4.7%;bottom:7%;max-width:82%;text-shadow:0 2px 8px #000}}.eyebrow{{font-size:clamp(9px,.8vw,13px);letter-spacing:.18em;color:var(--sub);margin-bottom:.4em}}.ja{{font-size:clamp(17px,2vw,32px);line-height:1.4;letter-spacing:.04em}}.line{{display:block;white-space:nowrap}}.v .place{{left:7%;top:4%;font-size:22px}}.v .route{{right:6%;top:3.5%;width:34%}}.v .stats{{right:7%;top:15%;font-size:8px}}.v .copy{{left:7%;bottom:7%;max-width:86%}}.v .ja{{font-size:clamp(17px,4.2vw,22px)}}.status{{margin-top:20px;border-top:1px solid #292c31;padding-top:14px;color:#aaa;line-height:1.8;font-size:13px}}.status b{{color:#fff}}@media(max-width:850px){{.grid{{grid-template-columns:1fr}}article:last-child{{width:min(100%,390px)}}}}
</style></head><body><main>
<h1>VIDEO PASSAGE REVIEW</h1>
<div class="meta">{html.escape(str(manifest_path))} · approval: <b>{manifest["approval"]["status"]}</b></div>
<nav id="tabs"></nav><section class="grid"><article><h2>LANDSCAPE 16:9</h2><div id="h" class="stage h"></div></article><article><h2>PORTRAIT 9:16</h2><div id="v" class="stage v"></div></article></section>
<div class="status"><b>修正方法</b>　この画面を見ながらAIへ番号と修正文を伝える → AIが review.json を更新 → reviewコマンドで再生成 → approveコマンドで承認。HTMLは表示専用で、原本はJSONです。</div>
</main><script>
const manifest={data};let selected=0;const cues=manifest.cues;
function stage(cue,vertical){{const t=manifest.telemetry.reduce((a,b)=>Math.abs(b.time_s-(cue.start_s+cue.end_s)/2)<Math.abs(a.time_s-(cue.start_s+cue.end_s)/2)?b:a);const lines=(vertical?cue.copy_vertical:[cue.copy_horizontal]).map(x=>`<span class="line">${{x}}</span>`).join("");return `<img src="frames/${{cue.id}}.jpg"><div class="place">${{cue.place}}<small>${{manifest.project.location_label||""}}</small></div>${{cue.route_svg}}<div class="stats">${{Math.round(t.speed_kmh)}} KM/H<br>${{manifest.design.show_heart_rate?"HR — BPM":""}}</div><div class="copy"><div class="eyebrow">${{cue.eyebrow||""}}</div><div class="ja">${{lines}}</div></div>`}}
function render(){{document.getElementById("h").innerHTML=stage(cues[selected],false);document.getElementById("v").innerHTML=stage(cues[selected],true);[...document.querySelectorAll("button")].forEach((b,i)=>b.classList.toggle("active",i===selected))}}
cues.forEach((c,i)=>{{const b=document.createElement("button");b.textContent=`${{String(i+1).padStart(2,"0")}}  ${{c.place}}`;b.onclick=()=>{{selected=i;render()}};document.getElementById("tabs").appendChild(b)}});render();
</script></body></html>"""


def command_review(args) -> None:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    review_dir = args.output_dir or args.manifest.parent / "review"
    extract_review_frames(manifest, review_dir)
    for cue in manifest["cues"]:
        cue["route_svg"] = route_svg(manifest, cue)
    output = review_dir / "index.html"
    output.write_text(review_html(manifest, args.manifest), encoding="utf-8")
    print(f"[review] {output}")


def command_validate(args) -> None:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    errors = validation_errors(manifest)
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        sys.exit(1)
    print("[validate] OK")


def command_approve(args) -> None:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    errors = validation_errors(manifest)
    if errors:
        for error in errors:
            print(f"[ERROR] {error}")
        sys.exit(1)
    manifest["approval"] = {
        "status": "approved",
        "approved_at": utc_now(),
        "approved_by": args.by,
        "content_hash": content_hash(manifest),
    }
    save_manifest(args.manifest, manifest)
    print(f"[approve] {manifest['approval']['content_hash'][:12]} by {args.by}")


def ensure_approved(manifest: dict) -> None:
    approval = manifest.get("approval", {})
    if approval.get("status") != "approved":
        sys.exit("manifest is not approved")
    if approval.get("content_hash") != content_hash(manifest):
        sys.exit("manifest changed after approval; review and approve again")


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def projected_route(rows: list[dict], box: tuple[int, int, int, int]) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = box
    min_lon, max_lon = min(r["lon"] for r in rows), max(r["lon"] for r in rows)
    min_lat, max_lat = min(r["lat"] for r in rows), max(r["lat"] for r in rows)
    lon_span, lat_span = max(max_lon - min_lon, 1e-9), max(max_lat - min_lat, 1e-9)
    return [
        (
            x0 + (row["lon"] - min_lon) / lon_span * (x1 - x0),
            y1 - (row["lat"] - min_lat) / lat_span * (y1 - y0),
        )
        for row in rows
    ]


def make_overlay(manifest: dict, cue: dict, vertical: bool, output: Path) -> None:
    spec = manifest["design"]["vertical" if vertical else "horizontal"]
    width, height = spec["width"], spec["height"]
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    scale = width / (1080 if vertical else 1920)
    left = int(width * (0.07 if vertical else 0.047))
    place_y = int(height * (0.04 if vertical else 0.055))
    copy_y = int(height * (0.82 if vertical else 0.84))
    place_size = int((44 if vertical else 64) * scale)
    copy_size = int((42 if vertical else 58) * scale)
    small_size = int((18 if vertical else 22) * scale)
    jp = font(manifest["design"]["font_jp"], place_size)
    jp_copy = font(manifest["design"]["font_jp"], copy_size)
    en = font(manifest["design"]["font_en"], small_size)
    shadow = max(2, round(scale * 2))

    draw.text((left, place_y), cue["place"], font=jp, fill=(255, 255, 255, 235),
              stroke_width=shadow, stroke_fill=(0, 0, 0, 120))
    location_label = manifest["project"].get("location_label", "")
    if location_label:
        draw.text((left, place_y + place_size * 1.15), location_label, font=en,
                  fill=(255, 255, 255, 180), stroke_width=shadow,
                  stroke_fill=(0, 0, 0, 100))

    rows = manifest["telemetry"]
    map_w = int(width * (0.34 if vertical else 0.19))
    map_h = int(map_w * 0.5)
    map_x = width - left - map_w
    map_y = int(height * 0.04)
    points = projected_route(rows[::max(1, len(rows) // 100)], (map_x, map_y, map_x + map_w, map_y + map_h))
    draw.line(points, fill=(255, 255, 255, 195), width=max(1, round(scale * 2)), joint="curve")
    current = nearest_telemetry(manifest, (cue["start_s"] + cue["end_s"]) / 2)
    marker = projected_route(rows + [current], (map_x, map_y, map_x + map_w, map_y + map_h))[-1]
    radius = max(4, round(scale * 5))
    draw.ellipse((marker[0] - radius, marker[1] - radius, marker[0] + radius, marker[1] + radius),
                 fill=(255, 255, 255, 255))
    speed = round(current.get("speed_kmh", 0))
    draw.text((width - left, map_y + map_h + small_size), f"{speed} KM/H", font=en,
              anchor="ra", fill=(255, 255, 255, 180), stroke_width=shadow,
              stroke_fill=(0, 0, 0, 100))

    if cue.get("eyebrow"):
        draw.text((left, copy_y - small_size * 1.7), cue["eyebrow"], font=en,
                  fill=(255, 255, 255, 180), stroke_width=shadow,
                  stroke_fill=(0, 0, 0, 120))
    lines = cue["copy_vertical"] if vertical else [cue["copy_horizontal"]]
    for index, line in enumerate(lines):
        draw.text((left, copy_y + index * copy_size * 1.45), line, font=jp_copy,
                  fill=(255, 255, 255, 245), stroke_width=shadow,
                  stroke_fill=(0, 0, 0, 150))
    image.save(output)


def render_format(manifest: dict, output: Path, vertical: bool, duration: float | None) -> None:
    source = manifest["source"]["video"]
    spec = manifest["design"]["vertical" if vertical else "horizontal"]
    width, height = spec["width"], spec["height"]
    overlay_dir = output.parent / f"_{output.stem}_overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    cues = [cue for cue in manifest["cues"] if duration is None or cue["start_s"] < duration]
    pngs = []
    for cue in cues:
        png = overlay_dir / f"{cue['id']}.png"
        make_overlay(manifest, cue, vertical, png)
        pngs.append(png)
    inputs = ["-i", source]
    for png in pngs:
        inputs += ["-loop", "1", "-framerate", "30", "-i", str(png)]
    if vertical:
        base = f"[0:v]scale=-2:{height},crop={width}:{height}:(iw-{width})/2:0,fps=30[v0]"
    else:
        base = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps=30[v0]"
        )
    filters = [base]
    current = "v0"
    for index, cue in enumerate(cues, 1):
        end = min(cue["end_s"], duration) if duration is not None else cue["end_s"]
        out = f"v{index}"
        filters.append(
            f"[{current}][{index}:v]overlay=0:0:"
            f"enable='between(t,{cue['start_s']:.3f},{end:.3f})':shortest=1[{out}]"
        )
        current = out
    cmd = ["ffmpeg", "-y", "-hide_banner", *inputs, "-filter_complex", ";".join(filters),
           "-map", f"[{current}]", "-map", "0:a?"]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)]
    subprocess.run(cmd, check=True)


def command_render(args) -> None:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    errors = validation_errors(manifest)
    if errors:
        sys.exit("\n".join(errors))
    ensure_approved(manifest)
    output_dir = args.output_dir or args.manifest.parent / "rendered"
    output_dir.mkdir(parents=True, exist_ok=True)
    formats = ("horizontal", "vertical") if args.format == "both" else (args.format,)
    for name in formats:
        output = output_dir / f"{manifest['project']['episode_id']}-{name}.mp4"
        render_format(manifest, output, name == "vertical", args.duration)
        manifest["outputs"][name] = str(output)
        print(f"[render] {output}")
    save_manifest(args.manifest, manifest)


def command_upload(args) -> None:
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    ensure_approved(manifest)
    video = Path(manifest.get("outputs", {}).get("horizontal", ""))
    if not video.exists():
        sys.exit("approved horizontal output not found; render first")
    cmd = [
        str(PROJECT_ROOT / "scripts" / "upload_youtube.py"),
        "--episode-id", manifest["project"]["episode_id"],
        "--video", str(video),
        "--title", args.title or manifest["project"]["title"],
        "--description", str(args.description),
        "--privacy", "unlisted",
    ]
    if args.thumbnail:
        cmd += ["--thumbnail", str(args.thumbnail)]
    if args.playlist:
        cmd += ["--playlist", args.playlist]
    subprocess.run(cmd, check=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--source", type=Path, required=True)
    init.add_argument("--gps-csv", type=Path, required=True)
    init.add_argument("--gpx", type=Path)
    init.add_argument("--fit", type=Path)
    init.add_argument("--srt", type=Path, required=True)
    init.add_argument("--episode-id", required=True)
    init.add_argument("--title")
    init.add_argument("--location-label", default="",
                      help="small uppercase label below the place, e.g. KANAZAWA · ISHIKAWA")
    init.add_argument("--manifest", type=Path, required=True)
    init.set_defaults(func=command_init)

    review = sub.add_parser("review")
    review.add_argument("--manifest", type=Path, required=True)
    review.add_argument("--output-dir", type=Path)
    review.set_defaults(func=command_review)

    validate = sub.add_parser("validate")
    validate.add_argument("--manifest", type=Path, required=True)
    validate.set_defaults(func=command_validate)

    approve = sub.add_parser("approve")
    approve.add_argument("--manifest", type=Path, required=True)
    approve.add_argument("--by", required=True)
    approve.set_defaults(func=command_approve)

    render = sub.add_parser("render")
    render.add_argument("--manifest", type=Path, required=True)
    render.add_argument("--output-dir", type=Path)
    render.add_argument("--format", choices=["horizontal", "vertical", "both"], default="both")
    render.add_argument("--duration", type=float, help="preview/testing duration")
    render.set_defaults(func=command_render)

    upload = sub.add_parser("upload-unlisted")
    upload.add_argument("--manifest", type=Path, required=True)
    upload.add_argument("--description", type=Path, required=True)
    upload.add_argument("--title")
    upload.add_argument("--thumbnail", type=Path)
    upload.add_argument("--playlist")
    upload.set_defaults(func=command_upload)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
