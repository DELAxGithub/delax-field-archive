from pathlib import Path

from check_episode_ids import check


def _ep(root: Path, name: str, eid: str) -> None:
    (root / name).mkdir()
    (root / name / "episode.yaml").write_text(f"id: {eid}   # comment\nseries: DWT\n", encoding="utf-8")


def test_ok_and_template_ignored(tmp_path):
    _ep(tmp_path, "DWT_EP001", "DWT_EP001")
    _ep(tmp_path, "_template", "DWT_EP000")
    assert check(tmp_path) == []


def test_mismatch_and_duplicate(tmp_path):
    _ep(tmp_path, "DWT_EP001", "DWT_EP001")
    _ep(tmp_path, "DWT_EP002", "DWT_EP001")
    problems = check(tmp_path)
    assert any("一致しない" in p for p in problems)
    assert any("重複" in p for p in problems)


def test_missing_yaml(tmp_path):
    (tmp_path / "DWT_EP003").mkdir()
    assert check(tmp_path) == ["DWT_EP003: episode.yaml がない"]
