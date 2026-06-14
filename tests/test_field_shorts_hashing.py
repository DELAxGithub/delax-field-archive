"""dropbox_content_hash の byte 一致テスト。

期待値はテスト側で独立に (Dropbox の content-hash アルゴリズムを手で組んで)
計算し、実装と突き合わせる。実装をそのままなぞる tautology を避ける。
"""
from __future__ import annotations

import hashlib

import pytest

from field_shorts.hashing import DROPBOX_BLOCK, dropbox_content_hash


def test_single_block(tmp_path):
    data = b"hello field shorts"
    f = tmp_path / "a.bin"
    f.write_bytes(data)
    expected = hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()
    assert dropbox_content_hash(f) == expected


def test_exact_block_boundary(tmp_path):
    block = b"\xaa" * DROPBOX_BLOCK
    f = tmp_path / "c.bin"
    f.write_bytes(block)
    expected = hashlib.sha256(hashlib.sha256(block).digest()).hexdigest()
    assert dropbox_content_hash(f) == expected


def test_spans_two_blocks(tmp_path):
    b0 = b"\x01" * DROPBOX_BLOCK
    b1 = b"\x02" * 123
    f = tmp_path / "b.bin"
    f.write_bytes(b0 + b1)
    expected = hashlib.sha256(
        hashlib.sha256(b0).digest() + hashlib.sha256(b1).digest()
    ).hexdigest()
    assert dropbox_content_hash(f) == expected


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        dropbox_content_hash(tmp_path / "nope.bin")
