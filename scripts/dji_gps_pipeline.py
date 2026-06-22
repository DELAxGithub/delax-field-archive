#!/usr/bin/env -S uv run --quiet --with pillow python
"""DJI Osmo Action GPS pipeline: LRF/MP4 -> CSV/GPX -> SRT -> burned preview.

The GPS Bluetooth Remote Controller writes location samples into DJI's `djmd`
metadata track. ExifTool 13.55 can decode these samples from Action 6 files.
LRF is preferred because it contains the same metadata and is much smaller.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


GPS_FIELDS = ("SampleTime", "GPSDateTime", "GPSLatitude", "GPSLongitude", "GPSAltitude")
PLACE_PRIORITY = (
    "neighbourhood", "suburb", "quarter", "city_district", "borough",
    "village", "town", "city",
)
ROAD_PRIORITY = ("road", "pedestrian", "footway", "cycleway", "path")
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "delax-field-archive/dji-gps-pipeline"
FONT_CANDIDATES = (
    "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
)


def copy_index(prefix: str) -> int:
    if prefix == "":
        return 0
    match = re.fullmatch(r"Copy(\d+)", prefix)
    return int(match.group(1)) + 1 if match else sys.maxsize


def records_from_exiftool(data: dict) -> list[dict]:
    """Convert ExifTool -G4 JSON keys into ordered DJI telemetry records."""
    grouped: dict[str, dict] = {}
    for key, value in data.items():
        if ":" not in key:
            continue
        prefix, field = key.rsplit(":", 1)
        if field in GPS_FIELDS:
            grouped.setdefault(prefix, {})[field] = value

    records = []
    for prefix in sorted(grouped, key=copy_index):
        row = grouped[prefix]
        if not all(row.get(field) is not None for field in GPS_FIELDS[:4]):
            continue
        records.append({
            "sample_time_s": float(row["SampleTime"]),
            "datetime_utc": str(row["GPSDateTime"]),
            "lat": float(row["GPSLatitude"]),
            "lon": float(row["GPSLongitude"]),
            "alt_m": float(row["GPSAltitude"]) if row.get("GPSAltitude") is not None else None,
        })
    return records


def downsample_one_hz(records: list[dict]) -> list[dict]:
    """Keep the first valid DJI GPS sample in each recording second."""
    out = []
    seen_seconds = set()
    for row in records:
        second = math.floor(row["sample_time_s"])
        if second in seen_seconds:
            continue
        seen_seconds.add(second)
        out.append(row)
    return out


def extract_records(source: Path) -> list[dict]:
    cmd = [
        "exiftool", "-ee", "-G4", "-n", "-j", "-api", "LargeFileSupport=1",
        *(f"-{field}" for field in GPS_FIELDS), str(source),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    if not payload:
        return []
    return downsample_one_hz(records_from_exiftool(payload[0]))


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["sample_time_s", "datetime_utc", "lat", "lon", "alt_m"]
        )
        writer.writeheader()
        writer.writerows(rows)


def write_gpx(rows: list[dict], path: Path) -> None:
    points = []
    for row in rows:
        dt = row["datetime_utc"].replace(":", "-", 2).replace(" ", "T") + "Z"
        ele = f"<ele>{row['alt_m']:.3f}</ele>" if row["alt_m"] is not None else ""
        points.append(
            f'<trkpt lat="{row["lat"]:.8f}" lon="{row["lon"]:.8f}">'
            f"{ele}<time>{html.escape(dt)}</time></trkpt>"
        )
    body = "\n      ".join(points)
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="delax-field-archive" '
        'xmlns="http://www.topografix.com/GPX/1/1">\n'
        "  <trk><name>DJI Action GPS</name><trkseg>\n"
        f"      {body}\n"
        "  </trkseg></trk>\n"
        "</gpx>\n",
        encoding="utf-8",
    )


def load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return [{
        "sample_time_s": float(row["sample_time_s"]),
        "datetime_utc": row["datetime_utc"],
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
        "alt_m": float(row["alt_m"]) if row.get("alt_m") else None,
    } for row in rows]


def cache_key(lat: float, lon: float) -> str:
    return f"{lat:.4f},{lon:.4f}"


def reverse_geocode(lat: float, lon: float, cache: dict) -> dict:
    key = cache_key(lat, lon)
    if key in cache:
        return cache[key]
    query = urllib.parse.urlencode({
        "format": "jsonv2",
        "lat": f"{lat:.7f}",
        "lon": f"{lon:.7f}",
        "zoom": "17",
        "addressdetails": "1",
        "accept-language": "ja,en;q=0.8",
    })
    request = urllib.request.Request(
        f"{NOMINATIM_URL}?{query}", headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.load(response)
    cache[key] = data
    time.sleep(1.05)
    return data


def pick(address: dict, priorities: tuple[str, ...], fallback: str) -> str:
    for field in priorities:
        if address.get(field):
            return str(address[field])
    return fallback


def collapse_segments(points: list[dict], total_duration: float, min_segment_s: float) -> list[dict]:
    segments = []
    for point in points:
        label = (point["place"], point["road"])
        if not segments or segments[-1]["label"] != label:
            if segments:
                segments[-1]["end"] = point["sample_time_s"]
            segments.append({
                "start": point["sample_time_s"],
                "end": total_duration,
                "label": label,
            })
    if segments:
        segments[-1]["end"] = total_duration

    while len(segments) > 1:
        short_index = next(
            (i for i, segment in enumerate(segments)
             if segment["end"] - segment["start"] < min_segment_s),
            None,
        )
        if short_index is None:
            break
        i = short_index
        if i == 0:
            segments[1]["start"] = segments[0]["start"]
        else:
            segments[i - 1]["end"] = segments[i]["end"]
        segments.pop(i)
    return segments


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, rem = divmod(milliseconds, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(segments: list[dict], path: Path) -> None:
    blocks = []
    for index, segment in enumerate(segments, 1):
        place, road = segment["label"]
        text = place if not road or road == place else f"{place}\n{road}"
        blocks.append(
            f"{index}\n{srt_timestamp(segment['start'])} --> "
            f"{srt_timestamp(segment['end'])}\n{text}"
        )
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def geocode_csv(csv_path: Path, srt_path: Path, cache_path: Path,
                interval_s: float, min_segment_s: float) -> list[dict]:
    rows = load_csv(csv_path)
    if not rows:
        raise ValueError("GPS CSV contains no rows")
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    points = []
    next_sample = rows[0]["sample_time_s"]
    for row in rows:
        if row["sample_time_s"] + 1e-6 < next_sample:
            continue
        data = reverse_geocode(row["lat"], row["lon"], cache)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        address = data.get("address", {})
        points.append({
            **row,
            "place": pick(address, PLACE_PRIORITY, address.get("municipality", "現在地")),
            "road": pick(address, ROAD_PRIORITY, ""),
        })
        next_sample += interval_s
    if points[-1]["sample_time_s"] < rows[-1]["sample_time_s"] - 1:
        row = rows[-1]
        data = reverse_geocode(row["lat"], row["lon"], cache)
        address = data.get("address", {})
        points.append({
            **row,
            "place": pick(address, PLACE_PRIORITY, address.get("municipality", "現在地")),
            "road": pick(address, ROAD_PRIORITY, ""),
        })
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    total_duration = rows[-1]["sample_time_s"] + 1.0
    segments = collapse_segments(points, total_duration, min_segment_s)
    write_srt(segments, srt_path)
    return segments


SRT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+"
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)


def parse_srt(path: Path) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        match = SRT_TIME_RE.fullmatch(lines[1].strip())
        if not match:
            continue
        values = [int(value) for value in match.groups()]
        start = values[0] * 3600 + values[1] * 60 + values[2] + values[3] / 1000
        end = values[4] * 3600 + values[5] * 60 + values[6] + values[7] / 1000
        cues.append({"start": start, "end": end, "text": "\n".join(lines[2:])})
    return cues


def find_font() -> str:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError("Japanese font not found")


def make_caption_png(text: str, path: Path, width: int, height: int) -> None:
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    primary_font = ImageFont.truetype(find_font(), max(34, width // 26))
    secondary_font = ImageFont.truetype(find_font(), max(24, width // 42))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        canvas.save(path)
        return
    fonts = [primary_font] + [secondary_font] * (len(lines) - 1)
    boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=2)
             for line, font in zip(lines, fonts)]
    text_width = max(box[2] - box[0] for box in boxes)
    line_heights = [box[3] - box[1] for box in boxes]
    gap = max(10, height // 90)
    box_width = min(width - 80, text_width + 72)
    box_height = sum(line_heights) + gap * (len(lines) - 1) + 48
    x0 = (width - box_width) // 2
    y0 = height - box_height - max(70, height // 13)
    draw.rounded_rectangle(
        (x0, y0, x0 + box_width, y0 + box_height),
        radius=20, fill=(0, 0, 0, 180),
    )
    y = y0 + 24
    for line, font, line_height in zip(lines, fonts, line_heights):
        line_width = draw.textlength(line, font=font)
        x = (width - line_width) / 2
        draw.text(
            (x, y), line, font=font, fill=(255, 255, 250, 255),
            stroke_width=2, stroke_fill=(0, 0, 0, 220),
        )
        y += line_height + gap
    canvas.save(path)


def render_preview(source: Path, srt_path: Path, output: Path,
                   duration_s: float | None, width: int) -> None:
    cues = parse_srt(srt_path)
    if duration_s is not None:
        cues = [cue for cue in cues if cue["start"] < duration_s]
    if not cues:
        raise ValueError("No SRT cues overlap the requested preview")
    height = round(width * 9 / 16)
    overlay_dir = output.parent / f"_{output.stem}_captions"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    pngs = []
    for index, cue in enumerate(cues, 1):
        png = overlay_dir / f"caption_{index:03d}.png"
        make_caption_png(cue["text"], png, width, height)
        pngs.append(png)

    inputs = ["-i", str(source)]
    for png in pngs:
        inputs += ["-loop", "1", "-framerate", "30", "-i", str(png)]
    filters = [f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1[v0]"]
    current = "v0"
    for index, cue in enumerate(cues, 1):
        out = f"v{index}"
        end = min(cue["end"], duration_s) if duration_s is not None else cue["end"]
        filters.append(
            f"[{current}][{index}:v]overlay=0:0:"
            f"enable='between(t,{cue['start']:.3f},{end:.3f})':shortest=1[{out}]"
        )
        current = out
    cmd = [
        "ffmpeg", "-y", "-hide_banner", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", f"[{current}]", "-map", "0:a?",
    ]
    if duration_s is not None:
        cmd += ["-t", str(duration_s)]
    cmd += [
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(output),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    extract = sub.add_parser("extract")
    extract.add_argument("--source", required=True, type=Path)
    extract.add_argument("--csv", required=True, type=Path)
    extract.add_argument("--gpx", required=True, type=Path)

    geocode = sub.add_parser("geocode")
    geocode.add_argument("--csv", required=True, type=Path)
    geocode.add_argument("--srt", required=True, type=Path)
    geocode.add_argument("--cache", required=True, type=Path)
    geocode.add_argument("--interval", type=float, default=30)
    geocode.add_argument("--min-segment", type=float, default=30)

    render = sub.add_parser("render")
    render.add_argument("--source", required=True, type=Path)
    render.add_argument("--srt", required=True, type=Path)
    render.add_argument("--output", required=True, type=Path)
    render.add_argument("--duration", type=float, default=None)
    render.add_argument("--width", type=int, default=1920)

    args = parser.parse_args()
    if args.command == "extract":
        rows = extract_records(args.source)
        if not rows:
            sys.exit(f"GPS data not found: {args.source}")
        write_csv(rows, args.csv)
        write_gpx(rows, args.gpx)
        print(f"[GPS] {len(rows)} one-Hz samples -> {args.csv} / {args.gpx}")
    elif args.command == "geocode":
        segments = geocode_csv(
            args.csv, args.srt, args.cache, args.interval, args.min_segment
        )
        print(f"[SRT] {len(segments)} segments -> {args.srt}")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        render_preview(args.source, args.srt, args.output, args.duration, args.width)
        print(f"[render] {args.output}")


if __name__ == "__main__":
    main()
