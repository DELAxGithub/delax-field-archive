"""Field Telop render-queue poller — Step 5 (dry-run / mock).

Reads a Field Telop render job + its per-cue overlay (written by field-telop-check-web
on the `render-queue` branch), re-verifies them against the approved passage_v1
manifest, applies the cue edit, and prepares the render + proxy commands.

overlay_sha SSoT
----------------
The poller NEVER re-implements overlay_sha. It is computed by
`render_passage_short.overlay_sha()` (Python), which is the single source of truth
(the Web cannot reproduce json.dumps's float/int repr byte-for-byte, so it never
computes it). That module hard-imports `delax_core` at load and `sys.exit`s without
it, so the import is LAZY here — only `compute_overlay_sha()` needs the wheel.
Everything else (parse / validate / consistency / apply / command build / result /
proxy path) is pure and runs without the wheel.

Scope (Step 5): build the plan and commands. It does NOT (yet) do real GitHub
render-queue I/O, real ffmpeg render, real Dropbox upload, or LaunchAgent
registration — those are driven by an outer runner.

Production note
---------------
`render_passage_short.py` + `field_shorts/*` currently live on
`feat/field-passage-integration`; integrate them to main / a baseline branch
before production. The poller resolves them relative to this scripts/ dir.
"""
from __future__ import annotations

import math
import numbers
import re
import sys
from pathlib import Path

from field_shorts.proxy import build_proxy_cmd
from field_shorts.sources import resolve_source

# --- schema validation regexes (mirror field-telop-check-web; NOT overlay_sha) ---
SHA_HEX = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
EPISODE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
CUE_ID = re.compile(r"^cue-\d{3,5}$")
GH_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
OVERLAY_ID = re.compile(r"^\d{8}T\d{6}Z-cue-\d{3,5}-[a-z0-9]{4,16}$")

OVERLAYS_DIR = "field-telop/overlays"
PROXY_DIR = "field-telop/proxies"
PROXY_FILE = "source_proxy.mp4"
JOB_KIND = "field-telop-render"
PRESET = "video-passage-v1"

# Exact key allow-lists — the poller is the last gate on untrusted render-queue
# JSON, so any unknown key (source, overlay_sha, copy_*, local_path, *_token, …)
# is fail-closed, mirroring the Web's strict() schemas.
JOB_KEYS = frozenset({
    "schema_version", "job_kind", "job_id", "episode_id", "cue_id", "overlay_id",
    "overlay_path", "manifest_sha", "manifest_content_hash", "passage_info_hash",
    "preset", "preset_version", "design_sha", "requested_by", "created_at", "status",
})
OVERLAY_KEYS = frozenset({
    "schema_version", "overlay_kind", "overlay_id", "episode_id", "cue_id",
    "base_manifest_sha", "base_manifest_content_hash", "passage_info_hash",
    "place", "info", "start_s", "end_s", "review_note", "approval_reset_required",
    "updated_by", "updated_at",
})

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # .../scripts


