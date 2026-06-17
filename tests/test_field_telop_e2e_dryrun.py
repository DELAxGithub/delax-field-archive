"""Field Telop local dry-run E2E.

Exercises the full poller chain on a Web-shaped job + per-cue overlay + approved
passage_v1 manifest, WITHOUT running ffmpeg / render_passage_short / GitHub /
Dropbox:

    parse_job -> parse_overlay -> job<->overlay consistency -> job<->manifest
    match -> apply overlay -> overlay_sha (Python SSoT, wheel-gated) ->
    render command build -> proxy command build -> result JSON

Asserts the security invariants end to end: no source path in job/result/render
command, registry fail-closed, result records overlay_sha.

NOTE (real render, deferred): render_passage_short requires
`job.overlay_sha == overlay_sha(manifest_cue)` over the cue IN the manifest it is
given, AND an HMAC-approved manifest whose content_hash matches. The Web edit
changes the cue, so before a REAL render the edited manifest must be RE-APPROVED
(HMAC re-signed). Who/how re-approves is an open decision — the poller does NOT
re-sign here (it would otherwise weaken the approval gate). Dry-run builds the
command only; real render stays blocked until that is resolved + a real source is
registered.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from field_shorts import field_telop_queue_poller as P
from field_shorts.sources import SourceNotAllowed

OID = "20260617T123456Z-cue-001-ab12cd"
CONTENT_HASH = "a" * 64
PIH = "c" * 64
DESIGN_SHA = "d" * 64
BASE_SHA = "e" * 40


def _job() -> dict:
    return {
        "schema_version": 1, "job_kind": "field-telop-render", "job_id": OID,
        "episode_id": "DBT_EP003", "cue_id": "cue-001", "overlay_id": OID,
        "overlay_path": f"field-telop/overlays/DBT_EP003/cue-001/{OID}.json",
        "manifest_sha": BASE_SHA, "manifest_content_hash": CONTENT_HASH,
        "passage_info_hash": PIH, "preset": "video-passage-v1", "preset_version": 1,
        "design_sha": DESIGN_SHA, "requested_by": "h-kodera",
        "created_at": "2026-06-17T12:34:56.789Z", "status": "pending",
    }


def _overlay() -> dict:
    return {
        "schema_version": 1, "overlay_kind": "field-telop-cue-overlay", "overlay_id": OID,
        "episode_id": "DBT_EP003", "cue_id": "cue-001", "base_manifest_sha": BASE_SHA,
        "base_manifest_content_hash": CONTENT_HASH, "passage_info_hash": PIH,
        "place": "マラガ港", "info": "地中海の玄関口 再生した港の遊歩道",
        "start_s": 12, "end_s": 22, "review_note": "海側カット採用",
        "approval_reset_required": True, "updated_by": "h-kodera",
        "updated_at": "2026-06-17T12:34:56.789Z",
    }


def _manifest() -> dict:
    return {
        "project": {"episode_id": "DBT_EP003"},
        "approval": {"status": "approved", "content_hash": CONTENT_HASH},
        "passage_info_hash": PIH,
        "design": {"design_sha": DESIGN_SHA},
        "cues": [{"id": "cue-001", "start_s": 1.0, "end_s": 9.0, "place": "原文",
                  "info": "原文 info", "copy_horizontal": "原文", "copy_vertical": ["原文"]}],
    }


def _has_core() -> bool:
    try:
        import delax_core  # noqa: F401
        return True
    except Exception:
        return False


def test_dry_run_full_chain(tmp_path: Path):
    job = P.parse_job(_job())
    overlay = P.parse_overlay(_overlay())
    P.assert_job_overlay_consistent(job, overlay)
    P.assert_manifest_match(job, _manifest())
    applied = P.apply_overlay(_manifest(), overlay)
    assert applied["place"] == "マラガ港" and applied["info"].startswith("地中海")

    # overlay_sha: real Python SSoT if the wheel is present, else a placeholder so
    # the rest of the dry-run chain still runs (NOT a stubbed sha — the real-call
    # round-trip is asserted separately below when the wheel is available).
    overlay_sha = P.compute_overlay_sha(applied) if _has_core() else ("f" * 64)

    rp_job = P.build_render_passage_job(job, overlay_sha)
    assert rp_job["overlay_sha"] == overlay_sha and rp_job["cue_id"] == "cue-001"

    # render command points at the registry (source resolved by render_passage_short)
    render_cmd = P.build_render_command(
        tmp_path / "rp_job.json", tmp_path / "manifest.json", tmp_path / "registry.json",
        render_script=Path("/x/render_passage_short.py"))
    assert "--registry" in render_cmd and any("render_passage_short.py" in c for c in render_cmd)

    proxy_path = P.proxy_dropbox_path("DBT_EP003")
    assert proxy_path == "/DELAX_field/field-telop/proxies/DBT_EP003/source_proxy.mp4"
    # proxy_cmd legitimately contains the LOCAL source path — it is the local ffmpeg
    # invocation on the Mac and is NEVER transmitted (not in job/result/render cmd).
    source_local = "/Volumes/cam/edit.mp4"
    proxy_cmd = P.build_proxy_command(source_local, "/Users/x/Dropbox/DELAX_field/p.mp4")
    assert isinstance(proxy_cmd, list) and proxy_cmd
    assert any(source_local in c for c in proxy_cmd)  # local cmd carries the source (expected)

    result = P.build_result(job, overlay_sha, output_content_hash="9" * 64,
                            status="done", finished_at="2026-06-17T13:00:00Z")

    # security invariant: the TRANSMITTED artifacts (job / result / render command)
    # carry no source path and no absolute local path (the precise invariant, not a
    # brittle "source" substring check).
    for blob in (json.dumps(rp_job), json.dumps(result), " ".join(render_cmd)):
        assert source_local not in blob
        assert "/Volumes/" not in blob and "/Users/" not in blob
    assert result["overlay_sha"] == overlay_sha
    assert P.SHA_HEX.match(result["overlay_sha"])


def test_dry_run_registry_fail_closed(tmp_path: Path):
    reg = tmp_path / "sources.json"
    reg.write_text(json.dumps({"version": 1, "sources": {}}))  # empty → nothing registered
    with pytest.raises(SourceNotAllowed):
        P.assert_source_registered("DBT_EP003", reg)


@pytest.mark.skipif(not _has_core(),
                    reason="delax_core wheel not available; real overlay_sha round-trip needs it")
def test_dry_run_overlay_sha_is_render_passage_short_ssot():
    import sys
    scripts = Path(P.__file__).resolve().parent.parent
    sys.path.insert(0, str(scripts))
    import render_passage_short as R

    applied = P.apply_overlay(_manifest(), P.parse_overlay(_overlay()))
    assert P.compute_overlay_sha(applied) == R.overlay_sha(applied)
