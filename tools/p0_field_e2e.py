#!/usr/bin/env python3
"""Synthetic E2E for the Passage field short integration (manifest-driven).

Proves pipeline mechanics + every gate: an HMAC-approved (via the single Passage
approval API) review manifest + a source resolved from the local allowlist by the
manifest's episode_id → render_passage_short → 1080×1920 mp4 (faststart, atomic,
content-hash receipt), with fail-closed on unapproved / tampered / wrong
manifest-hash / wrong overlay-sha / wrong design-sha / episode-mismatch /
unregistered-source / output==source. The manifest journey OMITS the codes.

Real-footage E2E (a real registered POV source) remains. Run with delax_core on
PYTHONPATH.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from delax_core.design import passage_v1  # noqa: E402
from field_shorts import sources  # noqa: E402
import render_passage_short as R  # noqa: E402

KEY = "e2e-test-secret-not-production"
EP = "TEST_PASSAGE"


def make_source(dst: Path) -> None:
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=6",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(dst),
    ], check=True)


def approved_manifest() -> dict:
    m = {
        "schema_version": 1,
        "project": {"episode_id": EP, "title": "Passage E2E",
                    "location_label": "Málaga", "created_at": "2026-05-21T08:00:00+00:00"},
        "source": {"video": "synthetic_src.mp4", "duration_s": 6.0, "gps_csv": "none.csv"},
        "design": {
            "preset": "video-passage-v1", "preset_version": 1,
            "design_sha": passage_v1.design_sha(),
            "journey": {"full_from": "Comares", "full_to": "Málaga",  # codes OMITTED
                        "region": "Málaga, Spain", "mode_label": "Walking", "date": "2026/05/21"},
            "horizontal": {"width": 3840, "height": 2160},
            "vertical": {"width": 1080, "height": 1920},
            "font_jp": "hiragino-kaku-w6/w3", "font_en": "helvetica-neue",
            "show_place": True, "show_road": False, "show_route": True,
            "show_speed": False, "show_heart_rate": False,
        },
        "telemetry": [
            {"time_s": 0.0, "lat": 36.835, "lon": -4.255, "alt_m": 896, "speed_kmh": 4.7},
            {"time_s": 2.0, "lat": 36.78, "lon": -4.34, "alt_m": 500, "speed_kmh": 4.7},
            {"time_s": 4.0, "lat": 36.74, "lon": -4.40, "alt_m": 120, "speed_kmh": 4.7},
        ],
        "cues": [{"id": "cue-001", "start_s": 1.0, "end_s": 4.0,
                  "place": "ライオン峠からの下り", "info": "標高896m A-7000の最高地点",
                  "copy_horizontal": "ライオン峠からの下り",
                  "copy_vertical": ["ライオン峠からの下り"]}],
        "approval": {"status": "draft", "approved_at": None, "approved_by": None,
                     "content_hash": None},
        "outputs": {},
    }
    # the ONLY sanctioned approval path: Passage validator THEN core HMAC sign
    return passage_v1.approve_passage_manifest(m, "claude-e2e", secret_key=KEY)


def job_for(manifest: dict) -> dict:
    cue = manifest["cues"][0]
    return {
        "preset": "video-passage-v1", "preset_version": 1,
        "design_sha": passage_v1.design_sha(),
        "manifest_content_hash": manifest["approval"]["content_hash"],
        "episode_id": manifest["project"]["episode_id"],
        "cue_id": "cue-001", "overlay_sha": R.overlay_sha(cue),
    }


def faststart(path: Path) -> bool:
    head = path.read_bytes()
    moov, mdat = head.find(b"moov"), head.find(b"mdat")
    return moov != -1 and mdat != -1 and moov < mdat


def ffprobe_json(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
        check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="passage_e2e_"))
    src = tmp / "synthetic_src.mp4"
    out = tmp / "passage_short.mp4"
    reg = tmp / "field-shorts-sources.json"
    make_source(src)
    sources.add_source(EP, src, path=reg)  # register the source under the episode id

    manifest = approved_manifest()
    job = job_for(manifest)

    def refused(j, m, o, registry=reg) -> bool:
        try:
            R.render_passage_short(j, m, secret_key=KEY, source_registry_path=registry, output=o)
            return False
        except (R.PassageJobError, ValueError):
            return True

    # 1) happy path — source resolved from the registry by manifest episode_id
    result = R.render_passage_short(job, manifest, secret_key=KEY,
                                    source_registry_path=reg, output=out)
    info = ffprobe_json(out)
    vs = [s for s in info["streams"] if s.get("codec_type") == "video"]
    aus = [s for s in info["streams"] if s.get("codec_type") == "audio"]
    w, h = vs[0]["width"], vs[0]["height"]
    record = json.loads(Path(str(result["record"])).read_text())

    checks = {
        "resolution_1080x1920": (w, h) == (1080, 1920),
        "has_video_and_audio": len(vs) == 1 and len(aus) == 1,
        "faststart": faststart(out),
        "content_hash_matches_record": record["content_hash"] == result["content_hash"],
        "design_sha_pinned": record["design_sha"] == passage_v1.design_sha(),
        "manifest_hash_recorded": record["manifest_content_hash"] == manifest["approval"]["content_hash"],
        "overlay_sha_recorded": record["overlay_sha"] == job["overlay_sha"],
        "episode_recorded": record["episode_id"] == EP,
        "no_temp_left": not list(out.parent.glob(".*tmp*")),
        "no_overlay_left": not list(out.parent.glob(".*passage_overlay*")),
    }

    bad = tmp / "nope.mp4"
    unapproved = copy.deepcopy(manifest); unapproved["approval"]["status"] = "draft"
    checks["refuse_unapproved"] = refused(job, unapproved, bad)
    tampered = copy.deepcopy(manifest); tampered["cues"][0]["place"] = "改ざん"
    checks["refuse_tampered_content"] = refused(job, tampered, bad)
    checks["refuse_wrong_manifest_hash"] = refused({**job, "manifest_content_hash": "0" * 64}, manifest, bad)
    checks["refuse_wrong_overlay_sha"] = refused({**job, "overlay_sha": "0" * 64}, manifest, bad)
    checks["refuse_wrong_design_sha"] = refused({**job, "design_sha": "0" * 64}, manifest, bad)
    checks["refuse_episode_mismatch"] = refused({**job, "episode_id": "OTHER_EP"}, manifest, bad)

    # source not registered: empty registry → resolution fails closed
    empty_reg = tmp / "empty.json"
    checks["refuse_unregistered_source"] = refused(job, manifest, bad, registry=empty_reg)

    # output == source: resolve source then point output at it
    resolved = sources.resolve_source(EP, path=reg)
    checks["refuse_output_eq_source"] = refused(job, manifest, resolved)

    # the single approval API refuses to SIGN a Passage-invalid manifest (half code)
    halfm = copy.deepcopy(manifest); halfm["design"]["journey"]["code_from"] = "COM"
    halfm["approval"] = {"status": "draft", "approved_at": None, "approved_by": None, "content_hash": None}
    try:
        passage_v1.approve_passage_manifest(halfm, "x", secret_key=KEY)
        checks["cannot_sign_invalid_passage"] = False
    except passage_v1.PassageDesignError:
        checks["cannot_sign_invalid_passage"] = True

    print(f"[e2e] {w}x{h} video={len(vs)} audio={len(aus)} faststart={checks['faststart']} "
          f"hash={result['content_hash'][:16]}…")
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    if not all(checks.values()):
        sys.exit("E2E FAILED")
    print(f"[e2e] ALL PASS ({len(checks)} checks)")


if __name__ == "__main__":
    main()
