"""S3-C field adapter: map a reviewed passage_info onto the episode's measured GPS.

Same rules as the Street View adapter, but the target axis is the recorded telemetry
time (start_s/end_s), not a Street View sample. The reviewed cue body is reused
VERBATIM (no transform / regeneration). Pure — no core wheel needed.
"""
import json
import math
from pathlib import Path

import pytest

from passage_info_field import (
    ASSIGN_MAX_DIST_M,
    PassageFieldError,
    build_field_cues,
    map_passage_info_to_cues,
)


def _telemetry(n=12, dt=1.0, step_deg=0.00009):   # ~10 m/s along the equator-ish
    return [{"time_s": i * dt, "lat": 36.70 + i * step_deg, "lon": -4.40,
             "alt_m": None, "speed_kmh": 36.0} for i in range(n)]


def _cue(idx, rp, *, lat=None, lng=-4.40, place=None):
    lat = 36.70 + (rp / 10.0) * 0.00009 if lat is None else lat   # ~10 m of cum per 0.00009
    return {"id": f"cue-{idx:03d}", "lat": lat, "lng": lng, "route_progress_m": rp,
            "place": place or f"地点{idx}",
            "info": {"eyebrow": "EB", "copy_horizontal": f"地点{idx} の道",
                     "copy_vertical": [f"地点{idx}", "の道"]},
            "review_note": "ok", "used_evidence_ids": ["ev-001"], "status": "generated"}


def _pi(cues):
    return {"schema_version": 1, "kind": "passage-info", "cues": cues}


def test_clean_mapping_to_time():
    out = map_passage_info_to_cues(_pi([_cue(1, 10.0), _cue(2, 50.0)]), _telemetry())
    a = {x["cue_id"]: x for x in out["assignments"]}
    assert out["review_required"] == []
    assert a["cue-001"]["start_s"] == 1.0 and a["cue-002"]["start_s"] == 5.0


def test_tie_breaks_to_smaller_index():
    # rp=5 is equidistant from telemetry 0 (0 m) and 1 (10 m) -> index 0, time 0
    out = map_passage_info_to_cues(_pi([_cue(1, 5.0)]), _telemetry())
    assert out["assignments"][0]["start_s"] == 0.0


def test_half_interval_overshoot_to_review():
    # a sparse gap (cum 50 -> 150) strands a cue at rp=100; median interval ~10 m
    tel = _telemetry()
    for i in range(6, len(tel)):
        tel[i]["lat"] = 36.70 + (150 + (i - 6) * 10) / 10.0 * 0.00009
    out = map_passage_info_to_cues(_pi([_cue(1, 100.0)]), tel)
    assert out["assignments"] == []
    assert out["review_required"][0]["cue_id"] == "cue-001"


def test_latlng_mismatch_to_review():
    far = 36.70 + 0.003                       # ~330 m off the assigned telemetry point
    out = map_passage_info_to_cues(_pi([_cue(1, 10.0, lat=far)]), _telemetry())
    assert out["assignments"] == []
    assert out["review_required"] and ASSIGN_MAX_DIST_M == 150.0


def test_collision_all_review_no_first_wins():
    out = map_passage_info_to_cues(_pi([_cue(1, 10.0), _cue(2, 11.0)]), _telemetry())
    assert out["assignments"] == []
    assert {r["cue_id"] for r in out["review_required"]} == {"cue-001", "cue-002"}


def test_structural_failures_raise():
    with pytest.raises(PassageFieldError):
        map_passage_info_to_cues(_pi([_cue(1, 99999.0)]), _telemetry())   # out of route
    with pytest.raises(PassageFieldError):
        map_passage_info_to_cues(_pi([_cue(1, float("nan"))]), _telemetry())
    bad = _telemetry()
    bad[4]["time_s"] = 1.0                                                 # non-monotonic time
    with pytest.raises(PassageFieldError):
        map_passage_info_to_cues(_pi([_cue(1, 10.0)]), bad)


def test_build_field_cues_reuses_body_verbatim_and_no_overlap():
    cues = build_field_cues(_pi([_cue(1, 10.0), _cue(2, 50.0)]), _telemetry(),
                            default_duration_s=8.0)
    assert [c["id"] for c in cues] == ["cue-001", "cue-002"]
    # body is reused verbatim from passage_info (no transform)
    assert cues[0]["copy_horizontal"] == "地点1 の道"
    assert cues[0]["copy_vertical"] == ["地点1", "の道"]
    assert cues[0]["place"] == "地点1" and cues[0]["eyebrow"] == "EB"
    # windows are chronological and non-overlapping (clamped to the next cue's start)
    assert cues[0]["end_s"] <= cues[1]["start_s"]
    assert all(c["end_s"] > c["start_s"] for c in cues)


def test_build_field_cues_fails_closed_on_review():
    far = 36.70 + 0.003
    with pytest.raises(PassageFieldError):
        build_field_cues(_pi([_cue(1, 10.0, lat=far)]), _telemetry())


