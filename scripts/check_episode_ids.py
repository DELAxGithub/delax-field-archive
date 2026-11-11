#!/usr/bin/env python3
"""episodes/*/episode.yaml の id がディレクトリ名と一致し、重複しないことを検査する。

CLAUDE.md「エピソードIDの重複を検知したら必ず指摘する」の機械チェック。
`_` 始まりのディレクトリ (テンプレート) は対象外。YAML ライブラリ不要 (top-level の `id:` のみ読む)。
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

ID_RE = re.compile(r"^id:\s*([^\s#]+)", re.MULTILINE)


def check(episodes_dir: Path) -> list[str]:
    problems: list[str] = []
    seen: dict[str, str] = {}
    for d in sorted(p for p in episodes_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
        f = d / "episode.yaml"
        if not f.is_file():
            problems.append(f"{d.name}: episode.yaml がない")
            continue
        m = ID_RE.search(f.read_text(encoding="utf-8"))
        if not m:
            problems.append(f"{d.name}: id: が見つからない")
            continue
        eid = m.group(1).strip("\"'")
        if eid != d.name:
            problems.append(f"{d.name}: id ({eid}) がディレクトリ名と一致しない")
        if eid in seen:
            problems.append(f"{d.name}: id ({eid}) が {seen[eid]} と重複")
        seen[eid] = d.name
    return problems


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent / "episodes"
    found = check(root)
    for line in found:
        print(f"check_episode_ids: {line}", file=sys.stderr)
    sys.exit(1 if found else 0)
