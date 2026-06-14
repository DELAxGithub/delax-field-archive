"""Dropbox source proxy — a low-res, faststart copy of the source the Web editor
scrubs for IN/OUT (D5, handover 2026-06-14).

The browser can't open the multi-GB master on the external SSD, so the Mac
generates a small 480p proxy into the Dropbox-synced reports root; the Web fetches
it to set the highlight IN/OUT. The proxy gets the same discipline as the short
render: temp → ffprobe verify → atomic rename → content hash, so a half-written
proxy never appears at the final path.

`proxy_output_path` and `build_proxy_cmd` are pure (no ffmpeg/fs) so they
unit-test without rendering. `generate_proxy` runs ffmpeg.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .ffprobe import verify_video
from .hashing import dropbox_content_hash
from .paths import safe_path_component

PROXY_HEIGHT = 480           # tall edge; width auto (-2) keeps the source aspect
PROXY_CRF = 30               # scrub-quality, small file
PROXY_AUDIO_KBPS = 96


def reports_root(reports_root: str | Path | None = None) -> Path:
    """Dropbox-synced base. Mirrors render_short.py's DEFAULT_OUTPUT_BASE policy:
    $DELAX_REPORTS_ROOT, else ~/Dropbox/delax-reports."""
    base = reports_root or os.environ.get(
        "DELAX_REPORTS_ROOT", str(Path.home() / "Dropbox" / "delax-reports")
    )
    return Path(base) / "delax-field-archive"


def proxy_output_path(
    episode_id: str, source: str | Path, reports_root_dir: str | Path | None = None
) -> Path:
    safe = safe_path_component(episode_id, label="episode_id")
    return reports_root(reports_root_dir) / safe / f"proxy_{Path(source).stem}.mp4"


def build_proxy_cmd(source: str | Path, dest: str | Path) -> list[str]:
    """ffmpeg argv for the proxy. `scale=-2:H` keeps aspect (even width);
    `+faststart` moves the moov atom up front so the browser can stream-seek."""
    return [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(source),
        "-vf", f"scale=-2:{PROXY_HEIGHT}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(PROXY_CRF),
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", f"{PROXY_AUDIO_KBPS}k",
        "-movflags", "+faststart",
        str(dest),
    ]


def temp_proxy_path(dest: Path) -> Path:
    """Hidden sibling temp with the SAME .mp4 suffix (ffmpeg picks the muxer from
    the extension, and os.replace is atomic within the same directory)."""
    return dest.with_name(f".{dest.stem}.tmp{dest.suffix}")


def generate_proxy(
    episode_id: str,
    source: str | Path,
    *,
    reports_root_dir: str | Path | None = None,
) -> dict:
    """Render the proxy and return {path, content_hash, height}. Fail-closed: a
    missing source raises; a temp that fails ffprobe verification is discarded and
    no final proxy appears."""
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(f"source not found: {source}")

    dest = proxy_output_path(episode_id, source, reports_root_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = temp_proxy_path(dest)
    try:
        proc = subprocess.run(build_proxy_cmd(source, tmp), capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ffmpeg proxy failed (exit {proc.returncode}): "
                f"{(proc.stderr or proc.stdout).strip()}"
            )
        verify_video(tmp)
        os.replace(tmp, dest)  # atomic
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)

    return {
        "path": str(dest),
        "content_hash": dropbox_content_hash(dest),
        "height": PROXY_HEIGHT,
    }