class PollerError(Exception):
    """A malformed / mismatched job or overlay — fail closed, never render."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise PollerError(msg)


def _match(pattern: re.Pattern[str], value: object) -> bool:
    return isinstance(value, str) and pattern.match(value) is not None


def _finite_nonneg(value: object) -> bool:
    """A real, finite, non-negative number — and NOT a bool (bool is an int
    subclass in Python, so isinstance(True, int) is True)."""
    return (
        isinstance(value, numbers.Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and value >= 0
    )


def _assert_exact_keys(data: dict, allowed: frozenset[str], what: str) -> None:
    keys = set(data.keys())
    if keys != allowed:
        unexpected = keys - allowed
        missing = allowed - keys
        raise PollerError(f"{what} keys mismatch: unexpected={sorted(unexpected)} missing={sorted(missing)}")


# ── parse / validate ────────────────────────────────────────────────────────
def parse_job(data: object) -> dict:
    _require(isinstance(data, dict), "job must be an object")
    job = dict(data)  # type: ignore[arg-type]
    # fail-closed on any unknown key (source / overlay_sha / *_token / …)
    _assert_exact_keys(job, JOB_KEYS, "job")
    _require(job.get("schema_version") == 1, "job schema_version must be 1")
    _require(job.get("job_kind") == JOB_KIND, f"job_kind must be {JOB_KIND}")
    _require(_match(OVERLAY_ID, job.get("job_id")), "bad job_id")
    _require(_match(OVERLAY_ID, job.get("overlay_id")), "bad overlay_id")
    _require(job.get("job_id") == job.get("overlay_id"), "job_id must equal overlay_id")
    _require(_match(EPISODE_ID, job.get("episode_id")), "bad episode_id")
    _require(_match(CUE_ID, job.get("cue_id")), "bad cue_id")
    _require(isinstance(job.get("overlay_path"), str) and job["overlay_path"].startswith(OVERLAYS_DIR + "/"),
             "bad overlay_path")
    _require(_match(GIT_SHA, job.get("manifest_sha")), "bad manifest_sha")
    _require(_match(SHA_HEX, job.get("manifest_content_hash")), "bad manifest_content_hash")
    _require(_match(SHA_HEX, job.get("passage_info_hash")), "bad passage_info_hash")
    _require(_match(SHA_HEX, job.get("design_sha")), "bad design_sha")
    _require(job.get("preset") == PRESET, "bad preset")
    _require(job.get("preset_version") == 1, "bad preset_version")
    _require(_match(GH_LOGIN, job.get("requested_by")), "bad requested_by")
    _require(_match(ISO_UTC, job.get("created_at")), "bad created_at")
    _require(job.get("status") in ("pending", "running", "done", "failed"), "bad status")
    return job


def parse_overlay(data: object) -> dict:
    _require(isinstance(data, dict), "overlay must be an object")
    ov = dict(data)  # type: ignore[arg-type]
    # fail-closed on any unknown key (source / overlay_sha / copy_horizontal / …)
    _assert_exact_keys(ov, OVERLAY_KEYS, "overlay")
    _require(ov.get("schema_version") == 1, "overlay schema_version must be 1")
    _require(ov.get("overlay_kind") == "field-telop-cue-overlay", "bad overlay_kind")
    _require(_match(OVERLAY_ID, ov.get("overlay_id")), "bad overlay_id")
    _require(_match(EPISODE_ID, ov.get("episode_id")), "bad episode_id")
    _require(_match(CUE_ID, ov.get("cue_id")), "bad cue_id")
    _require(_match(GIT_SHA, ov.get("base_manifest_sha")), "bad base_manifest_sha")
    _require(_match(SHA_HEX, ov.get("base_manifest_content_hash")), "bad base_manifest_content_hash")
    _require(_match(SHA_HEX, ov.get("passage_info_hash")), "bad passage_info_hash")
    _require(isinstance(ov.get("place"), str), "bad place")
    _require(isinstance(ov.get("info"), str) and ov["info"].strip(), "info is empty")
    _require(_finite_nonneg(ov.get("start_s")), "bad start_s (must be a finite, non-negative number)")
    _require(_finite_nonneg(ov.get("end_s")), "bad end_s (must be a finite, non-negative number)")
    _require(ov["end_s"] > ov["start_s"], "end_s must be after start_s")
    _require(ov.get("approval_reset_required") is True, "approval_reset_required must be true")
    _require(_match(GH_LOGIN, ov.get("updated_by")), "bad updated_by")
    _require(_match(ISO_UTC, ov.get("updated_at")), "bad updated_at")
    return ov


def assert_job_overlay_consistent(job: dict, overlay: dict) -> None:
    _require(overlay["episode_id"] == job["episode_id"], "episode_id mismatch (job/overlay)")
    _require(overlay["cue_id"] == job["cue_id"], "cue_id mismatch (job/overlay)")
    _require(overlay["overlay_id"] == job["overlay_id"], "overlay_id mismatch (job/overlay)")
    expected = f"{OVERLAYS_DIR}/{job['episode_id']}/{job['cue_id']}/{job['overlay_id']}.json"
    _require(job["overlay_path"] == expected, f"overlay_path mismatch (expected {expected})")


def assert_manifest_match(job: dict, manifest: dict) -> None:
    """Authoritative re-verify against the server's manifest (poller is the last gate)."""
    proj = manifest.get("project", {})
    _require(proj.get("episode_id") == job["episode_id"], "episode_id mismatch (job/manifest)")
    approval = manifest.get("approval", {})
    _require(approval.get("status") == "approved", "manifest is not approved")
    _require(approval.get("content_hash") == job["manifest_content_hash"],
             "manifest_content_hash mismatch (stale)")
    _require(manifest.get("passage_info_hash") == job["passage_info_hash"],
             "passage_info_hash mismatch")
    design = manifest.get("design", {})
    _require(design.get("design_sha") == job["design_sha"], "design_sha mismatch")


