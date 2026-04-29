"""render_long.py の BGM 選曲 / filter chain pure 関数テスト。"""
from __future__ import annotations
import json
from pathlib import Path

import pytest

from render_long import (
    BGM_CROSSFADE_S,
    select_bgm_tracks,
    build_bgm_filter_chain,
)


def _write_catalog(library: Path, tracks: list[dict]) -> None:
    library.mkdir(parents=True, exist_ok=True)
    (library / "_catalog.json").write_text(json.dumps(tracks))


class TestSelectBgmTracks:
    def test_empty_catalog_exits(self, tmp_path: Path):
        _write_catalog(tmp_path, [])
        with pytest.raises(SystemExit):
            select_bgm_tracks(tmp_path, total_duration_s=600.0,
                              genres=("lofi",), seed=0)

    def test_short_tracks_filtered_out(self, tmp_path: Path):
        # 全曲が crossfade × 1.5 (= 7.5s) 未満 → 候補ゼロで SystemExit
        _write_catalog(tmp_path, [
            {"path": "a.wav", "genre": "lofi", "duration_sec": 3.0,
             "intro_silence_ms": 0},
            {"path": "b.wav", "genre": "lofi", "duration_sec": 5.0,
             "intro_silence_ms": 0},
        ])
        with pytest.raises(SystemExit):
            select_bgm_tracks(tmp_path, total_duration_s=600.0,
                              genres=("lofi",), seed=0)

    def test_normal_selection_fills_duration(self, tmp_path: Path):
        _write_catalog(tmp_path, [
            {"path": f"track-{i}.wav", "genre": "lofi", "duration_sec": 60.0,
             "intro_silence_ms": 0}
            for i in range(5)
        ])
        tracks = select_bgm_tracks(tmp_path, total_duration_s=300.0,
                                    genres=("lofi",), seed=0)
        # 各曲は 60s − 5s crossfade = 55s 寄与。5曲で 275s、6曲で 330s
        assert len(tracks) >= 5
        # 詰め込みすぎていないか (10000 上限の暴走でないこと)
        assert len(tracks) < 100

    def test_intro_silence_filter(self, tmp_path: Path):
        # intro_silence_ms >= 1500 は除外される
        _write_catalog(tmp_path, [
            {"path": "noisy.wav", "genre": "lofi", "duration_sec": 60.0,
             "intro_silence_ms": 2000},
        ])
        with pytest.raises(SystemExit):
            select_bgm_tracks(tmp_path, total_duration_s=120.0,
                              genres=("lofi",), seed=0)

    def test_genre_filter(self, tmp_path: Path):
        _write_catalog(tmp_path, [
            {"path": "j.wav", "genre": "jazz", "duration_sec": 60.0,
             "intro_silence_ms": 0},
        ])
        # genres に jazz が含まれていなければ候補ゼロ
        with pytest.raises(SystemExit):
            select_bgm_tracks(tmp_path, total_duration_s=120.0,
                              genres=("lofi",), seed=0)

    def test_seed_reproducibility(self, tmp_path: Path):
        _write_catalog(tmp_path, [
            {"path": f"track-{i}.wav", "genre": "lofi", "duration_sec": 60.0,
             "intro_silence_ms": 0}
            for i in range(10)
        ])
        a = select_bgm_tracks(tmp_path, total_duration_s=300.0,
                               genres=("lofi",), seed=42)
        b = select_bgm_tracks(tmp_path, total_duration_s=300.0,
                               genres=("lofi",), seed=42)
        # 同じ seed なら順序まで再現
        assert [t["path"] for t in a] == [t["path"] for t in b]


class TestBuildBgmFilterChain:
    def test_single_track(self):
        tracks = [{"path": "a.wav", "duration_sec": 60.0}]
        filter_str, label = build_bgm_filter_chain(tracks, video_duration_s=60.0,
                                                    input_offset=2)
        assert label  # ラベル名は実装側で決まるが、空でない
        # 入力 [2:a] が aformat 経由で a0 にマップされる
        assert "[2:a]" in filter_str
        assert "[a0]" in filter_str

    def test_multi_track_acrossfade(self):
        tracks = [
            {"path": "a.wav", "duration_sec": 60.0},
            {"path": "b.wav", "duration_sec": 60.0},
            {"path": "c.wav", "duration_sec": 60.0},
        ]
        filter_str, _ = build_bgm_filter_chain(tracks, video_duration_s=180.0,
                                                input_offset=2)
        # acrossfade が n-1 回現れる
        assert filter_str.count("acrossfade") == 2
        # crossfade duration が定数と一致
        assert f"d={BGM_CROSSFADE_S}" in filter_str

    def test_zero_track_exits(self):
        with pytest.raises(SystemExit):
            build_bgm_filter_chain([], video_duration_s=60.0, input_offset=2)
