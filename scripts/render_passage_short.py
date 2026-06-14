#!/usr/bin/env -S uv run --quiet --with pillow python
"""Field 9:16 short renderer — Passage overlay from an APPROVED manifest.

handover 2026-06-14 §3.5 / Codex review 2026-06-14:
- The render context is built from an HMAC-APPROVED review manifest that is
  re-validated here (core `delax_core.review` + Passage `passage_v1`). A raw
  context is NEVER accepted (no approval bypass).
- The job carries only immutable SHA references — preset, preset_version,
  design_sha, approved manifest content_hash, the selected cue id, and the cue's
  overlay_sha — and rendering is refused unless ALL of them match.
- On-video design is the approved `video-passage-v1` preset; compositing + safety
  (temp→ffprobe→atomic rename, faststart, content hash, fail-closed) are Slice 1's,
  reused verbatim. No black bar / center card / pill / CTA.
- The source path is resolved locally (allowlist), never taken from the job (D6).

delax_core is imported as an installed/edit-installed package; no developer-home
absolute path is embedded (§3.2.1).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Slice 1 scaffold (same scripts/ dir, as render_short imports field_shorts)
from render_short import (
    build_ffmpeg_cmd,
    default_output_path,
    ensure_output_distinct_from_source,
    temp_render_path,
)
from field_shorts.ffprobe import ProbeError, probe_duration, verify_video
from field_shorts.hashing import dropbox_content_hash
from field_shorts.sources import SourceRegistryError, resolve_source
from field_shorts.validation import ValidationError, validate_clip_range

try:
    from delax_core import review as core_review
    from delax_core.design import passage_v1
except ImportError as e:  # pragma: no cover
    sys.exit(f"delax_core not importable ({e}); install the approved wheel or "
             f"editable core (PYTHONPATH) — do not hardcode a path")


class PassageJobError(Exception):
    """A malformed / mismatched / unapproved passage job — fail closed, never render."""


def overlay_sha(cue: dict) -> str:
    """SHA-256 of the cue's editable fields (place/info/IN/OUT) — the Web overlay
    identity the job pins."""
    payload = {"place": cue.get("place"), "info": cue.get("info"),
               "start_s": cue.get("start_s"), "end_s": cue.get("end_s")}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")).hexdigest()


def _context_from_manifest(manifest: dict, cue: dict) -> dict:
    design = manifest["design"]
    journey = dict(design.get("journey") or {})
    telem = manifest.get("telemetry", [])
    route = {"lats": [t["lat"] for t in telem], "lons": [t["lon"] for t in telem]}
    cstart = cue["start_s"]
    rec = min(telem, key=lambda t: abs(t["time_s"] - cstart)) if telem else None
    current = ({"lat": rec["lat"], "lon": rec["lon"], "speed_kmh": rec["speed_kmh"]}
               if rec else None)
    return {"journey": journey, "route": route, "current": current,
            "cue": {"place": cue["place"], "info": cue.get("info")}}


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise PassageJobError(msg)


def render_passage_short(
    job: dict, manifest: dict, *,
    secret_key: str | None = None, source_registry_path=None,
    output: Path | None = None, keep_overlay: bool = False,
) -> dict:
    """Render one 9:16 Passage short from an APPROVED manifest. The source is
    resolved from the LOCAL allowlist by the manifest's episode_id — never passed
    in — so an approved Episode A manifest cannot render Episode B footage.
    Fail-closed at every gate. Returns {output, content_hash, design_sha, overlay_sha}."""
    key = secret_key or os.environ.get("DELAX_HMAC_SECRET")
    _require(bool(key), "HMAC secret required (DELAX_HMAC_SECRET) to verify approval")

    # 1. core approval (HMAC) + core schema/semantic + Passage semantic — all must pass
    _require(core_review.verify_approval(manifest, secret_key=key),
             "manifest is not approved or its content changed since signing")
    core_errs = core_review.validate_manifest(manifest, secret_key=key)
    _require(not core_errs, f"core manifest invalid: {core_errs}")
    schema_errs = passage_v1.validate_passage_schema(manifest)
    _require(not schema_errs, f"passage design schema invalid: {schema_errs}")
    passage_errs = passage_v1.validate_passage_manifest(
        manifest, expected_design_sha=job.get("design_sha"))
    _require(not passage_errs, f"passage manifest invalid: {passage_errs}")

    # 2. immutable SHA pins — preset / version / design_sha / manifest hash / overlay sha
    design = manifest["design"]
    local_sha = passage_v1.design_sha()
    _require(job.get("preset") == design.get("preset") == passage_v1.PRESET_NAME,
             "preset mismatch (job / manifest / local preset)")
    _require(job.get("preset_version") == design.get("preset_version") == passage_v1.PRESET_VERSION,
             "preset_version mismatch")
    _require(job.get("design_sha") == design.get("design_sha") == local_sha,
             f"design_sha mismatch (job={job.get('design_sha')} local={local_sha})")
    recomputed = core_review.calculate_content_hash(manifest)
    _require(job.get("manifest_content_hash") == manifest["approval"]["content_hash"] == recomputed,
             "approved manifest content_hash mismatch")

    cue = next((c for c in manifest.get("cues", []) if c.get("id") == job.get("cue_id")), None)
    _require(cue is not None, f"cue {job.get('cue_id')!r} not found in manifest")
    _require(job.get("overlay_sha") == overlay_sha(cue), "overlay_sha mismatch (stale cue edit)")

    # 3. episode binding — job.episode_id must equal manifest.project.episode_id, and
    #    the source is resolved from the local allowlist by THAT id (not the job/CLI),
    #    so an approved manifest cannot be pointed at another episode's footage (D6).
    episode_id = manifest.get("project", {}).get("episode_id")
    _require(bool(episode_id) and job.get("episode_id") == episode_id,
             f"episode_id mismatch (job={job.get('episode_id')!r} manifest={episode_id!r})")
    try:
        source = resolve_source(episode_id, path=source_registry_path)
    except SourceRegistryError as e:
        raise PassageJobError(f"source resolution failed for {episode_id!r}: {e}") from e

    # 4. clip window from the approved cue
    start_s = float(cue["start_s"])
    duration_s = float(cue["end_s"]) - start_s
    try:
        src_dur = probe_duration(source)
        validate_clip_range(start_s, duration_s, src_dur)
    except (ProbeError, ValidationError) as e:
        raise PassageJobError(f"clip window invalid against source: {e}") from e

    out = output or default_output_path(source, episode_id)
    ensure_output_distinct_from_source(source, out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 5. Passage 9:16 overlay (preset-owned) → Slice 1 composite + safety
    context = _context_from_manifest(manifest, cue)
    overlay = passage_v1.render_overlay(context, "vertical")  # 1080×1920 RGBA
    overlay_png = out.parent / f".{out.stem}.passage_overlay.png"
    overlay.save(overlay_png)

    tmp = temp_render_path(out)
    try:
        cmd = build_ffmpeg_cmd(source, tmp, start_s, duration_s, overlay_png, None, 0.0)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise PassageJobError(
                f"ffmpeg failed (exit {proc.returncode}): {(proc.stderr or proc.stdout).strip()}")
        try:
            verify_video(tmp, expect_duration=duration_s)
        except ProbeError as e:
            raise PassageJobError(f"rendered file failed verification: {e}") from e
        os.replace(tmp, out)  # atomic
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        if not keep_overlay:
            overlay_png.unlink(missing_ok=True)

    content_hash = dropbox_content_hash(out)
    record = {
        "schema_version": 1, "kind": "passage_short",
        "episode_id": episode_id,
        "output": str(out), "content_hash": content_hash,
        "preset": passage_v1.PRESET_NAME, "preset_version": passage_v1.PRESET_VERSION,
        "design_sha": local_sha, "manifest_content_hash": recomputed,
        "cue_id": cue["id"], "overlay_sha": job["overlay_sha"],
        "format": "vertical", "faststart": True,
        "source_name": Path(source).name, "start_s": start_s, "duration_s": duration_s,
        "rendered_at": datetime.now(timezone.utc).isoformat(),
    }
    record_path = out.with_name(f"{out.stem}.passage.json")
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    return {"output": out, "content_hash": content_hash, "design_sha": local_sha,
            "overlay_sha": job["overlay_sha"], "record": record_path}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True, type=Path, help="passage job JSON (SHA pins)")
    ap.add_argument("--manifest", required=True, type=Path, help="approved review manifest JSON")
    ap.add_argument("--registry", type=Path, default=None,
                    help="source allowlist path (default ~/.config/...); source is "
                         "resolved by the manifest's episode_id, never passed in")
    ap.add_argument("--output", "-o", type=Path, default=None)
    ap.add_argument("--keep-overlay", action="store_true")
    args = ap.parse_args()

    job = json.loads(args.job.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    try:
        result = render_passage_short(
            job, manifest, source_registry_path=args.registry,
            output=args.output, keep_overlay=args.keep_overlay)
    except (PassageJobError, passage_v1.PassageDesignError) as e:
        sys.exit(f"passage render refused: {e}")
    print(f"✓ {result['output']}")
    print(f"  content_hash={result['content_hash']}")
    print(f"  design_sha={result['design_sha']}")
    print(f"  overlay_sha={result['overlay_sha']}")
    print(f"  record={result['record']}")


if __name__ == "__main__":
    main()
