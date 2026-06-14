"""field adapter — 実エピソード (DWT_EP002) 読み込み + 純粋ヘルパ + fail-closed。

実データは worktree にコミット済みの episodes/ を直接読む (regression pin)。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from field_shorts.adapter import (
    FieldEpisodeError,
    compose_info,
    ep_chip,
    format_capture_date,
    load_episode,
    nearest_landmark,
)

EPISODES = Path(__file__).resolve().parent.parent / "episodes"


class TestPureHelpers:
    def test_ep_chip_numbered(self):
        assert ep_chip("DWT_EP002") == "EP002"
        assert ep_chip("DBT_EP013") == "EP013"

    def test_ep_chip_test_episode(self):
        assert ep_chip("TEST_malaga-coastal_2026-05-11") == "TEST"

    def test_format_capture_date(self):
        assert format_capture_date("2026-05-04") == "2026.05.04"
        assert format_capture_date("") == ""
        assert format_capture_date("garbage") == ""

    def test_compose_info(self):
        assert compose_info("Málaga", "Spain", "2026-05-04") == "Málaga · Spain · 2026.05.04"
        assert compose_info("Málaga", "", "") == "Málaga"
        assert compose_info("", "", "") == ""

    def test_nearest_landmark(self):
        lms = ((0.0, "A"), (300.0, "B"), (900.0, "C"))
        assert nearest_landmark(lms, 0) == "A"
        assert nearest_landmark(lms, 500) == "B"
        assert nearest_landmark(lms, 5000) == "C"
        assert nearest_landmark((), 10) is None

    def test_nearest_landmark_before_first(self):
        # t がどの landmark にも先行されないとき → 先頭にフォールバック
        lms = ((300.0, "B"), (900.0, "C"))
        assert nearest_landmark(lms, 100) == "B"


class TestLoadRealEpisode:
    def test_dwt_ep002_shape(self):
        ep = load_episode(EPISODES, "DWT_EP002")
        assert ep.id == "DWT_EP002"
        assert ep.series == "DWT"
        assert ep.series_label == "DELAX Walking Tour"
        assert ep.ep_chip == "EP002"
        assert ep.city == "Málaga"
        assert ep.country == "Spain"
        assert len(ep.highlights) == 3

    def test_dwt_ep002_first_highlight(self):
        ep = load_episode(EPISODES, "DWT_EP002")
        h0 = ep.highlights[0]
        assert h0.timestamp_sec == 30
        assert h0.duration_sec == 60
        assert h0.suggested_platform == "shorts"
        assert h0.default_info == "Málaga · Spain · 2026.05.04"
        assert h0.default_place  # geo 由来で非空

    def test_render_args_defaults(self):
        ep = load_episode(EPISODES, "DWT_EP002")
        h0 = ep.highlights[0]
        args = ep.render_args(h0)
        assert args["episode_id"] == "DWT_EP002"
        assert args["series_label"] == "DELAX Walking Tour"
        assert args["ep_chip"] == "EP002"
        assert args["start"] == 30.0
        assert args["duration"] == 60.0
        assert args["location_primary"] == h0.default_place
        assert args["location_secondary"] == h0.default_info

    def test_render_args_overrides(self):
        ep = load_episode(EPISODES, "DWT_EP002")
        h0 = ep.highlights[0]
        args = ep.render_args(h0, place="マラガ", info="custom", start=12, duration=45)
        assert args["location_primary"] == "マラガ"
        assert args["location_secondary"] == "custom"
        assert args["start"] == 12.0
        assert args["duration"] == 45.0


class TestFailClosed:
    def test_missing_yaml(self, tmp_path):
        with pytest.raises(FieldEpisodeError):
            load_episode(tmp_path, "NOPE")

    def test_id_mismatch(self, tmp_path):
        d = tmp_path / "DWT_EP999"
        d.mkdir()
        (d / "episode.yaml").write_text("id: WRONG\nseries: DWT\n", encoding="utf-8")
        with pytest.raises(FieldEpisodeError):
            load_episode(tmp_path, "DWT_EP999")

    def test_not_a_mapping(self, tmp_path):
        d = tmp_path / "X"
        d.mkdir()
        (d / "episode.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
        with pytest.raises(FieldEpisodeError):
            load_episode(tmp_path, "X")