def apply_overlay(manifest: dict, overlay: dict) -> dict:
    """Return the manifest cue with the overlay's edits applied (the cue overlay_sha
    is computed over). copy_horizontal/copy_vertical stay as the manifest's."""
    cue = next((c for c in manifest.get("cues", []) if c.get("id") == overlay["cue_id"]), None)
    _require(cue is not None, f"cue {overlay['cue_id']} not found in manifest")
    applied = dict(cue)  # type: ignore[arg-type]
    applied["place"] = overlay["place"]
    applied["info"] = overlay["info"]
    applied["start_s"] = overlay["start_s"]
    applied["end_s"] = overlay["end_s"]
    return applied


# ── overlay_sha SSoT (lazy import; needs delax_core wheel) ────────────────────
def compute_overlay_sha(applied_cue: dict) -> str:
    """Compute overlay_sha via render_passage_short.overlay_sha — the SSoT. Lazy
    import: render_passage_short hard-imports delax_core and exits without it."""
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    from render_passage_short import overlay_sha  # noqa: E402  (lazy: needs delax_core)

    return overlay_sha(applied_cue)


# ── command / path / result builders (pure) ──────────────────────────────────
def build_render_passage_job(job: dict, overlay_sha: str) -> dict:
    """The render_passage_short.py job: field-telop pins + the poller-computed
    overlay_sha (render_passage_short refuses to render unless it matches)."""
    _require(_match(SHA_HEX, overlay_sha), "overlay_sha must be a 64-hex sha")
    return {
        "preset": PRESET,
        "preset_version": 1,
        "design_sha": job["design_sha"],
        "manifest_content_hash": job["manifest_content_hash"],
        "episode_id": job["episode_id"],
        "cue_id": job["cue_id"],
        "overlay_sha": overlay_sha,
    }


def build_render_command(
    rp_job_path: str | Path, manifest_path: str | Path, registry_path: str | Path,
    *, python_exe: str = "python3", render_script: Path | None = None,
) -> list[str]:
    """argv for render_passage_short.py. The source is NEVER passed — it is
    resolved by render_passage_short from the registry by episode_id (D6)."""
    script = render_script or (_SCRIPTS_DIR / "render_passage_short.py")
    return [python_exe, str(script),
            "--job", str(rp_job_path),
            "--manifest", str(manifest_path),
            "--registry", str(registry_path)]


def proxy_dropbox_path(episode_id: str, dropbox_root: str = "/DELAX_field") -> str:
    """Dropbox path of the episode proxy (matches the Web's field-proxy.ts):
    <DROPBOX_ROOT>/field-telop/proxies/<episode_id>/source_proxy.mp4."""
    _require(_match(EPISODE_ID, episode_id), f"unsafe episode_id: {episode_id}")
    return f"{dropbox_root}/{PROXY_DIR}/{episode_id}/{PROXY_FILE}"


def build_proxy_command(source: str | Path, dest: str | Path) -> list[str]:
    """Low-res proxy ffmpeg argv — reuses field_shorts.proxy.build_proxy_cmd (SSoT
    for the encode). `source` is the LOCAL registry-resolved path (stays on the Mac,
    never in a job/result); `dest` is the local Dropbox-mount proxy path."""
    return build_proxy_cmd(source, dest)


def build_result(job: dict, overlay_sha: str, *, output_content_hash: str, status: str,
                 finished_at: str) -> dict:
    """Render result written back to field-telop/results/<job_id>.json. Records the
    poller-computed overlay_sha + output hash. Contains NO source path."""
    _require(status in ("done", "failed"), "result status must be done|failed")
    return {
        "schema_version": 1,
        "job_id": job["job_id"],
        "episode_id": job["episode_id"],
        "cue_id": job["cue_id"],
        "overlay_id": job["overlay_id"],
        "overlay_sha": overlay_sha,
        "output_content_hash": output_content_hash,
        "status": status,
        "finished_at": finished_at,
    }


def assert_source_registered(episode_id: str, registry_path: str | Path) -> Path:
    """Fail-closed if the episode has no registered source (D6 allowlist)."""
    return resolve_source(episode_id, path=registry_path)
