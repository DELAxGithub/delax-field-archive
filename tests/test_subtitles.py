"""generate_subtitles.py の SRT 整形 pure 関数テスト。"""
from __future__ import annotations

from generate_subtitles import srt_timestamp, segments_to_srt


class TestSrtTimestamp:
    def test_zero(self):
        assert srt_timestamp(0.0) == "00:00:00,000"

    def test_milliseconds(self):
        assert srt_timestamp(0.5) == "00:00:00,500"

    def test_minutes_seconds(self):
        assert srt_timestamp(125.25) == "00:02:05,250"

    def test_hours(self):
        assert srt_timestamp(3725.0) == "01:02:05,000"


class TestSegmentsToSrt:
    def test_single_cue(self):
        srt = segments_to_srt([{"start": 0.0, "end": 2.5, "text": "Hello world"}])
        # 1行目: cue 番号、2行目: 範囲、3行目: テキスト
        lines = srt.split("\n")
        assert lines[0] == "1"
        assert "-->" in lines[1]
        assert lines[2] == "Hello world"

    def test_multiple_cues_separated_by_blank_line(self):
        segs = [
            {"start": 0.0, "end": 1.0, "text": "first"},
            {"start": 1.0, "end": 2.0, "text": "second"},
        ]
        srt = segments_to_srt(segs)
        # SRT の cue 区切りは空行 (\n\n)
        assert "\n\n" in srt
        assert "first" in srt
        assert "second" in srt

    def test_empty_text_is_skipped(self):
        segs = [
            {"start": 0.0, "end": 1.0, "text": "  "},
            {"start": 1.0, "end": 2.0, "text": "real"},
        ]
        srt = segments_to_srt(segs)
        assert "real" in srt
        # 空文字 cue は番号も含めスキップ
        assert "1\n" in srt and "real" in srt
        # 空白だけ cue は出力されない
        assert srt.count("-->") == 1
