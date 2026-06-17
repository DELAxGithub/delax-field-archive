"""FakeQueueClient + path helpers (no real gh)."""
from __future__ import annotations

import pytest

from field_shorts import field_telop_queue as q


def test_path_helpers():
    assert q.job_path("approved-ready", "JID") == "field-telop/jobs/approved-ready/JID.json"
    assert q.job_path("done", "JID") == "field-telop/jobs/done/JID.json"
    assert q.approved_manifest_path("DBT_EP003", "a" * 64) == \
        f"field-telop/manifests-approved/DBT_EP003/{'a' * 64}.json"
    assert q.result_path("JID") == "field-telop/results/JID.json"
    with pytest.raises(ValueError):
        q.job_path("pending", "JID")  # pending is not a render status dir for the runner


def test_fake_client_crud_and_list():
    c = q.FakeQueueClient()
    assert c.read_json("x") is None
    c.write_json("field-telop/jobs/approved-ready/a.json", {"id": "a"}, "m")
    c.write_json("field-telop/jobs/approved-ready/b.json", {"id": "b"}, "m")
    c.write_json("field-telop/jobs/done/c.json", {"id": "c"}, "m")
    assert c.list_names("field-telop/jobs/approved-ready") == ["a.json", "b.json"]
    assert c.read_json("field-telop/jobs/approved-ready/a.json") == {"id": "a"}
    c.delete("field-telop/jobs/approved-ready/a.json", "m")
    assert c.read_json("field-telop/jobs/approved-ready/a.json") is None
    assert c.list_names("field-telop/jobs/approved-ready") == ["b.json"]


def test_fake_client_read_is_deep_copy():
    c = q.FakeQueueClient({"p": {"nested": {"v": 1}}})
    got = c.read_json("p")
    got["nested"]["v"] = 999
    assert c.read_json("p")["nested"]["v"] == 1  # stored copy unchanged


def test_gh_client_constructs_without_calling_gh():
    # constructing must not shell out; only explicit ops do
    c = q.GhQueueClient("DELAxGithub", "delax-field-archive", "render-queue")
    assert c.owner == "DELAxGithub" and c.branch == "render-queue"
