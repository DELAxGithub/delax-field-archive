"""S3-C field adapter: place a reviewed passage_info onto the episode's measured GPS.

The Street View side maps each cue's ``route_progress_m`` onto a Street View sample;
here the same value is mapped onto the recorded telemetry, yielding ``start_s/end_s``
for the live-action (CapturedVideo) renderer. The reviewed cue body is reused VERBATIM
— no transform, no regeneration — so both renderers show the same copy and record the
same passage_info_hash. The mapping rules match the Street View adapter:

  - nearest cumulative distance (ties -> the earlier telemetry index)
  - a ``route_progress_m`` that is non-finite / negative / beyond the recorded route, or
    a non-monotonic telemetry clock, FAILS CLOSED (raises)
  - a progress deviation over half the median telemetry interval, a lat/lng more than
    150 m from the matched point, or more than one cue on the same telemetry row sends
    the cue(s) to review (never a silent drop / first-wins / merge)

Pure: no core wheel. Validation of the passage_info itself happens upstream (core).
"""
from __future__ import annotations

import math

from video_passage_pipeline import haversine_m

ASSIGN_MAX_DIST_M = 150.0


class PassageFieldError(Exception):
    """A passage_info -> telemetry mapping failure (structural or unmappable cue)."""


def _is_finite(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def _cumulative_m(telemetry: list) -> list:
    cums = [0.0]
    for i in range(1, len(telemetry)):
        cums.append(cums[-1] + haversine_m(telemetry[i - 1], telemetry[i]))
    return cums


def _median_interval(cums: list) -> float:
    gaps = sorted(cums[i] - cums[i - 1] for i in range(1, len(cums)))
    if not gaps:
        return 0.0
    mid = len(gaps) // 2
    return gaps[mid] if len(gaps) % 2 else (gaps[mid - 1] + gaps[mid]) / 2.0


def map_passage_info_to_cues(passage_info: dict, telemetry: list, *,
                             default_duration_s: float = 8.0,
                             video_duration_s: float | None = None) -> dict:
    """Map each reviewed cue onto a telemetry time. Returns
    ``{"assignments": [{"cue_id","start_s","end_s","cue"}], "review_required": [...]}``.
    Raises ``PassageFieldError`` on structural problems (see module docstring)."""
    if not telemetry:
        raise PassageFieldError("telemetry must be a non-empty sequence")
    for row in telemetry:
        if not (_is_finite(row.get("time_s")) and _is_finite(row.get("lat"))
                and _is_finite(row.get("lon"))):
            raise PassageFieldError("telemetry has a non-finite time_s / lat / lon")
    times = [row["time_s"] for row in telemetry]
    for i in range(1, len(times)):
        if times[i] < times[i - 1]:
            raise PassageFieldError("telemetry time_s must be non-decreasing")

    cums = _cumulative_m(telemetry)
    route_total = cums[-1]
    half_interval = _median_interval(cums) / 2.0

    review: list[dict] = []
    bucket: dict[int, list] = {}
    for cue in passage_info["cues"]:
        progress = cue["route_progress_m"]
        if not _is_finite(progress) or progress < 0.0 or progress > route_total + 1e-6:
            raise PassageFieldError(
                f"{cue['id']}: route_progress_m {progress!r} is non-finite or outside the "
                f"recorded route [0, {route_total}]")
        best_i, best_d = 0, abs(cums[0] - progress)
        for i in range(1, len(cums)):
            d = abs(cums[i] - progress)
            if d < best_d:        # strict < -> ties keep the earlier index
                best_i, best_d = i, d
        if best_d > half_interval:
            review.append({"cue_id": cue["id"],
                           "reason": f"progress deviation {best_d:.1f} m exceeds half the "
                                     f"telemetry interval {half_interval:.1f} m"})
            continue
        dist = haversine_m({"lat": cue["lat"], "lon": cue["lng"]}, telemetry[best_i])
        if dist > ASSIGN_MAX_DIST_M:
            review.append({"cue_id": cue["id"],
                           "reason": f"lat/lng {dist:.0f} m from telemetry point {best_i} "
                                     f"exceeds {ASSIGN_MAX_DIST_M:.0f} m"})
            continue
        bucket.setdefault(best_i, []).append(cue)

    assignments: list[dict] = []
    for index, cues_here in bucket.items():
        if len(cues_here) == 1:
            cue = cues_here[0]
            start_s = float(telemetry[index]["time_s"])
            end_s = start_s + default_duration_s
            if video_duration_s is not None:
                end_s = min(end_s, video_duration_s)
            assignments.append({"cue_id": cue["id"], "start_s": start_s,
                                "end_s": end_s, "cue": cue})
        else:
            for cue in cues_here:
                review.append({"cue_id": cue["id"],
                               "reason": f"{len(cues_here)} cues map to telemetry point "
                                         f"{index} (no first-wins or merge)"})
    assignments.sort(key=lambda a: (a["start_s"], a["cue_id"]))
    return {"assignments": assignments, "review_required": review}


def build_field_cues(passage_info: dict, telemetry: list, *,
                     default_duration_s: float = 8.0,
                     video_duration_s: float | None = None) -> list:
    """Produce video_passage review cues (start_s/end_s + the verbatim cue body) from a
    reviewed passage_info. Fails closed if any cue cannot be placed. Windows are clamped
    so they stay chronological and non-overlapping (the live-action review's invariant)."""
    result = map_passage_info_to_cues(passage_info, telemetry,
                                      default_duration_s=default_duration_s,
                                      video_duration_s=video_duration_s)
    if result["review_required"]:
        reasons = "; ".join(f"{r['cue_id']}: {r['reason']}"
                            for r in result["review_required"][:5])
        raise PassageFieldError(f"passage_info cues do not map to telemetry: {reasons}")

    assignments = result["assignments"]
    cues: list[dict] = []
    for i, assignment in enumerate(assignments):
        cue = assignment["cue"]
        info = cue["info"]
        end_s = assignment["end_s"]
        if i + 1 < len(assignments):            # no overlap with the next cue
            end_s = min(end_s, assignments[i + 1]["start_s"])
        cues.append({
            "id": cue["id"],
            "start_s": assignment["start_s"],
            "end_s": end_s,
            "place": cue["place"],
            "road": "",
            "eyebrow": info.get("eyebrow", ""),
            "copy_horizontal": info["copy_horizontal"],
            "copy_vertical": list(info["copy_vertical"]),
            "review_note": cue.get("review_note", ""),
        })
    return cues
