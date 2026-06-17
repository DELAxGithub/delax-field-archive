"""Field Telop runner (Phase 7) — process approved-ready jobs.

Reads approved-ready jobs from the render-queue (via an injectable QueueClient),
re-verifies them against the approved manifest, renders via render_passage_short.py
(the authoritative HMAC/overlay_sha gate), generates the proxy, writes the result,
and moves the job to done/failed.

Modes:
  --dry-run (default): build the render + proxy commands, NO subprocess, NO queue
                       writes. Safe to run anywhere.
  --execute:           claim → render_passage_short → proxy → result → move.
  --once / --loop:     one pass / repeat (LaunchAgent uses --loop).

render_passage_short / ffmpeg run only in --execute and need delax_core wheel +
DELAX_HMAC_SECRET + a registered source + ffmpeg. The runner NEVER signs (it only
delegates verification to render_passage_short). source paths never enter the
result/job (resolved by render_passage_short from the D6 registry).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

# Redact any absolute/local path so a failure message (e.g. SourceMissing carrying
# the resolved source path) never leaks a source path into the result artifact.
_ABS_PATH = re.compile(r"(/Users/|/Volumes/|/private/|/var/folders/|/tmp/|/mnt/|/home/)\S*")


def _safe_error(e: Exception) -> str:
    return _ABS_PATH.sub("<redacted-path>", str(e))

from field_shorts import field_telop_queue_poller as poller
from field_shorts import field_telop_queue as q
from field_shorts.sources import resolve_source


class RunnerError(Exception):
    pass


def proxy_local_path(dropbox_local_root: str | Path, episode_id: str) -> Path:
    """Local filesystem path of the proxy under the Dropbox mount, from the
    Dropbox-relative proxy path (proxy_dropbox_path)."""
    rel = poller.proxy_dropbox_path(episode_id).lstrip("/")
    return Path(dropbox_local_root).expanduser() / rel


def _load_approved(client: q.QueueClient, job_id: str) -> tuple[dict, dict]:
    """Read + structurally re-verify an approved-ready job and its approved manifest.
    Verification of HMAC/overlay_sha is delegated to render_passage_short at render
    time; here we gate the queue (eligibility + manifest pin match)."""
    raw = client.read_json(q.job_path("approved-ready", job_id))
    if raw is None:
        raise RunnerError(f"job {job_id} not in approved-ready")
    if not poller.is_render_eligible(raw):
        raise RunnerError(f"job {job_id} is not render-eligible")
    job = poller.parse_approved_job(raw)
    manifest = client.read_json(q.approved_manifest_path(job["episode_id"], job["manifest_content_hash"]))
    if manifest is None:
        raise RunnerError(f"approved manifest missing for {job_id}")
    poller.assert_manifest_match(job, manifest)  # episode/content_hash/passage_info_hash/design_sha/approved
    return job, manifest


def default_render_fn(rp_job: dict, manifest: dict, registry_path: str | Path | None,
                      *, render_script: Path | None = None) -> dict:
    """Run render_passage_short.py as a subprocess (it does the authoritative
    verify_approval + overlay_sha + approval gates). Returns {content_hash,
    overlay_sha, output}. Only called in --execute."""
    script = render_script or (poller._SCRIPTS_DIR / "render_passage_short.py")
    with tempfile.TemporaryDirectory() as td:
        jp = Path(td) / "rp_job.json"
        mp = Path(td) / "manifest.json"
        out = Path(td) / "out.mp4"
        jp.write_text(json.dumps(rp_job), encoding="utf-8")
        mp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        cmd = poller.build_render_command(jp, mp, registry_path or "", render_script=script)
        cmd += ["--output", str(out)]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise RunnerError(f"render_passage_short failed: {p.stderr.strip() or p.stdout.strip()}")
        fields = {}
        for line in p.stdout.splitlines():
            for key in ("content_hash", "overlay_sha"):
                if line.strip().startswith(key + "="):
                    fields[key] = line.split("=", 1)[1].strip()
        if "content_hash" not in fields or "overlay_sha" not in fields:
            raise RunnerError("render_passage_short produced no content_hash/overlay_sha")
        return {"content_hash": fields["content_hash"], "overlay_sha": fields["overlay_sha"],
                "output": str(out)}


def default_proxy_fn(source: str | Path, dest: str | Path) -> None:
    """Generate the low-res proxy via ffmpeg into the local Dropbox mount."""
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    cmd = poller.build_proxy_command(source, dest)
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RunnerError(f"proxy ffmpeg failed: {p.stderr.strip()}")


def process_one(client: q.QueueClient, job_id: str, *, registry_path: str | Path | None,
                dropbox_local_root: str | Path, now: str, execute: bool,
                render_fn=default_render_fn, proxy_fn=default_proxy_fn) -> dict:
    """Process a single approved-ready job. Dry-run returns a plan (no writes);
    execute claims → renders → proxies → writes result → moves the job."""
    job, manifest = _load_approved(client, job_id)
    rp_job = poller.build_render_passage_job(job, job["overlay_sha"])
    proxy_dst = proxy_local_path(dropbox_local_root, job["episode_id"])

    if not execute:
        # build commands only — no subprocess, no queue writes
        render_cmd = poller.build_render_command("<rp_job>", "<manifest>", registry_path or "<registry>")
        return {"mode": "dry-run", "job_id": job_id, "episode_id": job["episode_id"],
                "render_cmd": render_cmd, "proxy_dest": str(proxy_dst),
                "overlay_sha": job["overlay_sha"]}

    # claim: approved-ready → running
    client.write_json(q.job_path("running", job_id), {**job, "status": "running"},
                      f"chore(field-telop): claim {job_id}")
    client.delete(q.job_path("approved-ready", job_id), f"chore(field-telop): claim {job_id}")
    try:
        source = resolve_source(job["episode_id"], path=registry_path)  # D6, fail-closed
        rendered = render_fn(rp_job, manifest, registry_path)
        proxy_fn(source, proxy_dst)
        result = poller.build_result(job, rendered["overlay_sha"],
                                     output_content_hash=rendered["content_hash"],
                                     status="done", finished_at=now)
        terminal = "done"
    except Exception as e:  # noqa: BLE001 — any failure is recorded, never a stuck running job
        result = poller.build_result(job, job["overlay_sha"], output_content_hash="0" * 64,
                                     status="failed", finished_at=now)
        result["error"] = _safe_error(e)  # redact any absolute/source path
        terminal = "failed"
    client.write_json(q.result_path(job_id), result, f"chore(field-telop): result {job_id}")
    client.write_json(q.job_path(terminal, job_id), {**job, "status": terminal},
                      f"chore(field-telop): {terminal} {job_id}")
    client.delete(q.job_path("running", job_id), f"chore(field-telop): {terminal} {job_id}")
    return result


def run_once(client: q.QueueClient, *, registry_path: str | Path | None,
             dropbox_local_root: str | Path, now: str, execute: bool, **fns) -> list[dict]:
    out = []
    for name in client.list_names(f"{q.JOBS_DIR}/approved-ready"):
        if not name.endswith(".json"):
            continue
        out.append(process_one(client, name[:-5], registry_path=registry_path,
                               dropbox_local_root=dropbox_local_root, now=now,
                               execute=execute, **fns))
    return out


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Field Telop runner")
    ap.add_argument("--execute", action="store_true", help="render (default is dry-run)")
    ap.add_argument("--loop", action="store_true", help="repeat (LaunchAgent); else one pass")
    ap.add_argument("--interval", type=int, default=120)
    ap.add_argument("--owner", default=os.environ.get("GITHUB_REPO_OWNER", "DELAxGithub"))
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPO_NAME", "delax-field-archive"))
    ap.add_argument("--branch", default="render-queue")
    ap.add_argument("--registry", default=None)
    ap.add_argument("--dropbox-local-root", default=os.environ.get("DROPBOX_LOCAL_ROOT", str(Path.home() / "Dropbox")))
    args = ap.parse_args(argv)

    client = q.GhQueueClient(args.owner, args.repo, args.branch)

    def one() -> None:
        results = run_once(client, registry_path=args.registry,
                           dropbox_local_root=args.dropbox_local_root, now=_now_iso(),
                           execute=args.execute)
        print(f"[runner] processed {len(results)} job(s) (execute={args.execute})")

    if args.loop:
        import time
        while True:
            try:
                one()
            except q.QueueError as e:
                print(f"[runner] queue error: {e}")
            time.sleep(args.interval)
    else:
        one()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
