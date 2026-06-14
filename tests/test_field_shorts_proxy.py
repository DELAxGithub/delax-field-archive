"""Dropbox source proxy の純粋部分 (出力パス / ffmpeg cmd / temp) テスト。

ffmpeg は回さない。cmd 構築・パス計算・faststart フラグだけ確認する。
"""
from __future__ import annotations

import pytest

from field_shorts.proxy import (
    PROXY_HEIGHT,
    build_proxy_cmd,
    generate_proxy,
    proxy_output_path,
    reports_root,
    temp_proxy_path,
)


def test_proxy_output_path(tmp_path):
    p = proxy_output_path("DWT_EP002", "/Volumes/SSD/C0122.MP4", reports_root_dir=tmp_path)
    assert p == tmp_path / "delax-field-archive" / "DWT_EP002" / "proxy_C0122.mp4"


def test_reports_root_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DELAX_REPORTS_ROOT", str(tmp_path))
    assert reports_root() == tmp_path / "delax-field-archive"


def test_build_proxy_cmd_faststart_and_scale():
    cmd = build_proxy_cmd("/src.mp4", "/dst.mp4")
    assert "-movflags" in cmd
    assert "+faststart" in cmd
    assert f"scale=-2:{PROXY_HEIGHT}" in cmd
    assert cmd[-1] == "/dst.mp4"
    assert cmd[0] == "ffmpeg"


def test_temp_proxy_path_hidden_mp4(tmp_path):
    dest = tmp_path / "proxy_C0122.mp4"
    tmp = temp_proxy_path(dest)
    assert tmp.name.startswith(".")
    assert tmp.suffix == ".mp4"
    assert tmp.parent == dest.parent


def test_generate_proxy_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        generate_proxy("DWT_EP002", tmp_path / "nope.mp4")
