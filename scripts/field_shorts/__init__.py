"""field_shorts — Slice 1 基盤パッケージ (field-archive ショート オンライン化)。

意図的に **何も eager import しない**。render_short.py は
`field_shorts.validation` / `.ffprobe` / `.hashing` だけを取り込んで
`uv run --with pillow` のまま動く必要があるため、ここで `.adapter`
(PyYAML 依存) を import すると render パスに余計な依存が混入する。
各モジュールは利用側が個別に `from field_shorts.<mod> import ...` する。

設計: ~/src/devlog/handover/2026-06-14-field-shorts-online-codex-request.md (Slice 1)
"""
