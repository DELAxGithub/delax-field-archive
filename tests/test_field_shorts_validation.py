"""clip range / telop 文字幅 (752px) の fail-closed 検証テスト。

文字幅の閾値ロジックはフォント実測に依存しない形 (max_width を渡す) で検証し、
実フォントでの spot check を 1 本だけ足す。
"""
from __future__ import annotations

import pytest

from field_shorts.validation import (
    MAX_CENTERED_WIDTH,
    MAX_DURATION_S,
    ValidationError,
    measure_text_width,
    validate_clip_range,
    validate_telop_width,
)

# 本番 render_short.py が使う実フォント (macOS)。
FONT = "/System/Library/Fonts/ヒラギノ角ゴシック W7.ttc"


class TestClipRange:
    def test_ok_with_source(self):
        validate_clip_range(5, 30, 100)

    def test_ok_without_source(self):
        validate_clip_range(0, 60)

    def test_negative_start(self):
        with pytest.raises(ValidationError):
            validate_clip_range(-1, 30)

    def test_zero_duration(self):
        with pytest.raises(ValidationError):
            validate_clip_range(0, 0)

    def test_over_max_duration(self):
        with pytest.raises(ValidationError):
            validate_clip_range(0, MAX_DURATION_S + 1)

    def test_start_at_or_after_source_end(self):
        with pytest.raises(ValidationError):
            validate_clip_range(100, 10, 100)

    def test_clip_overruns_source(self):
        with pytest.raises(ValidationError):
            validate_clip_range(90, 30, 100)

    def test_bool_is_not_a_number(self):
        with pytest.raises(ValidationError):
            validate_clip_range(True, 30)

    def test_epsilon_tolerated(self):
        # 末尾がソースを 1ms だけ超える程度は許容。
        validate_clip_range(70.0, 30.0, 100.0)


class TestTelopWidth:
    def test_threshold_logic_pass(self):
        # フォント実測値に依存せず比較ロジックだけ確認。
        assert validate_telop_width("x", FONT, 84, max_width=10_000) > 0

    def test_threshold_logic_fail(self):
        with pytest.raises(ValidationError):
            validate_telop_width("x", FONT, 84, max_width=1)

    def test_real_short_place_fits(self):
        assert validate_telop_width("マラガ", FONT, 84) <= MAX_CENTERED_WIDTH

    def test_real_long_place_overflows(self):
        with pytest.raises(ValidationError):
            validate_telop_width("あ" * 40, FONT, 84)

    def test_measure_text_width_positive(self):
        assert measure_text_width("マラガ", FONT, 84) > 0
