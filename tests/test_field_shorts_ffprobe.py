"""ffprobe ラッパの純粋述語 + verify_video の fail-closed 判定テスト。

ffprobe バイナリを呼ばずに済むよう、parsed=<dict> 注入で検証ロジックだけ叩く。
"""
from __future__ import annotations

import pytest

from field_shorts.ffprobe import (
    ProbeError,
    duration_of,
    has_video_stream,
    probe,
    verify_video,
)

VIDEO = {
    "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
    "format": {"duration": "30.05"},
}
AUDIO_ONLY = {"streams": [{"codec_type": "audio"}], "format": {"duration": "30.0"}}


def test_has_video_stream():
    assert has_video_stream(VIDEO)
    assert not has_video_stream(AUDIO_ONLY)
    assert not has_video_stream({})


def test_duration_of():
    assert duration_of(VIDEO) == 30.05
    assert duration_of({"format": {}}) is None
    assert duration_of({"format": {"duration": "bad"}}) is None


def test_verify_ok():
    assert verify_video("ignored", expect_duration=30, parsed=VIDEO) is VIDEO


def test_verify_no_video_stream():
    with pytest.raises(ProbeError):
        verify_video("x", parsed=AUDIO_ONLY)


def test_verify_duration_mismatch():
    with pytest.raises(ProbeError):
        verify_video("x", expect_duration=60, parsed=VIDEO)


def test_verify_duration_within_tolerance():
    # 30.05 vs 29.0 = 1.05s < 1.5s
    verify_video("x", expect_duration=29.0, tolerance=1.5, parsed=VIDEO)


def test_verify_missing_duration_when_expected():
    with pytest.raises(ProbeError):
        verify_video("x", expect_duration=30, parsed={"streams": [{"codec_type": "video"}]})


def test_probe_missing_file(tmp_path):
    with pytest.raises(ProbeError):
        probe(tmp_path / "nope.mp4")
