"""source registry (allowlist) の fail-closed テスト。

実ファイルの ~/.config には触れず、すべて tmp_path 上の registry で検証する。
"""
from __future__ import annotations

import pytest

from field_shorts.sources import (
    DEFAULT_REGISTRY_PATH,
    SourceMissing,
    SourceNotAllowed,
    SourceRegistryError,
    add_source,
    load_registry,
    resolve_source,
)


def _reg(tmp_path):
    return tmp_path / "field-shorts-sources.json"


def test_default_registry_is_outside_repo():
    # registry 実体は ~/.config 配下 = git 非追跡 (D6)。
    s = str(DEFAULT_REGISTRY_PATH)
    assert ".config" in s and "delax-field-archive" in s


def test_load_missing_is_empty_allowlist(tmp_path):
    reg = load_registry(_reg(tmp_path))
    assert reg["sources"] == {}


def test_add_then_resolve_roundtrip(tmp_path):
    src = tmp_path / "edit_master.mp4"
    src.write_bytes(b"x")
    add_source("DWT_EP002", src, path=_reg(tmp_path))
    assert resolve_source("DWT_EP002", path=_reg(tmp_path)) == src


def test_resolve_unknown_episode(tmp_path):
    with pytest.raises(SourceNotAllowed):
        resolve_source("NOPE", path=_reg(tmp_path))


def test_resolve_registered_but_file_gone(tmp_path):
    reg = {"version": 1, "sources": {"DWT_EP002": str(tmp_path / "gone.mp4")}}
    with pytest.raises(SourceMissing):
        resolve_source("DWT_EP002", registry=reg)


def test_relative_path_rejected_on_add(tmp_path):
    with pytest.raises(SourceRegistryError):
        add_source("X", "relative/path.mp4", path=_reg(tmp_path))


def test_relative_path_rejected_on_resolve():
    reg = {"version": 1, "sources": {"X": "relative.mp4"}}
    with pytest.raises(SourceRegistryError):
        resolve_source("X", registry=reg)


def test_add_dir_rejected(tmp_path):
    d = tmp_path / "adir"
    d.mkdir()
    with pytest.raises(SourceMissing):
        add_source("X", d, path=_reg(tmp_path))


def test_malformed_registry_json(tmp_path):
    p = _reg(tmp_path)
    p.write_text("{not valid json")
    with pytest.raises(SourceRegistryError):
        load_registry(p)


def test_registry_missing_sources_object(tmp_path):
    p = _reg(tmp_path)
    p.write_text('{"version": 1}')
    with pytest.raises(SourceRegistryError):
        load_registry(p)
