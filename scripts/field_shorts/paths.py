"""Path-safety helpers shared across the field-shorts pipeline.

`safe_path_component` is the single validator for any value (episode_id today, a
job's episode field tomorrow) that gets concatenated into an output path — it
rejects separators and `..` so a crafted id can't escape the reports/episodes
root. `same_file` is the guard that keeps a render from overwriting its own
source. Only stdlib — safe to import from the render path.
"""
from __future__ import annotations

from pathlib import Path

_ILLEGAL = ("/", "\\", "\x00")


class UnsafePathComponent(ValueError):
    """A value that would escape its intended directory if used as a path part."""


def safe_path_component(name: str, *, label: str = "path component") -> str:
    """Return `name` unchanged if it is a single safe path segment, else raise.
    Rejects empties, `.`/`..`, any `..` substring, and path separators / NUL."""
    if not isinstance(name, str) or not name.strip():
        raise UnsafePathComponent(f"{label} must be a non-empty string (got {name!r})")
    if name in (".", ".."):
        raise UnsafePathComponent(f"{label} {name!r} is not allowed")
    if ".." in name:
        raise UnsafePathComponent(f"{label} {name!r} contains '..'")
    for ch in _ILLEGAL:
        if ch in name:
            raise UnsafePathComponent(
                f"{label} {name!r} contains an illegal character {ch!r}"
            )
    return name


def same_file(a: str | Path, b: str | Path) -> bool:
    """True if `a` and `b` point at the same file. Uses os.path.samefile when both
    exist (catches symlink/hardlink aliasing), else compares resolved paths so a
    not-yet-created output is still caught."""
    pa, pb = Path(a), Path(b)
    try:
        if pa.exists() and pb.exists() and pa.samefile(pb):
            return True
    except OSError:
        pass
    return pa.resolve() == pb.resolve()
