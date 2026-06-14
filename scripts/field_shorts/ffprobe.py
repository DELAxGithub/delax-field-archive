"""Thin ffprobe wrappers for fail-closed post-render verification.

A rendered short is written to a temp path, then verified here (has a video
stream, non-empty, duration ≈ requested) BEFORE the atomic rename to the final
path. If ffprobe disagrees, the temp is discarded and no final file appears — the
poller's honest-success check never sees a half-written mp4.

The pure predicates (`has_video_stream`, `duration_of`) take a parsed ffprobe dict
so they unit-test without invoking the ffprobe binary. Only stdlib — safe to
import from the render path.
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any


class ProbeError(Exception):
    """ffprobe failed, or its output failed a fail-closed check."""


def probe(path: str | Path) -> dict[str, Any]:
    """Run `ffprobe -show_format -show_streams -print_format json`. Raises
    ProbeError on a missing file, a non-zero ffprobe, or non-JSON output."""
    path = Path(path)
    if not path.exists():
        raise ProbeError(f"file not found: {path}")
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-print_format", "json",
                "-show_format", "-show_streams",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:  # ffprobe binary absent
        raise ProbeError("ffprobe not found on PATH") from e
    except subprocess.CalledProcessError as e:
        raise ProbeError(f"ffprobe failed for {path}: {e.stderr.strip()}") from e
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ProbeError(f"ffprobe output not JSON for {path}: {e}") from e


def has_video_stream(info: dict[str, Any]) -> bool:
    return any(s.get("codec_type") == "video" for s in info.get("streams", []))


def duration_of(info: dict[str, Any]) -> float | None:
    """Container duration as a finite float, or None. A `nan`/`inf` duration is
    treated as missing (None) so it can never pass a `verify_video` window check."""
    raw = info.get("format", {}).get("duration")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def probe_duration(path: str | Path) -> float:
    """Source/clip duration in seconds. Raises ProbeError if unavailable."""
    info = probe(path)
    dur = duration_of(info)
    if dur is None:
        raise ProbeError(f"no duration in ffprobe output for {path}")
    return dur


def verify_video(
    path: str | Path,
    *,
    expect_duration: float | None = None,
    tolerance: float = 1.5,
    parsed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail-closed verification of a rendered file. Raises ProbeError unless the
    file has a video stream, is non-empty, and (if expect_duration given) its
    duration is within `tolerance` seconds of expected. `parsed` injects a probe
    dict for unit tests. Returns the probe dict."""
    info = parsed if parsed is not None else probe(path)
    if not has_video_stream(info):
        raise ProbeError(f"no video stream in {path}")
    # 空ファイル検査は実ファイル経路のみ。`parsed` 注入時 (ユニットテスト) は
    # サイズ検査を呼び出し側責務とする。
    if parsed is None and Path(path).stat().st_size == 0:
        raise ProbeError(f"empty file: {path}")
    if expect_duration is not None:
        dur = duration_of(info)
        if dur is None:
            raise ProbeError(f"no duration to verify in {path}")
        if abs(dur - expect_duration) > tolerance:
            raise ProbeError(
                f"duration {dur:.2f}s differs from expected "
                f"{expect_duration:.2f}s by more than {tolerance}s"
            )
    return info
