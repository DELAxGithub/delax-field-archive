"""Field Telop approve CLI tests.

Pure tests (sanitize / edited manifest / build approved job / no-local-path /
approved-job parsing / render-eligibility / secret-missing) run WITHOUT the
delax_core wheel. The full HMAC re-approval (passage_v1.approve_passage_manifest
+ verify + overlay_sha SSoT) is wheel-gated (skipif), never stubbed.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from field_shorts import field_telop_queue_poller as poller
from field_shorts import field_telop_approve as A
from field_shorts.field_telop_approve import ApproveError

OID = "20260617T123456Z-cue-001-ab12cd"
H64 = "a" * 64
PIH = "c" * 64
DESIGN_SHA = "d" * 64
BASE_SHA = "e" * 40


def _job() -> dict:
    return {
        "schema_version": 1, "job_kind": "field-telop-render", "job_id": OID,
        "episode_id": "DBT_EP003", "cue_id": "cue-001", "overlay_id": OID,
        "overlay_path": f"field-telop/overlays/DBT_EP003/cue-001/{OID}.json",
        "manifest_sha": BASE_SHA, "manifest_content_hash": H64, "passage_info_hash": PIH,
        "preset": "video-passage-v1", "preset_version": 1, "design_sha": DESIGN_SHA,
        "requested_by": "h-kodera", "created_at": "2026-06-17T12:34:56.789Z", "status": "pending",
    }


def _overlay() -> dict:
    return {
        "schema_version": 1, "overlay_kind": "field-telop-cue-overlay", "overlay_id": OID,
        "episode_id": "DBT_EP003", "cue_id": "cue-001", "base_manifest_sha": BASE_SHA,
        "base_manifest_content_hash": H64, "passage_info_hash": PIH,
        "place": "マラガ港", "info": "地中海の玄関口 再生した港の遊歩道",
        "start_s": 12, "end_s": 22, "review_note": "", "approval_reset_required": True,
        "updated_by": "h-kodera", "updated_at": "2026-06-17T12:34:56.789Z",
    }


def _base_manifest(source_video: str = "/Volumes/cam/DBT_EP003/edit.mp4") -> dict:
    return {
        "schema_version": 1,
        "project": {"episode_id": "DBT_EP003", "title": "t", "location_label": "Málaga",
                    "created_at": "2026-06-18T00:00:00+00:00"},
        "source": {"video": source_video, "duration_s": 600.0, "gps_csv": "/Volumes/cam/gps.csv"},
        "design": {"preset": "video-passage-v1", "preset_version": 1, "design_sha": DESIGN_SHA,
                   "journey": {}, "horizontal": {"width": 3840, "height": 2160},
                   "vertical": {"width": 1080, "height": 1920}, "font_jp": "x", "font_en": "y",
                   "show_place": True, "show_road": False, "show_route": True,
                   "show_speed": False, "show_heart_rate": False},
        "telemetry": [{"time_s": 0.0, "lat": 36.72, "lon": -4.42, "alt_m": 5, "speed_kmh": 12.0}],
        "passage_info_hash": PIH,
        "cues": [{"id": "cue-001", "start_s": 1.0, "end_s": 9.0, "place": "原文", "info": "原文",
                  "copy_horizontal": "原文", "copy_vertical": ["原文"]}],
        "outputs": {},
        "approval": {"status": "approved", "approved_at": "2026-06-17T00:00:00+00:00",
                     "approved_by": "x", "content_hash": H64, "signature": "0" * 64},
    }


# ── pure: source sanitize / edited manifest ────────────────────────────────
def test_sanitize_source_registry_only():
    s = A.sanitize_source({"video": "/Volumes/cam/x.mp4", "duration_s": 600.0,
                           "gps_csv": "/Volumes/cam/g.csv", "gpx": "/Volumes/cam/r.gpx"}, "DBT_EP003")
    assert s == {"video": "registry://DBT_EP003", "duration_s": 600.0, "gps_csv": "registry://DBT_EP003"}
    assert "/Volumes/" not in json.dumps(s)


def test_edited_manifest_applies_edit_resets_approval_sanitizes_source():
    base = _base_manifest()
    em = A.edited_manifest(base, _overlay(), "DBT_EP003")
    cue = em["cues"][0]
    assert cue["place"] == "マラガ港" and cue["info"].startswith("地中海")
    assert cue["start_s"] == 12 and cue["end_s"] == 22
    assert em["approval"]["status"] == "draft" and em["approval"]["content_hash"] is None
    assert em["source"]["video"] == "registry://DBT_EP003"
    assert "/Volumes/" not in json.dumps(em, ensure_ascii=False)
    # base not mutated
    assert base["source"]["video"] == "/Volumes/cam/DBT_EP003/edit.mp4"
    assert base["cues"][0]["place"] == "原文"


# ── pure: approved job build + parse + eligibility ─────────────────────────
def test_build_and_parse_approved_job():
    job = A.build_approved_job(_job(), overlay_sha=H64, new_content_hash="b" * 64,
                               approved_by="h-kodera", approved_at="2026-06-18T00:00:00Z")
    assert job["status"] == "approved-ready" and job["overlay_sha"] == H64
    assert job["manifest_content_hash"] == "b" * 64
    parsed = poller.parse_approved_job(job)  # round-trips
    assert parsed["job_id"] == OID
    assert poller.is_render_eligible(job) is True


def test_parse_approved_job_rejects():
    good = A.build_approved_job(_job(), overlay_sha=H64, new_content_hash="b" * 64,
                                approved_by="h-kodera", approved_at="2026-06-18T00:00:00Z")
    with pytest.raises(poller.PollerError):  # pending job (no overlay_sha) is not an approved job
        poller.parse_approved_job(_job())
    with pytest.raises(poller.PollerError):  # wrong status
        poller.parse_approved_job({**good, "status": "pending"})
    with pytest.raises(poller.PollerError):  # unknown key
        poller.parse_approved_job({**good, "source": "/Volumes/x"})


def test_pending_job_not_render_eligible():
    assert poller.is_render_eligible(_job()) is False


# ── pure: no-local-path guard + secret fail-closed ─────────────────────────
def test_assert_no_local_path():
    A._assert_no_local_path({"source": {"video": "registry://DBT_EP003"}}, "ok")  # passes
    for bad in ("/Volumes/x.mp4", "/Users/d/x", "/tmp/x"):
        with pytest.raises(ApproveError):
            A._assert_no_local_path({"v": bad}, "bad")


def test_assert_registry_source_allowlist():
    A._assert_registry_source({"source": {"video": "registry://EP", "gps_csv": "registry://EP"}}, "ok")
    # allowlist catches non-registry sources the denylist would miss (/mnt, /home, C:\, file://)
    for bad in ("/mnt/x.mp4", "/home/d/x.mp4", "C:\\x.mp4", "file:///x.mp4", "s3://b/x", ""):
        with pytest.raises(ApproveError):
            A._assert_registry_source({"source": {"video": bad, "gps_csv": "registry://EP"}}, "bad")


def test_approve_overlay_requires_secret(monkeypatch):
    monkeypatch.delenv("DELAX_HMAC_SECRET", raising=False)
    with pytest.raises(ApproveError, match="DELAX_HMAC_SECRET"):
        A.approve_overlay(_job(), _overlay(), _base_manifest(), approved_by="h-kodera", secret_key=None)


# ── wheel-gated: full HMAC re-approval (SSoT, not stubbed) ─────────────────
def _has_core() -> bool:
    try:
        import delax_core  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _has_core(), reason="delax_core wheel not available; HMAC re-approval needs it")
def test_full_approve_overlay_round_trip():
    import sys
    scripts = Path(poller.__file__).resolve().parent.parent
    sys.path.insert(0, str(scripts))
    from delax_core.design import passage_v1
    from delax_core import review as core_review
    import render_passage_short as R

    KEY = "phase6-test-secret"
    # CRITICAL PATH: base carries an ABSOLUTE source path. The flow must sanitize it
    # to registry:// before the approved (GitHub-bound) manifest exists.
    base = _base_manifest(source_video="/Volumes/cam/DBT_EP003/edit.mp4")
    base["source"]["gps_csv"] = "/Volumes/cam/gps.csv"
    base["design"]["design_sha"] = passage_v1.design_sha()
    base["approval"] = {"status": "draft", "approved_at": None, "approved_by": None, "content_hash": None}
    base = passage_v1.approve_passage_manifest(base, "seed", secret_key=KEY)
    assert "/Volumes/" in json.dumps(base)  # base genuinely has the absolute path

    job = _job()
    job["design_sha"] = passage_v1.design_sha()
    job["manifest_content_hash"] = base["approval"]["content_hash"]

    approved, approved_job = A.approve_overlay(job, _overlay(), base, approved_by="h-kodera", secret_key=KEY)

    assert core_review.verify_approval(approved, secret_key=KEY)
    # absolute source sanitized away → registry:// in the approved manifest
    assert approved["source"]["video"] == "registry://DBT_EP003"
    assert approved["source"]["gps_csv"] == "registry://DBT_EP003"
    assert approved_job["status"] == "approved-ready"
    assert approved_job["manifest_content_hash"] == approved["approval"]["content_hash"]
    # overlay_sha is the render_passage_short SSoT over the APPROVED cue
    cue = next(c for c in approved["cues"] if c["id"] == "cue-001")
    assert approved_job["overlay_sha"] == R.overlay_sha(cue)
    # render_passage_short would accept it: its overlay_sha(manifest cue) == job pin
    assert R.overlay_sha(cue) == approved_job["overlay_sha"]
    assert "/Volumes/" not in json.dumps(approved, ensure_ascii=False)
    assert poller.is_render_eligible(approved_job)
