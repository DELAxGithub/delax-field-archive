"""Field Telop render-queue I/O client (Phase 7).

An injectable client abstracts the render-queue branch so the runner is testable
without GitHub: `GhQueueClient` (real `gh api`) in production, `FakeQueueClient`
(in-memory) in tests / `--dry-run`.

Layout on the render-queue branch (data-only, field-telop/ prefix):
    field-telop/jobs/approved-ready/<job_id>.json   render-eligible (approve CLI push)
    field-telop/jobs/running/<job_id>.json          claimed by the runner
    field-telop/jobs/done|failed/<job_id>.json       terminal
    field-telop/manifests-approved/<episode_id>/<content_hash>.json  approved manifest
    field-telop/results/<job_id>.json                runner result
The Web's pending jobs (field-telop/jobs/pending/) are NOT read by the runner.
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import time
from typing import Protocol

_HTTP_5XX = re.compile(r"HTTP 5\d\d")

QUEUE_PREFIX = "field-telop"
JOBS_DIR = f"{QUEUE_PREFIX}/jobs"
MANIFESTS_APPROVED_DIR = f"{QUEUE_PREFIX}/manifests-approved"
RESULTS_DIR = f"{QUEUE_PREFIX}/results"

RENDER_STATUSES = ("approved-ready", "running", "done", "failed")


def job_path(status: str, job_id: str) -> str:
    if status not in RENDER_STATUSES:
        raise ValueError(f"bad job status dir: {status}")
    return f"{JOBS_DIR}/{status}/{job_id}.json"


def approved_manifest_path(episode_id: str, content_hash: str) -> str:
    return f"{MANIFESTS_APPROVED_DIR}/{episode_id}/{content_hash}.json"


def result_path(job_id: str) -> str:
    return f"{RESULTS_DIR}/{job_id}.json"


class QueueError(Exception):
    """Queue I/O failure — fail closed."""


class QueueClient(Protocol):
    def read_json(self, path: str) -> dict | None: ...
    def write_json(self, path: str, data: dict, message: str) -> None: ...
    def delete(self, path: str, message: str) -> None: ...
    def list_names(self, dir_path: str) -> list[str]: ...


# ── in-memory fake (tests / dry-run) ─────────────────────────────────────────
class FakeQueueClient:
    """In-memory QueueClient — no network. Holds {path: dict}."""

    def __init__(self, files: dict[str, dict] | None = None):
        self.files: dict[str, dict] = dict(files or {})
        self.writes: list[str] = []
        self.deletes: list[str] = []

    def read_json(self, path: str) -> dict | None:
        v = self.files.get(path)
        return json.loads(json.dumps(v)) if v is not None else None  # deep copy

    def write_json(self, path: str, data: dict, message: str) -> None:
        self.files[path] = json.loads(json.dumps(data))
        self.writes.append(path)

    def delete(self, path: str, message: str) -> None:
        self.files.pop(path, None)
        self.deletes.append(path)

    def list_names(self, dir_path: str) -> list[str]:
        prefix = dir_path.rstrip("/") + "/"
        names = []
        for p in self.files:
            if p.startswith(prefix) and "/" not in p[len(prefix):]:
                names.append(p[len(prefix):])
        return sorted(names)


# ── gh-backed client (production) ─────────────────────────────────────────────
class GhQueueClient:
    """QueueClient backed by `gh api` against a repo branch (render-queue). Used
    only on the local Mac runner; tests use FakeQueueClient. Light retry/backoff."""

    def __init__(self, owner: str, repo: str, branch: str, *, retries: int = 3):
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.retries = retries

    def _gh(self, args: list[str]) -> tuple[int, str]:
        for attempt in range(self.retries):
            try:
                p = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
            except FileNotFoundError as e:
                raise QueueError("`gh` CLI not found — install + `gh auth login`") from e
            if p.returncode == 0:
                return 0, p.stdout
            err = p.stderr or ""
            transient = ("rate limit" in err.lower()) or (_HTTP_5XX.search(err) is not None)
            if transient and attempt < self.retries - 1:
                time.sleep(2 ** attempt)
                continue
            if "Not Found" in err or "404" in err:
                return 404, err
            raise QueueError(f"gh api {' '.join(args)} failed: {err.strip()}")
        raise QueueError("gh api retries exhausted")

    def _contents(self, path: str) -> str:
        return f"repos/{self.owner}/{self.repo}/contents/{path}"

    def read_json(self, path: str) -> dict | None:
        code, out = self._gh([f"{self._contents(path)}?ref={self.branch}"])
        if code == 404:
            return None
        obj = json.loads(out)
        return json.loads(base64.b64decode(obj["content"]).decode("utf-8"))

    def _sha(self, path: str) -> str | None:
        code, out = self._gh([f"{self._contents(path)}?ref={self.branch}"])
        return None if code == 404 else json.loads(out).get("sha")

    def write_json(self, path: str, data: dict, message: str) -> None:
        content = base64.b64encode(
            (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")).decode("ascii")
        args = ["-X", "PUT", self._contents(path), "-f", f"message={message}",
                "-f", f"content={content}", "-f", f"branch={self.branch}"]
        sha = self._sha(path)
        if sha:
            args += ["-f", f"sha={sha}"]
        self._gh(args)

    def delete(self, path: str, message: str) -> None:
        sha = self._sha(path)
        if not sha:
            return
        self._gh(["-X", "DELETE", self._contents(path), "-f", f"message={message}",
                  "-f", f"sha={sha}", "-f", f"branch={self.branch}"])

    def list_names(self, dir_path: str) -> list[str]:
        code, out = self._gh([f"{self._contents(dir_path)}?ref={self.branch}"])
        if code == 404:
            return []
        return sorted(e["name"] for e in json.loads(out) if e.get("type") == "file")
