"""Field Telop poller — dry-run / mock tests.

Pure tests (parse / validate / consistency / apply / command + path build /
result / registry fail-closed) run WITHOUT delax_core. The overlay_sha SSoT test
needs the delax_core wheel (render_passage_short hard-imports it) and is SKIPPED
otherwise — never stubbed, and the poller never gets its own overlay_sha impl.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from field_shorts import field_telop_queue_poller as P
from field_shorts.field_telop_queue_poller import PollerError
from field_shorts.sources import SourceNotAllowed

OID = "20260617T123456Z-cue-001-ab12cd"
H64 = "a" * 64
H40 = "b" * 40


def _job() -> dict:
    return {
        "schema_version": 1,
        "job_kind": "field-telop-render",
        "job_id": OID,
        "episode_id": "DBT_EP003",
        "cue_id": "cue-001",
        "overlay_id": OID,
        "overlay_path": f"field-telop/overlays/DBT_EP003/cue-001/{OID}.json",
        "manifest_sha": H40,
        "manifest_content_hash": H64,
        "passage_info_hash": "c" * 64,
        "preset": "video-passage-v1",
        "preset_version": 1,
        "design_sha": "d" * 64,
        "requested_by": "h-kodera",
        "created_at": "2026-06-17T12:34:56.789Z",
        "status": "pending",
    }


def _overlay() -> dict:
    return {
        "schema_version": 1,
        "overlay_kind": "field-telop-cue-overlay",
        "overlay_id": OID,
        "episode_id": "DBT_EP003",
        "cue_id": "cue-001",
        "base_manifest_sha": H40,
        "base_manifest_content_hash": H64,
        "passage_info_hash": "c" * 64,
        "place": "マラガ港",
        "info": "地中海の玄関口 再生した港の遊歩道",
        "start_s": 12,
        "end_s": 22,
        "review_note": "",
        "approval_reset_required": True,
        "updated_by": "h-kodera",
        "updated_at": "2026-06-17T12:34:56.789Z",
    }


def _manifest() -> dict:
    return {
        "project": {"episode_id": "DBT_EP003"},
        "approval": {"status": "approved", "content_hash": H64},
        "passage_info_hash": "c" * 64,
        "design": {"design_sha": "d" * 64},
        "cues": [{"id": "cue-001", "start_s": 1.0, "end_s": 9.0, "place": "orig",
                  "info": "orig info", "copy_horizontal": "x", "copy_vertical": ["x"]}],
    }


# ── parse / validate ──────────────────────────────────────────────────────
def test_parse_job_ok():
    assert P.parse_job(_job())["job_id"] == OID


def test_parse_job_rejects_overlay_sha_and_bad_ids():
    assert P.parse_job(_job())  # sanity
    with pytest.raises(PollerError, match="overlay_sha"):
        P.parse_job({**_job(), "overlay_sha": H64})
    with pytest.raises(PollerError):
        P.parse_job({**_job(), "job_id": "../../x"})
    with pytest.raises(PollerError):
        P.parse_job({**_job(), "manifest_content_hash": "nothex"})
    with pytest.raises(PollerError, match="job_id must equal overlay_id"):
        P.parse_job({**_job(), "overlay_id": "20260617T123456Z-cue-002-zzzz99"})


def test_parse_overlay_ok_and_rejects():
    assert P.parse_overlay(_overlay())["overlay_id"] == OID
    with pytest.raises(PollerError, match="info is empty"):
        P.parse_overlay({**_overlay(), "info": "   "})
    with pytest.raises(PollerError, match="end_s"):
        P.parse_overlay({**_overlay(), "start_s": 22, "end_s": 12})


# ── P1: strict key allow-list (fail-closed on unknown keys) ────────────────
def test_parse_job_rejects_unknown_keys():
    with pytest.raises(PollerError, match="source"):
        P.parse_job({**_job(), "source": "/Volumes/x.mov"})
    with pytest.raises(PollerError, match="overlay_sha"):
        P.parse_job({**_job(), "overlay_sha": H64})
    with pytest.raises(PollerError, match="extra"):
        P.parse_job({**_job(), "extra": 1})


def test_parse_job_rejects_missing_keys():
    j = _job()
    del j["design_sha"]
    with pytest.raises(PollerError, match="missing"):
        P.parse_job(j)


def test_parse_overlay_rejects_unknown_keys():
    with pytest.raises(PollerError, match="source"):
        P.parse_overlay({**_overlay(), "source": "/Volumes/x.mov"})
    with pytest.raises(PollerError, match="overlay_sha"):
        P.parse_overlay({**_overlay(), "overlay_sha": H64})
    with pytest.raises(PollerError, match="copy_horizontal"):
        P.parse_overlay({**_overlay(), "copy_horizontal": "x"})
    with pytest.raises(PollerError, match="copy_vertical"):
        P.parse_overlay({**_overlay(), "copy_vertical": ["x"]})


# ── P2: start_s / end_s numeric hardening (bool / NaN / Inf / negative) ────
def test_parse_overlay_rejects_bad_numbers():
    with pytest.raises(PollerError, match="start_s"):
        P.parse_overlay({**_overlay(), "start_s": True})
    with pytest.raises(PollerError, match="start_s"):
        P.parse_overlay({**_overlay(), "start_s": float("nan")})
    with pytest.raises(PollerError, match="end_s"):
        P.parse_overlay({**_overlay(), "end_s": float("inf")})
    with pytest.raises(PollerError, match="start_s"):
        P.parse_overlay({**_overlay(), "start_s": -1})


# ── consistency / manifest match ──────────────────────────────────────────
def test_job_overlay_consistency():
    P.assert_job_overlay_consistent(_job(), _overlay())  # ok
    with pytest.raises(PollerError, match="overlay_path mismatch"):
        bad = _job(); bad["overlay_path"] = "field-telop/overlays/OTHER/cue-001/" + OID + ".json"
        P.assert_job_overlay_consistent(bad, _overlay())
    with pytest.raises(PollerError, match="cue_id mismatch"):
        P.assert_job_overlay_consistent(_job(), {**_overlay(), "cue_id": "cue-002"})


def test_manifest_match():
    P.assert_manifest_match(_job(), _manifest())  # ok
    with pytest.raises(PollerError, match="stale"):
        m = _manifest(); m["approval"]["content_hash"] = "f" * 64
        P.assert_manifest_match(_job(), m)
    with pytest.raises(PollerError, match="not approved"):
        m = _manifest(); m["approval"]["status"] = "draft"
        P.assert_manifest_match(_job(), m)
    with pytest.raises(PollerError, match="passage_info_hash"):
        m = _manifest(); m["passage_info_hash"] = "e" * 64
        P.assert_manifest_match(_job(), m)
    with pytest.raises(PollerError, match="design_sha"):
        m = _manifest(); m["design"]["design_sha"] = "e" * 64
        P.assert_manifest_match(_job(), m)


# ── apply / build ──────────────────────────────────────────────────────────
def test_apply_overlay_reflects_edits():
    applied = P.apply_overlay(_manifest(), _overlay())
    assert applied["place"] == "マラガ港"
    assert applied["info"] == "地中海の玄関口 再生した港の遊歩道"
    assert applied["start_s"] == 12 and applied["end_s"] == 22
    # read-only copy_* untouched (sourced from the manifest)
    assert applied["copy_horizontal"] == "x"
    with pytest.raises(PollerError, match="not found in manifest"):
        P.apply_overlay(_manifest(), {**_overlay(), "cue_id": "cue-999"})


def test_build_render_passage_job_has_overlay_sha_no_source():
    rp = P.build_render_passage_job(_job(), H64)
    assert rp["overlay_sha"] == H64
    assert rp["episode_id"] == "DBT_EP003" and rp["cue_id"] == "cue-001"
    assert rp["preset"] == "video-passage-v1"
    assert "source" not in json.dumps(rp) and "/Volumes/" not in json.dumps(rp)
    with pytest.raises(PollerError):
        P.build_render_passage_job(_job(), "nothex")


def test_build_render_command_has_no_source_path():
    cmd = P.build_render_command("/tmp/rpjob.json", "/tmp/m.json", "/tmp/reg.json",
                                 render_script=Path("/x/render_passage_short.py"))
    assert "--job" in cmd and "--manifest" in cmd and "--registry" in cmd
    assert any("render_passage_short.py" in c for c in cmd)
    # the source absolute path is resolved by render_passage_short via the registry,
    # never placed in the command
    assert not any("/Volumes/" in c or "edit_master" in c for c in cmd)


def test_proxy_dropbox_path():
    assert P.proxy_dropbox_path("DBT_EP003") == \
        "/DELAX_field/field-telop/proxies/DBT_EP003/source_proxy.mp4"
    with pytest.raises(PollerError, match="unsafe episode_id"):
        P.proxy_dropbox_path("../etc")


def test_episode_id_must_match_core_schema():
    # episode_id must be ^[A-Z0-9_]+$ (matches delax_core manifest schema) so a
    # queue-accepted id is also a valid passage_v1 project.episode_id.
    assert P.EPISODE_ID.match("DWT_EP002") and P.EPISODE_ID.match("TEST_MARSEILLE2")
    for bad in ("TEST_marseille2_2026-04-02", "dwt_ep002", "EP-01", "a/b"):
        assert not P.EPISODE_ID.match(bad)
    # rejected at queue time (parse_job), not only at manifest-approve time
    with pytest.raises(PollerError):
        P.parse_job({**_job(), "episode_id": "TEST_marseille2_2026-04-02"})
    with pytest.raises(PollerError, match="unsafe episode_id"):
        P.proxy_dropbox_path("test-marseille2")


def test_build_proxy_command_reuses_ffmpeg_builder():
    cmd = P.build_proxy_command("/Volumes/x/edit.mp4", "/Users/d/Dropbox/DELAX_field/x.mp4")
    assert isinstance(cmd, list) and cmd
    assert any("/Users/d/Dropbox/DELAX_field/x.mp4" in c for c in cmd)


def test_build_result_no_source_path():
    r = P.build_result(_job(), H64, output_content_hash="9" * 64, status="done",
                       finished_at="2026-06-17T13:00:00Z")
    assert r["overlay_sha"] == H64 and r["status"] == "done"
    assert r["job_id"] == OID
    assert "source" not in json.dumps(r) and "/Volumes/" not in json.dumps(r)
    with pytest.raises(PollerError):
        P.build_result(_job(), H64, output_content_hash="9" * 64, status="pending",
                       finished_at="x")


# ── registry fail-closed ───────────────────────────────────────────────────
def test_assert_source_registered(tmp_path: Path):
    src = tmp_path / "edit.mp4"
    src.write_bytes(b"video")
    reg = tmp_path / "sources.json"
    reg.write_text(json.dumps({"version": 1, "sources": {"DBT_EP003": str(src)}}))
    assert P.assert_source_registered("DBT_EP003", reg) == src
    with pytest.raises(SourceNotAllowed):
        P.assert_source_registered("UNREGISTERED", reg)


# ── overlay_sha SSoT (needs delax_core wheel) ──────────────────────────────
def _has_core() -> bool:
    try:
        import delax_core  # noqa: F401
        return True
    except Exception:
        return False


def test_poller_has_no_own_overlay_sha_impl():
    """SSoT guard: the poller must not re-implement overlay_sha (no hashlib / no
    local def). It delegates to render_passage_short.overlay_sha (lazy import)."""
    src = Path(P.__file__).read_text(encoding="utf-8")
    assert "import hashlib" not in src
    assert "def overlay_sha" not in src
    assert "from render_passage_short import overlay_sha" in src


@pytest.mark.skipif(not _has_core(),
                    reason="delax_core wheel not available; overlay_sha SSoT needs it (NOT stubbed)")
def test_compute_overlay_sha_matches_render_passage_short():
    import sys
    scripts = Path(P.__file__).resolve().parent.parent
    sys.path.insert(0, str(scripts))
    import render_passage_short as R

    applied = P.apply_overlay(_manifest(), _overlay())
    got = P.compute_overlay_sha(applied)
    assert got == R.overlay_sha(applied)
    assert P.SHA_HEX.match(got)
