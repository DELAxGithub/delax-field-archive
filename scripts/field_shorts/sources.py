"""Source registry — the local allowlist that resolves `episode_id → source path`.

D6 (handover 2026-06-14): the original video path is NEVER carried in a render
job. The Web enqueues `{episode_id, edit overlay sha}`; the Mac-side poller turns
`episode_id` into an absolute source path HERE, via an operator-maintained
allowlist that lives OUTSIDE git:

    ~/.config/delax-field-archive/field-shorts-sources.json
    {
      "version": 1,
      "sources": { "DWT_EP002": "/Volumes/Sony_Vlog/2026-05-04/edit_master.mp4" }
    }

Absolute paths only, never committed. Fail-closed: an episode not in the
allowlist (`SourceNotAllowed`) or whose file is gone (`SourceMissing`) raises —
the poller refuses the job rather than guessing a path.

Only stdlib (json) — safe to import anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_REGISTRY_PATH = (
    Path.home() / ".config" / "delax-field-archive" / "field-shorts-sources.json"
)
REGISTRY_VERSION = 1


class SourceRegistryError(Exception):
    """The registry file itself is malformed/unreadable."""


class SourceNotAllowed(SourceRegistryError):
    """episode_id is not in the allowlist — refuse the job."""


class SourceMissing(SourceRegistryError):
    """episode_id is allowlisted but its file is absent on disk."""


def load_registry(path: str | Path | None = None) -> dict:
    """Load the registry. A NON-EXISTENT file is an empty allowlist (not an
    error). A present-but-malformed file raises (fail closed)."""
    target = Path(path) if path else DEFAULT_REGISTRY_PATH
    if not target.exists():
        return {"version": REGISTRY_VERSION, "sources": {}}
    try:
        obj = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise SourceRegistryError(f"registry {target} is not valid JSON: {e}") from e
    if not isinstance(obj, dict) or not isinstance(obj.get("sources"), dict):
        raise SourceRegistryError(
            f"registry {target} is malformed (expected a 'sources' object)"
        )
    # 未知の version を黙って受理しない (将来のスキーマ変更を素通りさせない)。
    version = obj.get("version")
    if version != REGISTRY_VERSION:
        raise SourceRegistryError(
            f"registry {target} has unsupported version {version!r} "
            f"(expected {REGISTRY_VERSION})"
        )
    return obj


def resolve_source(
    episode_id: str,
    *,
    path: str | Path | None = None,
    registry: dict | None = None,
) -> Path:
    """Resolve `episode_id` to an existing absolute source Path, or raise.

    `registry` injects a parsed allowlist (tests / a poller that already loaded
    it); otherwise the file at `path` (default `~/.config/...`) is read."""
    reg = registry if registry is not None else load_registry(path)
    where = path or DEFAULT_REGISTRY_PATH
    sources = reg.get("sources", {})
    if not isinstance(sources, dict):
        raise SourceRegistryError(f"registry {where} 'sources' is not an object")

    raw = sources.get(episode_id)
    if raw is None:
        raise SourceNotAllowed(
            f"episode {episode_id!r} is not in the source allowlist ({where}); "
            f"register it with add_source() before queueing a render"
        )
    if not isinstance(raw, str) or not raw.strip():
        raise SourceRegistryError(
            f"episode {episode_id!r} has an empty/non-string source path"
        )

    resolved = Path(raw).expanduser()
    if not resolved.is_absolute():
        raise SourceRegistryError(
            f"registry path for {episode_id!r} must be absolute (got {raw!r})"
        )
    if not resolved.exists():
        raise SourceMissing(f"source for {episode_id!r} not found on disk: {resolved}")
    if not resolved.is_file():
        raise SourceMissing(f"source for {episode_id!r} is not a file: {resolved}")
    return resolved


def add_source(
    episode_id: str,
    source_path: str | Path,
    *,
    path: str | Path | None = None,
) -> dict:
    """Register an absolute, existing source path for `episode_id` and persist the
    registry (atomic write, creating `~/.config/...`). Returns the updated dict.
    Raises if the path is relative or absent — only real files enter the allowlist."""
    src = Path(source_path).expanduser()
    if not src.is_absolute():
        raise SourceRegistryError(
            f"source path must be absolute (got {source_path!r})"
        )
    if not src.is_file():
        raise SourceMissing(f"source path does not exist or is not a file: {src}")

    target = Path(path) if path else DEFAULT_REGISTRY_PATH
    reg = load_registry(target)
    reg["version"] = reg.get("version", REGISTRY_VERSION)
    reg.setdefault("sources", {})
    reg["sources"][episode_id] = str(src)

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_text(
        json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(target)  # atomic on the same directory/fs
    return reg
