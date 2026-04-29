"""generate_description.py の chapter / fmt_ts まわり pure 関数テスト。"""
from __future__ import annotations
import textwrap
from pathlib import Path

from generate_description import fmt_ts, parse_chapters_metadata, build_chapter_block


class TestFmtTs:
    def test_under_one_minute(self):
        assert fmt_ts(0) == "00:00"
        assert fmt_ts(45) == "00:45"

    def test_minutes_only(self):
        assert fmt_ts(60) == "01:00"
        assert fmt_ts(905) == "15:05"

    def test_hours_format_kicks_in(self):
        assert fmt_ts(3600) == "1:00:00"
        assert fmt_ts(3661) == "1:01:01"


class TestParseChaptersMetadata:
    def test_parses_ffmetadata_block(self, tmp_path: Path):
        metadata_path = tmp_path / "chapters.txt"
        metadata_path.write_text(textwrap.dedent("""\
            ;FFMETADATA1
            [CHAPTER]
            TIMEBASE=1/1000
            START=0
            END=30000
            title=Opening
            [CHAPTER]
            TIMEBASE=1/1000
            START=30000
            END=120000
            title=Old town
        """))
        chapters = parse_chapters_metadata(metadata_path)
        assert chapters == [(0.0, "Opening"), (30.0, "Old town")]

    def test_returns_empty_when_no_chapters(self, tmp_path: Path):
        empty = tmp_path / "empty.txt"
        empty.write_text(";FFMETADATA1\n")
        assert parse_chapters_metadata(empty) == []


class TestBuildChapterBlock:
    def test_first_chapter_clamped_to_zero(self):
        chapters = [(2.5, "Intro"), (60.0, "Plaza"), (180.0, "Cathedral")]
        out = build_chapter_block(chapters)
        first = out.splitlines()[0]
        assert first.startswith("00:00 ") or first.startswith("0:00 ")

    def test_dedup_under_10s_gap(self):
        chapters = [(0.0, "Start"), (5.0, "Skipme"), (60.0, "OK")]
        lines = build_chapter_block(chapters).splitlines()
        # 5秒で間隔不足の "Skipme" は落ちる
        assert "Skipme" not in build_chapter_block(chapters)
        assert any("OK" in line for line in lines)

    def test_empty_chapters_falls_back(self):
        assert build_chapter_block([]) == "00:00 Opening"

    def test_prepends_zero_chapter_when_missing(self):
        chapters = [(15.0, "Late start")]
        out = build_chapter_block(chapters)
        assert out.startswith("00:00 ")
