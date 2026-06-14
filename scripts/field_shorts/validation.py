"""Fail-closed validation for the field-shorts render path.

Two guards, both run BEFORE ffmpeg so a bad input never burns a render:
  - clip range   : start >= 0, 0 < duration <= cap, and (if known) the clip fits
                   inside the source.
  - telop width  : the centered place/info text must fit the cross-platform safe
                   zone — centered max width 752px (docs/short-render-spec.md).

Depends only on Pillow (already a render dependency) — safe to import from
render_short.py under `uv run --with pillow`.
"""
from __future__ import annotations

import math

from PIL import ImageFont

# 中央寄せ字幕の最大幅 (docs/short-render-spec.md):
#   2 * min(540-60, 916-540) = 2 * min(480, 376) = 752
# 中心 x=540、右の safe zone 端 916 が最厳のため右に合わせた対称幅。
MAX_CENTERED_WIDTH = 752

# 尺の上限。3プラ最長 (Twitter 140 / Reels 90 / Shorts 60) にヘッドルーム。
# これを超える "duration" はジョブの取り違え/桁間違いとみなして弾く。
MAX_DURATION_S = 300.0

# 場所テロップ (primary/secondary) のフォント。render_short.py の
# FONT_BOLD/LOCATION_PRIMARY_FONT・FONT_LIGHT/LOCATION_SECONDARY_FONT と一致させる
# SSoT (test_render_short_hardening でドリフトを pin)。adapter の既定テロップ
# フィッティングと render_short の幅検証が同じ尺度を使うために共有する。
TELOP_PRIMARY_FONT = "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc"
TELOP_PRIMARY_SIZE = 84
TELOP_SECONDARY_FONT = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
TELOP_SECONDARY_SIZE = 34

# 浮動小数の丸め誤差で末尾がソースを 1ms 超える程度は許容する。
_CLIP_EPSILON_S = 1e-3


class ValidationError(ValueError):
    """A render input that would produce a broken/cropped short — fail closed."""


def _is_finite_number(v) -> bool:
    """A real, finite int/float (NOT bool, NOT NaN/Infinity). NaN slips past naive
    `< 0` / `<= 0` checks because every comparison with NaN is False, so it must be
    rejected explicitly."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def validate_clip_range(
    start_s: float, duration_s: float, source_duration_s: float | None = None
) -> None:
    """Raise ValidationError unless the [start, start+duration) window is sane and
    (when source_duration_s is given) fits inside the source."""
    if not _is_finite_number(start_s) or start_s < 0:
        raise ValidationError(f"start must be a finite number >= 0 (got {start_s!r})")
    if not _is_finite_number(duration_s) or duration_s <= 0:
        raise ValidationError(f"duration must be a finite number > 0 (got {duration_s!r})")
    if duration_s > MAX_DURATION_S:
        raise ValidationError(
            f"duration {duration_s}s exceeds max {MAX_DURATION_S}s "
            f"(likely a units/typo error)"
        )
    if source_duration_s is not None:
        if not _is_finite_number(source_duration_s) or source_duration_s <= 0:
            raise ValidationError(
                f"source duration must be a finite number > 0 (got {source_duration_s!r})"
            )
        if start_s >= source_duration_s:
            raise ValidationError(
                f"start {start_s}s is at/after source end {source_duration_s}s"
            )
        if start_s + duration_s > source_duration_s + _CLIP_EPSILON_S:
            raise ValidationError(
                f"clip end {start_s + duration_s:.3f}s exceeds source "
                f"{source_duration_s:.3f}s"
            )


def validate_cta_duration(cta_duration_s: float, clip_duration_s: float) -> None:
    """The CTA shows over the last `cta_duration_s` of the clip. Raise unless it is
    a finite positive number no longer than the clip itself."""
    if not _is_finite_number(cta_duration_s) or cta_duration_s <= 0:
        raise ValidationError(
            f"cta-duration must be a finite number > 0 (got {cta_duration_s!r})"
        )
    if cta_duration_s > clip_duration_s:
        raise ValidationError(
            f"cta-duration {cta_duration_s}s exceeds clip duration {clip_duration_s}s"
        )


def measure_text_width(text: str, font_path: str, font_size: int) -> float:
    """Rendered width in px of `text` at the given truetype font/size. Raises
    OSError (from Pillow) if the font can't be loaded — caller fails closed."""
    font = ImageFont.truetype(font_path, font_size)
    return font.getlength(text)


def validate_telop_width(
    text: str,
    font_path: str,
    font_size: int,
    *,
    label: str = "telop",
    max_width: int = MAX_CENTERED_WIDTH,
) -> float:
    """Raise ValidationError if the centered telop would cross the safe zone.
    Returns the measured width on success."""
    width = measure_text_width(text, font_path, font_size)
    if width > max_width:
        raise ValidationError(
            f"{label} {text!r} is {width:.0f}px wide; exceeds centered max "
            f"{max_width}px — it would cross the multi-platform safe zone. "
            f"Shorten it."
        )
    return width
