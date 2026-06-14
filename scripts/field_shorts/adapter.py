"""field adapter — read `episodes/{ID}/episode.yaml` into a normalized model the
Web editor and the Mac-side poller both consume.

MVP scope (D2, handover 2026-06-14): the editable unit is a single
`creative.highlight_moments[]` entry → one place/info telop pair + an IN/OUT
window. episode.yaml carries no place/info, so the adapter DERIVES a sensible
default from `geo` (the nearest preceding landmark for the place, City · Country ·
date for the info, NHK ふれあい街歩き grammar). The Web overlay (Slice 2) overrides
these; `render_args()` is where an override is applied on the way to render_short.py.

Fail-closed: a missing episode.yaml, an id that disagrees with the directory, or a
non-mapping document raises FieldEpisodeError.

Imports PyYAML — do NOT import this from render_short.py's hot path (keep the
`uv run --with pillow` render free of the yaml dependency).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .paths import safe_path_component
from .validation import (
    MAX_CENTERED_WIDTH,
    TELOP_PRIMARY_FONT,
    TELOP_PRIMARY_SIZE,
    measure_text_width,
)

SERIES_LABELS = {"DWT": "DELAX Walking Tour", "DBT": "DELAX Bike Tour"}
_EP_NUM_RE = re.compile(r"_EP(\d+)", re.IGNORECASE)


class FieldEpisodeError(Exception):
    """episode.yaml is absent, malformed, or disagrees with the requested id."""


@dataclass(frozen=True)
class HighlightMoment:
    index: int
    description: str
    timestamp_sec: float | None   # default IN; None = 未編集 (render 前に要設定)
    duration_sec: float | None    # default window length; None = 未編集
    suggested_platform: str
    default_place: str         # primary telop, geo-derived; editor overrides
    default_info: str          # secondary telop, geo-derived; editor overrides


@dataclass(frozen=True)
class FieldEpisode:
    id: str
    series: str
    status: str
    series_label: str
    ep_chip: str
    shot_date: str
    city: str
    country: str
    location_name: str
    landmarks: tuple           # tuple[(timestamp_sec: float, name: str), ...]
    highlights: tuple          # tuple[HighlightMoment, ...]

    def render_args(
        self,
        highlight: HighlightMoment,
        *,
        place: str | None = None,
        info: str | None = None,
        start: float | None = None,
        duration: float | None = None,
    ) -> dict:
        """Map a highlight (+ optional Web-overlay overrides) to render_short.py
        keyword args. The poller passes the result straight through to the CLI.
        start/duration stay None when neither the overlay nor the episode set them
        — render_short's validation then refuses rather than rendering 0s."""
        s = start if start is not None else highlight.timestamp_sec
        d = duration if duration is not None else highlight.duration_sec
        return {
            "episode_id": self.id,
            "series_label": self.series_label,
            "ep_chip": self.ep_chip,
            "start": float(s) if s is not None else None,
            "duration": float(d) if d is not None else None,
            "location_primary": place if place is not None else highlight.default_place,
            "location_secondary": info if info is not None else highlight.default_info,
        }


def episode_yaml_path(episodes_dir: str | Path, episode_id: str) -> Path:
    safe = safe_path_component(episode_id, label="episode_id")
    return Path(episodes_dir) / safe / "episode.yaml"


def _series_label(series: str) -> str:
    return SERIES_LABELS.get(str(series).upper(), "DELAX Field Tour")


def ep_chip(episode_id: str) -> str:
    """Top-right chip text. `DWT_EP002` → `EP002`; otherwise the first
    underscore token uppercased (`TEST_malaga-…` → `TEST`)."""
    m = _EP_NUM_RE.search(episode_id)
    if m:
        return f"EP{m.group(1)}"
    return episode_id.split("_", 1)[0].upper()


def format_capture_date(shot_date: str) -> str:
    """`2026-05-04` → `2026.05.04`; anything unparseable → '' (telop omits it)."""
    if not isinstance(shot_date, str):
        return ""
    m = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", shot_date)
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else ""


def compose_info(city: str, country: str, shot_date: str) -> str:
    """Secondary telop: `City · Country · YYYY.MM.DD`, skipping empties."""
    parts = [p for p in (city, country, format_capture_date(shot_date)) if p]
    return " · ".join(parts)


def nearest_landmark(landmarks: tuple, t: float) -> str | None:
    """Name of the last landmark at/at-before time `t`; if none precede, the first
    landmark; None if there are no landmarks."""
    if not landmarks:
        return None
    preceding = [name for (ts, name) in landmarks if ts <= t]
    if preceding:
        return preceding[-1]
    return landmarks[0][1]


def _place_candidates(landmarks: tuple, location_name: str, city: str,
                      t: float) -> list[str]:
    """Place-name candidates, most specific first: nearest landmark → location_name
    head ('A → B, City' → 'A') → city."""
    out: list[str] = []
    lm = nearest_landmark(landmarks, t)
    if lm:
        out.append(lm)
    if location_name:
        head = re.split(r"[→,]", location_name)[0].strip()
        if head:
            out.append(head)
    if city:
        out.append(city)
    return out


