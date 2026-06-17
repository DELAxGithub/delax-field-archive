"""Field Telop runner — dry-run / execute with a FakeQueueClient + injected
render/proxy fns (no real gh, no subprocess, no ffmpeg)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from field_shorts import field_telop_queue as q
from field_shorts import field_telop_runner as runner
from field_shorts.sources import SourceNotAllowed

OID = "20260617T123456Z-cue-001-ab12cd"
H64 = "a" * 64
PIH = "c" * 64
DESIGN_SHA = "d" * 64
OVERLAY_SHA = "f" * 64


def _approved_job() -> dict:
    return {
        "schema_version": 1, "job_kind": "field-telop-render", "job_id": OID,
        "episode_id": "DBT_EP003", "cue_id": "cue-001", "overlay_id": OID,
        "overlay_path": f"field-telop/overlays/DBT_EP003/cue-001/{OID}.json",
        "manifest_sha": "e" * 40, "manifest_content_hash": H64, "passage_info_hash": PIH,
        "preset": "video-passage-v1", "preset_version": 1, "design_sha": DESIGN_SHA,
        "requested_by": "h-kodera", "created_at": "2026-06-17T12:34:56.789Z",
        "status": "approved-ready", "overlay_sha": OVERLAY_SHA,
        "approved_by": "h-kodera", "approved_at": "2026-06-18T00:00:00+00:00",
    }


def _approved_manifest() -> dict:
    return {
        "project": {"episode_id": "DBT_EP003"},
        "approval": {"status": "approved", "content_hash": H64, "signature": "0" * 64},
        "passage_info_hash": PIH, "design": {"design_sha": DESIGN_SHA},
        "source": {"video": "registry://DBT_EP003", "duration_s": 600.0, "gps_csv": "registry://DBT_EP003"},
        "cues": [{"id": "cue-001", "start_s": 12.0, "end_s": 22.0, "place": "マラガ港", "info": "info"}],
    }


def _client_with_job() -> q.FakeQueueClient:
    c = q.FakeQueueClient()
    job = _approved_job()
    c.write_json(q.job_path("approved-ready", OID), job, "seed")
    c.write_json(q.approved_manifest_path("DBT_EP003", H64), _approved_manifest(), "seed")
    return c


def _registry(tmp_path: Path) -> Path:
    src = tmp_path / "edit.mp4"
    src.write_bytes(b"video")
    reg = tmp_path / "sources.json"
    reg.write_text(json.dumps({"version": 1, "sources": {"DBT_EP003": str(src)}}))
    return reg


def _boom(*a, **k):
    raise AssertionError("must not be called in dry-run")


def test_dry_run_builds_commands_no_writes(tmp_path):
    c = _client_with_job()
    c.writes.clear(); c.deletes.clear()  # ignore seed writes; track only process_one
    out = runner.process_one(c, OID, registry_path=None, dropbox_local_root=tmp_path,
                             now="2026-06-18T01:00:00Z", execute=False,
                             render_fn=_boom, proxy_fn=_boom)
    assert out["mode"] == "dry-run" and out["overlay_sha"] == OVERLAY_SHA
    assert "--registry" in out["render_cmd"]
    assert c.writes == [] and c.deletes == []  # dry-run never touches the queue


def test_execute_renders_writes_result_moves_done(tmp_path):
    c = _client_with_job()
    reg = _registry(tmp_path)
    rendered = {"content_hash": "9" * 64, "overlay_sha": OVERLAY_SHA, "output": "out.mp4"}
    proxied = []
    res = runner.process_one(
        c, OID, registry_path=reg, dropbox_local_root=tmp_path, now="2026-06-18T01:00:00Z",
        execute=True, render_fn=lambda rp, m, r: rendered,
        proxy_fn=lambda s, d: proxied.append((str(s), str(d))))
    assert res["status"] == "done" and res["overlay_sha"] == OVERLAY_SHA
    assert res["output_content_hash"] == "9" * 64
    # moved: approved-ready gone, done present, result written
    assert c.read_json(q.job_path("approved-ready", OID)) is None
    assert c.read_json(q.job_path("done", OID))["status"] == "done"
    assert c.read_json(q.result_path(OID))["status"] == "done"
    # proxy written under the local Dropbox mount; source resolved from registry
    assert proxied and "source_proxy.mp4" in proxied[0][1]


def test_execute_render_failure_moves_failed(tmp_path):
    c = _client_with_job()
    reg = _registry(tmp_path)

    def boom_render(rp, m, r):
        raise RuntimeError("ffmpeg exploded")

    res = runner.process_one(c, OID, registry_path=reg, dropbox_local_root=tmp_path,
                             now="2026-06-18T01:00:00Z", execute=True,
                             render_fn=boom_render, proxy_fn=lambda s, d: None)
    assert res["status"] == "failed" and "ffmpeg exploded" in res["error"]
    assert c.read_json(q.job_path("failed", OID))["status"] == "failed"
    assert c.read_json(q.job_path("approved-ready", OID)) is None


def test_execute_unregistered_source_fails_closed(tmp_path):
    c = _client_with_job()
    reg = tmp_path / "empty.json"
    reg.write_text(json.dumps({"version": 1, "sources": {}}))
    res = runner.process_one(c, OID, registry_path=reg, dropbox_local_root=tmp_path,
                             now="2026-06-18T01:00:00Z", execute=True,
                             render_fn=lambda rp, m, r: {"content_hash": "9" * 64, "overlay_sha": OVERLAY_SHA},
                             proxy_fn=lambda s, d: None)
    assert res["status"] == "failed"  # SourceNotAllowed → failed, never renders


def test_failed_result_error_redacts_source_path(tmp_path):
    c = _client_with_job()
    reg = _registry(tmp_path)

    def leaky_render(rp, m, r):
        raise RuntimeError("render died on /Volumes/cam/DBT_EP003/secret.mp4")

    res = runner.process_one(c, OID, registry_path=reg, dropbox_local_root=tmp_path,
                             now="t", execute=True, render_fn=leaky_render, proxy_fn=lambda s, d: None)
    assert res["status"] == "failed"
    assert "/Volumes/" not in res["error"] and "secret.mp4" not in res["error"]
    assert "<redacted-path>" in res["error"]


def test_non_approved_ready_ignored(tmp_path):
    c = q.FakeQueueClient()
    c.write_json(q.job_path("approved-ready", OID), {**_approved_job(), "status": "pending"}, "seed")
    with pytest.raises(runner.RunnerError):
        runner.process_one(c, OID, registry_path=None, dropbox_local_root=tmp_path,
                           now="t", execute=False, render_fn=_boom, proxy_fn=_boom)


def test_manifest_mismatch_rejected(tmp_path):
    c = _client_with_job()
    bad = _approved_manifest(); bad["approval"]["content_hash"] = "b" * 64  # != job pin
    c.write_json(q.approved_manifest_path("DBT_EP003", H64), bad, "seed")
    with pytest.raises(Exception):
        runner.process_one(c, OID, registry_path=None, dropbox_local_root=tmp_path,
                           now="t", execute=False, render_fn=_boom, proxy_fn=_boom)


def test_result_has_no_source_path(tmp_path):
    c = _client_with_job()
    reg = _registry(tmp_path)
    res = runner.process_one(
        c, OID, registry_path=reg, dropbox_local_root=tmp_path, now="t", execute=True,
        render_fn=lambda rp, m, r: {"content_hash": "9" * 64, "overlay_sha": OVERLAY_SHA},
        proxy_fn=lambda s, d: None)
    blob = json.dumps(res)
    assert "/Volumes/" not in blob and "source" not in blob and str(tmp_path) not in blob


def test_run_once_processes_all_approved_ready(tmp_path):
    c = _client_with_job()
    reg = _registry(tmp_path)
    results = runner.run_once(c, registry_path=reg, dropbox_local_root=tmp_path,
                              now="t", execute=True,
                              render_fn=lambda rp, m, r: {"content_hash": "9" * 64, "overlay_sha": OVERLAY_SHA},
                              proxy_fn=lambda s, d: None)
    assert len(results) == 1 and results[0]["status"] == "done"
