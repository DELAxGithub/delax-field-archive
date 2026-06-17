"""Field Telop local approve CLI (Phase 6) — HMAC re-approval of an edited overlay.

The Web/Vercel and the poller NEVER sign. ONLY this local CLI signs, and only via
`passage_v1.approve_passage_manifest()` (the sanctioned path). It:

  1. takes a pending field-telop job + its per-cue overlay + the base approved manifest
  2. applies the overlay edit to the manifest cue
  3. SANITIZES `source` to a registry URI (`registry://<episode_id>`) so no absolute
     source path is ever written to a GitHub-bound artifact (verified: registry URI
     passes passage_v1 validate/approve/verify; render_passage_short resolves the real
     source from the local D6 registry by episode_id, ignoring source.video)
  4. re-approves (HMAC sign) the edited manifest
  5. computes overlay_sha over the approved cue via render_passage_short.overlay_sha (SSoT)
  6. advances the job to `approved-ready` with the NEW content_hash + overlay_sha

Output: an approved manifest + an approved-ready job. The poller renders only
approved-ready jobs. Requires `DELAX_HMAC_SECRET` (fail-closed without it).

Production note: render_passage_short.py / field_shorts / passage_v1 live on
feat/field-passage-integration; integrate to main before production.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from pathlib import Path

from field_shorts import field_telop_queue_poller as poller

# Local absolute-path / leak markers that must never reach a GitHub-bound artifact.
_LOCAL_PATH = re.compile(r"(^/)|(/Users/)|(/Volumes/)|(/private/)|(/var/folders/)|(/tmp/)")


class ApproveError(Exception):
    """Re-approval failed — fail closed, never emit an approved artifact."""


def registry_uri(episode_id: str) -> str:
    return f"registry://{episode_id}"


def sanitize_source(source: dict, episode_id: str) -> dict:
    """Return a registry-safe `source`: video/gps_csv become registry URIs, only
    duration_s is preserved. No absolute/local path survives into the manifest."""
    return {
        "video": registry_uri(episode_id),
        "duration_s": source.get("duration_s"),
        "gps_csv": registry_uri(episode_id),
    }


def edited_manifest(base_manifest: dict, overlay: dict, episode_id: str) -> dict:
    """Apply the overlay edit to the matching cue, reset approval to draft, and
    sanitize source. Returns a NEW manifest (base is not mutated)."""
    applied_cue = poller.apply_overlay(base_manifest, overlay)  # validates cue presence
    m = copy.deepcopy(base_manifest)
    m["cues"] = [applied_cue if c.get("id") == overlay["cue_id"] else c for c in m["cues"]]
    m["source"] = sanitize_source(m.get("source", {}), episode_id)
    m["approval"] = {"status": "draft", "approved_at": None, "approved_by": None,
                     "content_hash": None, "signature": None}
    return m


def build_approved_job(pending_job: dict, *, overlay_sha: str, new_content_hash: str,
                       approved_by: str, approved_at: str) -> dict:
    """The pending job advanced to approved-ready: + overlay_sha, + approver meta,
    and manifest_content_hash updated to the NEW approved hash."""
    job = dict(pending_job)
    job["status"] = "approved-ready"
    job["overlay_sha"] = overlay_sha
    job["manifest_content_hash"] = new_content_hash
    job["approved_by"] = approved_by
    job["approved_at"] = approved_at
    return job


def _assert_registry_source(manifest: dict, label: str) -> None:
    """ALLOWLIST: source.video / gps_csv must be registry:// URIs (positive check —
    not a brittle denylist). Catches any non-registry source (/mnt, /home, C:\\,
    file://, …), not just known leak markers."""
    src = manifest.get("source", {})
    for field in ("video", "gps_csv"):
        v = src.get(field)
        if not (isinstance(v, str) and v.startswith("registry://")):
            raise ApproveError(f"{label} source.{field} must be a registry:// URI, got {v!r}")


def _assert_no_local_path(obj: dict, label: str) -> None:
    """Defense-in-depth denylist scan over the whole artifact (any leaked local
    path beyond source.*), on top of the source allowlist above."""
    blob = json.dumps(obj, ensure_ascii=False)
    if _LOCAL_PATH.search(blob):
        raise ApproveError(f"{label} contains a local/absolute path (must be registry:// only)")


def approve_overlay(job_in: dict, overlay_in: dict, base_manifest: dict, *,
                    approved_by: str, secret_key: str | None) -> tuple[dict, dict]:
    """Full re-approval. Needs delax_core (lazy import) + DELAX_HMAC_SECRET. Returns
    (approved_manifest, approved_job). Fail-closed at every gate."""
    key = secret_key or os.environ.get("DELAX_HMAC_SECRET")
    if not key:
        raise ApproveError("DELAX_HMAC_SECRET required (local approve CLI signs; Web/poller never sign)")

    job = poller.parse_job(job_in)
    overlay = poller.parse_overlay(overlay_in)
    poller.assert_job_overlay_consistent(job, overlay)
    poller.assert_manifest_match(job, base_manifest)  # base manifest matches the job's base pins

    em = edited_manifest(base_manifest, overlay, job["episode_id"])

    # lazy: passage_v1 / review hard-require delax_core (the wheel)
    if str(poller._SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(poller._SCRIPTS_DIR))
    from delax_core.design import passage_v1
    from delax_core import review as core_review

    errs = passage_v1.validate_passage_manifest(em, expected_design_sha=job["design_sha"])
    if errs:
        raise ApproveError(f"passage manifest invalid after edit: {errs}")
    approved = passage_v1.approve_passage_manifest(em, approved_by, secret_key=key)
    if not core_review.verify_approval(approved, secret_key=key):
        raise ApproveError("verify_approval failed on the freshly approved manifest")

    cue = next((c for c in approved["cues"] if c.get("id") == job["cue_id"]), None)
    if cue is None:
        raise ApproveError(f"cue {job['cue_id']} missing after approval")
    overlay_sha = poller.compute_overlay_sha(cue)  # render_passage_short.overlay_sha (SSoT)

    approved_job = build_approved_job(
        job, overlay_sha=overlay_sha, new_content_hash=approved["approval"]["content_hash"],
        approved_by=approved_by, approved_at=approved["approval"]["approved_at"])

    # fail-closed: source must be registry:// (allowlist) AND no local/absolute
    # path anywhere in either GitHub-bound artifact (denylist, defense in depth)
    _assert_registry_source(approved, "approved manifest")
    _assert_no_local_path(approved, "approved manifest")
    _assert_no_local_path(approved_job, "approved job")
    # the approved-ready job must itself parse (round-trip validation)
    poller.parse_approved_job(approved_job)
    return approved, approved_job


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Field Telop local HMAC re-approval CLI")
    ap.add_argument("--job", required=True, type=Path, help="pending field-telop job JSON")
    ap.add_argument("--overlay", required=True, type=Path, help="per-cue overlay JSON")
    ap.add_argument("--manifest", required=True, type=Path, help="base approved passage_v1 manifest JSON")
    ap.add_argument("--out-manifest", required=True, type=Path, help="approved manifest output")
    ap.add_argument("--out-job", required=True, type=Path, help="approved-ready job output")
    ap.add_argument("--approved-by", required=True, help="GitHub login of the human approver")
    args = ap.parse_args(argv)

    job_in = json.loads(args.job.read_text(encoding="utf-8"))
    overlay_in = json.loads(args.overlay.read_text(encoding="utf-8"))
    base_manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    try:
        approved, approved_job = approve_overlay(
            job_in, overlay_in, base_manifest, approved_by=args.approved_by, secret_key=None)
    except ApproveError as e:
        print(f"[approve] FAIL: {e}", file=sys.stderr)
        return 1
    args.out_manifest.write_text(json.dumps(approved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.out_job.write_text(json.dumps(approved_job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[approve] approved {approved_job['job_id']} content_hash="
          f"{approved['approval']['content_hash'][:12]} overlay_sha={approved_job['overlay_sha'][:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
