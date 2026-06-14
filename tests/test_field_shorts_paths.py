"""path-safety: safe_path_component (traversal 拒否) + same_file (元素材保護)。"""
from __future__ import annotations

import pytest

from field_shorts.paths import UnsafePathComponent, safe_path_component, same_file


class TestSafePathComponent:
    def test_ok(self):
        assert safe_path_component("DWT_EP002") == "DWT_EP002"
        assert (
            safe_path_component("TEST_malaga-coastal_2026-05-11")
            == "TEST_malaga-coastal_2026-05-11"
        )

    @pytest.mark.parametrize(
        "bad",
        ["..", ".", "../etc", "a/b", "a\\b", "", "   ", "x..y", "a/../b", "\x00x"],
    )
    def test_rejects(self, bad):
        with pytest.raises(UnsafePathComponent):
            safe_path_component(bad)

    def test_non_string(self):
        with pytest.raises(UnsafePathComponent):
            safe_path_component(None)


class TestSameFile:
    def test_identical(self, tmp_path):
        f = tmp_path / "a.mp4"
        f.write_bytes(b"x")
        assert same_file(f, f)

    def test_different(self, tmp_path):
        a = tmp_path / "a.mp4"
        a.write_bytes(b"x")
        b = tmp_path / "b.mp4"
        b.write_bytes(b"y")
        assert not same_file(a, b)

    def test_nonexistent_resolve_equal(self, tmp_path):
        p = tmp_path / "x.mp4"
        assert same_file(p, tmp_path / "x.mp4")
        assert not same_file(p, tmp_path / "y.mp4")

    def test_symlink_alias(self, tmp_path):
        real = tmp_path / "real.mp4"
        real.write_bytes(b"x")
        link = tmp_path / "link.mp4"
        link.symlink_to(real)
        assert same_file(real, link)