def test_video_duration_clamps_end():
    cues = build_field_cues(_pi([_cue(1, 100.0)]), _telemetry(), default_duration_s=8.0,
                            video_duration_s=12.0)
    assert cues[0]["end_s"] == 12.0    # start 10.0 + 8 -> 18, clamped to 12


# --- P1-2: wired into video_passage_pipeline (manifest consumes the common cue) ---

def _reviewed_pi():
    """A REAL reviewed passage_info built through core (correct info_hash). Requires the
    approved wheel — run the field suite via the wheel for the ingest tests."""
    from delax_core.passage_info import (apply_generation_result, passage_info_hash,
                                         transition_state)

    def _draft_cue(idx, rp):
        c = dict(_cue(idx, rp))
        c["status"] = "draft"
        c["info"] = {"eyebrow": "", "copy_horizontal": "", "copy_vertical": []}
        return c

    draft = {"schema_version": 1, "kind": "passage-info",
             "route": {"route_id": "DBT_EP_X", "city": "X", "country": "Y", "mode": "cycling"},
             "evidence": [{"id": "ev-001", "kind": "poi", "source_kind": "osm",
                           "lat": 36.70, "lng": -4.40, "content": "c"}],
             "cues": [_draft_cue(1, 10.0), _draft_cue(2, 50.0)],
             "generation_state": "draft", "info_hash": None, "provenance": None}
    result = {"base_info_hash": passage_info_hash(draft), "cues": [
        {"id": f"cue-{i:03d}", "status": "generated", "place": f"地点{i}",
         "info": {"eyebrow": "", "copy_horizontal": f"地点{i} の道",
                  "copy_vertical": [f"地点{i}", "の道"]},
         "used_evidence_ids": ["ev-001"]} for i in (1, 2)]}
    return transition_state(apply_generation_result(draft, result), "reviewed")


def _manifest():
    return {"schema_version": 1,
            "project": {"episode_id": "DBT_EP_X", "title": "T", "created_at": "2026-06-15T00:00:00Z"},
            "source": {"video": "/v.mp4", "duration_s": 60.0, "gps_csv": "/g.csv"},
            "design": {"preset": "video-passage-v1"},
            "telemetry": _telemetry(),
            "cues": [{"id": "cue-900", "start_s": 0.0, "end_s": 1.0, "place": "OLD",
                      "eyebrow": "", "copy_horizontal": "古い", "copy_vertical": ["古い"],
                      "review_note": ""}],
            "approval": {"status": "approved", "approved_at": "2026-06-15T00:00:00Z",
                         "approved_by": "x", "content_hash": "f" * 64},
            "outputs": {}}


def test_ingest_passage_replaces_cues_and_resets_approval(tmp_path):
    from video_passage_pipeline import build_parser
    pi = _reviewed_pi()
    m, p = tmp_path / "m.json", tmp_path / "pi.json"
    m.write_text(json.dumps(_manifest(), ensure_ascii=False))
    p.write_text(json.dumps(pi, ensure_ascii=False))
    args = build_parser().parse_args(
        ["ingest-passage", "--manifest", str(m), "--passage-info", str(p)])
    args.func(args)
    out = json.loads(m.read_text())
    # the live-action manifest now carries the SHARED reviewed cue body (verbatim)
    assert [c["id"] for c in out["cues"]] == ["cue-001", "cue-002"]
    assert out["cues"][0]["copy_horizontal"] == "地点1 の道"
    assert out["cues"][0]["copy_vertical"] == ["地点1", "の道"]
    assert all("start_s" in c and "end_s" in c for c in out["cues"])   # mapped to time
    assert out["passage_info_hash"] == pi["info_hash"]                  # cross-renderer key
    assert out["approval"]["status"] == "draft"                         # must re-review/approve


def test_ingest_passage_rejects_non_reviewed(tmp_path):
    from video_passage_pipeline import build_parser
    pi = _reviewed_pi()
    pi["generation_state"] = "generated"            # downgraded -> not reviewed
    m, p = tmp_path / "m.json", tmp_path / "pi.json"
    m.write_text(json.dumps(_manifest(), ensure_ascii=False))
    p.write_text(json.dumps(pi, ensure_ascii=False))
    args = build_parser().parse_args(
        ["ingest-passage", "--manifest", str(m), "--passage-info", str(p)])
    with pytest.raises(SystemExit):
        args.func(args)


def test_ingest_passage_rejects_tampered_hash(tmp_path):
    from video_passage_pipeline import build_parser
    pi = _reviewed_pi()
    pi["cues"][0]["place"] = "改ざん"               # body changed, info_hash now stale
    m, p = tmp_path / "m.json", tmp_path / "pi.json"
    m.write_text(json.dumps(_manifest(), ensure_ascii=False))
    p.write_text(json.dumps(pi, ensure_ascii=False))
    args = build_parser().parse_args(
        ["ingest-passage", "--manifest", str(m), "--passage-info", str(p)])
    with pytest.raises(SystemExit):                 # recomputed hash != recorded -> reject
        args.func(args)
