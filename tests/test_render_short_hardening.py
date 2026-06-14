"""render_short.py の Slice 1 ハードニング (faststart / temp / record) テスト。

ffmpeg は回さず、抽出した純粋ヘルパ (build_ffmpeg_cmd / temp_render_path /
write_render_record) を直接叩く。
"""
from __future__ import annotations

import json
from pathlib import Path

import render_short


def test_faststart_flag_no_cta():
    cmd = render_short.build_ffmpeg_cmd(
        Path("/src.mp4"), Path("/out.mp4"), 5, 30,
        Path("/ov.png"), None, 5.0,
    )
    assert "-movflags" in cmd
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"
    assert cmd[-1] == "/out.mp4"
    assert cmd.count("-i") == 2  # source + overlay


def test_faststart_flag_with_cta():
    cmd = render_short.build_ffmpeg_cmd(
        Path("/src.mp4"), Path("/out.mp4"), 5, 30,
        Path("/ov.png"), Path("/cta.png"), 5.0,
    )
    assert "+faststart" in cmd
    assert cmd.count("-i") == 3  # source + overlay + cta


def test_temp_render_path_hidden_keeps_mp4():
    out = Path("/x/y/short_C0122.mp4")
    tmp = render_short.temp_render_path(out)
    assert tmp.name == ".short_C0122.tmp.mp4"
    assert tmp.parent == out.parent
    assert tmp.suffix == ".mp4"  # ffmpeg muxer 判定 + os.replace atomic のため


def test_write_render_record(tmp_path):
    out = tmp_path / "short_C0122.mp4"
    out.write_bytes(b"x")
    rp = render_short.write_render_record(
        out,
        content_hash="abc123",
        episode_id="DWT_EP002",
        source=Path("/Volumes/SSD/C0122.MP4"),
        start_s=5,
        duration_s=30,
        location_primary="マラガ",
        location_secondary="Málaga · Spain · 2026.05.04",
        cta_text=None,
    )
    assert rp.name == "short_C0122.render.json"
    rec = json.loads(rp.read_text(encoding="utf-8"))
    assert rec["content_hash"] == "abc123"
    assert rec["faststart"] is True
    assert rec["episode_id"] == "DWT_EP002"
    assert rec["source_name"] == "C0122.MP4"
    assert rec["duration_s"] == 30
