"""Codex review (2026-06-14, NEEDS_REVISION) P1–P5 の回帰テスト。

P1 元素材上書き / P2 episode_id パストラバーサル / P3 非有限値 (NaN/Inf) /
P4 既定テロップ幅超過 / P5 schema 不正の黙認。各々を独立に固定する。
"""
from __future__ import annotations

from pathlib import Path

import pytest

import render_short
from field_shorts.adapter import FieldEpisodeError, load_episode
from field_shorts.ffprobe import ProbeError, duration_of, verify_video
from field_shorts.paths import UnsafePathComponent
from field_shorts.sources import SourceRegistryError, load_registry
from field_shorts.validation import (
    MAX_CENTERED_WIDTH,
    TELOP_PRIMARY_FONT,
    TELOP_PRIMARY_SIZE,
    TELOP_SECONDARY_FONT,
    TELOP_SECONDARY_SIZE,
    ValidationError,
    measure_text_width,
    validate_clip_range,
    validate_cta_duration,
)

EPISODES = Path(__file__).resolve().parent.parent / "episodes"
REAL_EPISODES = [
    "DWT_EP001",
    "DWT_EP002",
    "TEST_malaga-coastal_2026-05-11",
    "TEST_marseille2_2026-04-02",
]


# ── P1: --output が --source を踏み潰さない ──────────────────────────────
class TestP1SourceOverwrite:
    def test_same_file_rejected(self, tmp_path):
        f = tmp_path / "footage.mp4"
        f.write_bytes(b"x")
        with pytest.raises(ValueError):
            render_short.ensure_output_distinct_from_source(f, f)

    def test_distinct_ok(self, tmp_path):
        src = tmp_path / "src.mp4"
        src.write_bytes(b"x")
        render_short.ensure_output_distinct_from_source(src, tmp_path / "out.mp4")

    def test_symlinked_output_rejected(self, tmp_path):
        src = tmp_path / "src.mp4"
        src.write_bytes(b"x")
        link = tmp_path / "alias.mp4"
        link.symlink_to(src)
        with pytest.raises(ValueError):
            render_short.ensure_output_distinct_from_source(src, link)


# ── P2: episode_id のパストラバーサル ──────────────────────────────────
class TestP2PathTraversal:
    def test_default_output_path_rejects(self):
        with pytest.raises(UnsafePathComponent):
            render_short.default_output_path(Path("/src.mp4"), "../escape")

    def test_load_episode_rejects_traversal(self, tmp_path):
        with pytest.raises(UnsafePathComponent):
            load_episode(tmp_path, "../secrets")

    def test_load_episode_rejects_separator(self, tmp_path):
        with pytest.raises(UnsafePathComponent):
            load_episode(tmp_path, "a/b")

    def test_proxy_output_path_rejects(self, tmp_path):
        from field_shorts.proxy import proxy_output_path

        with pytest.raises(UnsafePathComponent):
            proxy_output_path("../escape", "/src.mp4", reports_root_dir=tmp_path)


# ── P3: 非有限値 (NaN / Infinity) ──────────────────────────────────────
class TestP3NonFinite:
    def test_nan_start(self):
        with pytest.raises(ValidationError):
            validate_clip_range(float("nan"), 30)

    def test_inf_duration(self):
        with pytest.raises(ValidationError):
            validate_clip_range(0, float("inf"))

    def test_nan_source_duration(self):
        with pytest.raises(ValidationError):
            validate_clip_range(0, 30, float("nan"))

    def test_duration_of_rejects_non_finite(self):
        assert duration_of({"format": {"duration": "nan"}}) is None
        assert duration_of({"format": {"duration": "inf"}}) is None

    def test_verify_video_nan_duration(self):
        parsed = {"streams": [{"codec_type": "video"}], "format": {"duration": "nan"}}
        with pytest.raises(ProbeError):
            verify_video("x", expect_duration=30, parsed=parsed)

    def test_cta_duration_ok(self):
        validate_cta_duration(5, 30)

    def test_cta_duration_exceeds_clip(self):
        with pytest.raises(ValidationError):
            validate_cta_duration(40, 30)

    def test_cta_duration_nan(self):
        with pytest.raises(ValidationError):
            validate_cta_duration(float("nan"), 30)

    def test_cta_duration_zero(self):
        with pytest.raises(ValidationError):
            validate_cta_duration(0, 30)


