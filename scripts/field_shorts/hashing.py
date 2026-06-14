"""Byte-exact hashing shared with the tachi pipeline.

`dropbox_content_hash` mirrors, byte-for-byte:
  ~/src/90_サイドワーク/たっちレディオショート/pipeline/scripts/lib/web_youtube.py
    :dropbox_content_hash
and Dropbox's documented content-hash
  https://www.dropbox.com/developers/reference/content-hash

Keeping the algorithm identical means the field Web/poller/uploader can verify a
rendered short's bytes against the Dropbox-synced completed video exactly the way
the tachi pipeline already does — the same record format, the same guarantee.

Only stdlib (hashlib) — safe to import from the render path (`uv run --with pillow`).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

# Dropbox hashes in 4 MiB blocks: sha256 over the concatenated per-block sha256
# digests. Must stay 4*1024*1024 to match Dropbox + tachi.
DROPBOX_BLOCK = 4 * 1024 * 1024


def dropbox_content_hash(path: str | Path) -> str:
    """Dropbox content_hash of a local file. Streams in 4 MiB blocks (never loads
    the whole mp4). Raises FileNotFoundError if absent (caller fails closed)."""
    path = Path(path)
    block_digests = b""
    with open(path, "rb") as f:
        while True:
            chunk = f.read(DROPBOX_BLOCK)
            if not chunk:
                break
            block_digests += hashlib.sha256(chunk).digest()
    return hashlib.sha256(block_digests).hexdigest()