def _default_place(landmarks: tuple, location_name: str, city: str, t: float) -> str:
    """First candidate that fits the centered telop max width (752px); if none fit,
    the narrowest. Stops a long landmark like 'Calle Bolivia / Baños del Carmen'
    (~1528px) from being saved as a default that can't render — it falls back to
    'Baños del Carmen' / 'Málaga'."""
    candidates = _place_candidates(landmarks, location_name, city, t)
    if not candidates:
        return ""
    measured = [
        (measure_text_width(c, TELOP_PRIMARY_FONT, TELOP_PRIMARY_SIZE), c)
        for c in candidates
    ]
    for width, name in measured:
        if width <= MAX_CENTERED_WIDTH:
            return name
    return min(measured, key=lambda wc: wc[0])[1]  # どれも収まらなければ最も狭いもの


def _parse_landmarks(raw) -> tuple:
    out = []
    if isinstance(raw, list):
        for lm in raw:
            if not isinstance(lm, dict):
                continue
            name = lm.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            ts = lm.get("timestamp_sec", 0)
            try:
                ts = float(ts)
            except (TypeError, ValueError):
                ts = 0.0
            out.append((ts, name.strip()))
    out.sort(key=lambda x: x[0])
    return tuple(out)


def _parse_optional_number(value, *, field: str, idx: int) -> float | None:
    """None/absent → None (unedited placeholder). A present finite int/float →
    float. Anything else (string, bool, NaN, Infinity) → FieldEpisodeError — a
    malformed value is never silently coerced to 0.0 and rendered as the opening."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FieldEpisodeError(
            f"highlight[{idx}].{field} must be a number or absent (got {value!r})"
        )
    if not math.isfinite(value):
        raise FieldEpisodeError(
            f"highlight[{idx}].{field} is not finite (got {value!r})"
        )
    return float(value)


def _parse_highlights(raw, landmarks: tuple, location_name: str,
                      city: str, country: str, shot_date: str) -> tuple:
    info = compose_info(city, country, shot_date)
    out = []
    if isinstance(raw, list):
        for i, hm in enumerate(raw):
            if not isinstance(hm, dict):
                raise FieldEpisodeError(f"highlight[{i}] is not a mapping: {hm!r}")
            ts = _parse_optional_number(hm.get("timestamp_sec"), field="timestamp_sec", idx=i)
            dur = _parse_optional_number(hm.get("duration_sec"), field="duration_sec", idx=i)
            platform = hm.get("suggested_platform")
            platform = platform if isinstance(platform, str) else ""
            # 既定 place は IN(=ts) 位置の地名。ts 未設定なら冒頭(0)で代表させる。
            place_t = ts if ts is not None else 0.0
            out.append(
                HighlightMoment(
                    index=i,
                    description=str(hm.get("description", "")),
                    timestamp_sec=ts,
                    duration_sec=dur,
                    suggested_platform=platform,
                    default_place=_default_place(landmarks, location_name, city, place_t),
                    default_info=info,
                )
            )
    return tuple(out)


def load_episode(episodes_dir: str | Path, episode_id: str) -> FieldEpisode:
    """Load + normalize one episode. Raises FieldEpisodeError (fail closed) on a
    missing/malformed file or an id that disagrees with the requested id."""
    path = episode_yaml_path(episodes_dir, episode_id)
    if not path.exists():
        raise FieldEpisodeError(f"episode.yaml not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise FieldEpisodeError(f"episode.yaml malformed ({path}): {e}") from e
    if not isinstance(data, dict):
        raise FieldEpisodeError(f"episode.yaml is not a mapping: {path}")

    yid = data.get("id")
    if str(yid) != str(episode_id):
        raise FieldEpisodeError(
            f"episode id mismatch: yaml id={yid!r}, requested={episode_id!r}"
        )

    series = str(data.get("series", ""))
    geo = data.get("geo") or {}
    capture = data.get("capture") or {}
    creative = data.get("creative") or {}
    if not isinstance(geo, dict):
        geo = {}
    if not isinstance(capture, dict):
        capture = {}
    if not isinstance(creative, dict):
        creative = {}

    landmarks = _parse_landmarks(geo.get("landmarks"))
    location_name = str(geo.get("location_name", ""))
    city = str(geo.get("city", ""))
    country = str(geo.get("country", ""))
    shot_date = str(capture.get("shot_date", ""))

    highlights = _parse_highlights(
        creative.get("highlight_moments"),
        landmarks, location_name, city, country, shot_date,
    )

    return FieldEpisode(
        id=str(episode_id),
        series=series,
        status=str(data.get("status", "")),
        series_label=_series_label(series),
        ep_chip=ep_chip(episode_id),
        shot_date=shot_date,
        city=city,
        country=country,
        location_name=location_name,
        landmarks=landmarks,
        highlights=highlights,
    )