# ── P4: 実データの既定テロップが全て 752px に収まる ─────────────────────
class TestP4DefaultTelopWidth:
    def test_every_real_default_fits(self):
        for ep_id in REAL_EPISODES:
            ep = load_episode(EPISODES, ep_id)
            for h in ep.highlights:
                if h.default_place:
                    w = measure_text_width(
                        h.default_place, TELOP_PRIMARY_FONT, TELOP_PRIMARY_SIZE
                    )
                    assert w <= MAX_CENTERED_WIDTH, (
                        f"{ep_id} h{h.index} place {h.default_place!r} = {w:.0f}px"
                    )
                if h.default_info:
                    w = measure_text_width(
                        h.default_info, TELOP_SECONDARY_FONT, TELOP_SECONDARY_SIZE
                    )
                    assert w <= MAX_CENTERED_WIDTH, (
                        f"{ep_id} h{h.index} info {h.default_info!r} = {w:.0f}px"
                    )

    def test_ep002_h0_falls_back_from_overlong_landmark(self):
        ep = load_episode(EPISODES, "DWT_EP002")
        place = ep.highlights[0].default_place
        # 'Calle Bolivia / Baños del Carmen' (~1528px) は既定値に選ばれない
        assert place != "Calle Bolivia / Baños del Carmen"
        assert (
            measure_text_width(place, TELOP_PRIMARY_FONT, TELOP_PRIMARY_SIZE)
            <= MAX_CENTERED_WIDTH
        )


# ── P5: schema 不正を黙って補正しない ──────────────────────────────────
class TestP5SchemaStrictness:
    def test_registry_unknown_version(self, tmp_path):
        p = tmp_path / "reg.json"
        p.write_text('{"version": 2, "sources": {}}', encoding="utf-8")
        with pytest.raises(SourceRegistryError):
            load_registry(p)

    def test_registry_missing_version(self, tmp_path):
        p = tmp_path / "reg.json"
        p.write_text('{"sources": {}}', encoding="utf-8")
        with pytest.raises(SourceRegistryError):
            load_registry(p)

    def test_malformed_timestamp_raises(self, tmp_path):
        d = tmp_path / "DWT_EP500"
        d.mkdir()
        (d / "episode.yaml").write_text(
            "id: DWT_EP500\nseries: DWT\ncreative:\n  highlight_moments:\n"
            "    - description: x\n      timestamp_sec: abc\n      duration_sec: 60\n",
            encoding="utf-8",
        )
        with pytest.raises(FieldEpisodeError):
            load_episode(tmp_path, "DWT_EP500")

    def test_nan_duration_raises(self, tmp_path):
        d = tmp_path / "DWT_EP501"
        d.mkdir()
        (d / "episode.yaml").write_text(
            "id: DWT_EP501\nseries: DWT\ncreative:\n  highlight_moments:\n"
            "    - description: x\n      timestamp_sec: 0\n      duration_sec: .nan\n",
            encoding="utf-8",
        )
        with pytest.raises(FieldEpisodeError):
            load_episode(tmp_path, "DWT_EP501")

    def test_unedited_none_duration_still_loads(self):
        # 未編集プレースホルダ (duration 未設定) は malformed ではない → 読めてよい
        ep = load_episode(EPISODES, "TEST_malaga-coastal_2026-05-11")
        assert ep.highlights[0].duration_sec is None
        assert ep.highlights[0].timestamp_sec == 0.0


# ── 既定フォント定数のドリフト pin (adapter フィット = render 幅検証) ──────
def test_telop_font_constants_match_render_short():
    assert render_short.FONT_BOLD == TELOP_PRIMARY_FONT
    assert render_short.LOCATION_PRIMARY_FONT == TELOP_PRIMARY_SIZE
    assert render_short.FONT_LIGHT == TELOP_SECONDARY_FONT
    assert render_short.LOCATION_SECONDARY_FONT == TELOP_SECONDARY_SIZE
