import json
from datetime import datetime

import pytest

from blogpost import parse_post
from queue_state import (ACTION_DUPLICATE, ACTION_INVALID, ACTION_SKIP, ACTION_UPLOAD, ACTION_WAIT, FAILED,
                         NEEDS_CHECK, PUBLISHED, PUBLISHING, RunLock, StateError, StateFile, decide,
                         merge_remote, recover_interrupted, taken_titles)

NOW = datetime(2026, 10, 9, 12, 0)


def post(path="p/a.md", title="제목", status="ready", extra=""):
    return parse_post(path, f"---\ntitle: {title}\nstatus: {status}\n{extra}---\n본문")


def test_ready_uploads():
    assert decide(post(), None, NOW, {}, 3).action == ACTION_UPLOAD


def test_draft_skipped_even_if_incomplete():
    p = parse_post("p/a.md", "---\ntitle:\nstatus: draft\n---\n")
    assert decide(p, None, NOW, {}, 3).action == ACTION_SKIP


def test_invalid():
    p = parse_post("p/a.md", "---\ntitle:\nstatus: ready\n---\n본문")
    assert decide(p, None, NOW, {}, 3).action == ACTION_INVALID


def test_schedule_boundary():
    assert decide(post(extra="publish_at: 2026-10-09 12:01\n"), None, NOW, {}, 3).action == ACTION_WAIT
    assert decide(post(extra="publish_at: 2026-10-09 12:00\n"), None, NOW, {}, 3).action == ACTION_UPLOAD


@pytest.mark.parametrize("status", [PUBLISHED, PUBLISHING, NEEDS_CHECK])
def test_never_auto_repost(status):
    p = post()
    assert decide(p, {"status": status, "hash": "other"}, NOW, {}, 3).action == ACTION_SKIP


def test_published_ignores_retry_token():
    p = post(extra="retry: 1\n")
    assert decide(p, {"status": PUBLISHED}, NOW, {}, 3).action == ACTION_SKIP


def test_needs_check_retry_only_with_new_token():
    p = post(extra="retry: 2026-10-09T11:00\n")
    assert decide(p, {"status": NEEDS_CHECK, "retry": ""}, NOW, {}, 3).action == ACTION_UPLOAD
    assert decide(p, {"status": NEEDS_CHECK, "retry": "2026-10-09T11:00"}, NOW, {}, 3).action == ACTION_SKIP


def test_failed_attempt_limit_and_reset_on_edit():
    p = post()
    rec = {"status": FAILED, "hash": p.content_hash, "attempts": 3}
    assert decide(p, rec, NOW, {}, 3).action == ACTION_SKIP
    assert decide(p, dict(rec, attempts=2), NOW, {}, 3).action == ACTION_UPLOAD
    assert decide(p, dict(rec, hash="edited"), NOW, {}, 3).action == ACTION_UPLOAD


def test_duplicate_title_and_override_by_retry():
    titles = {"제목": "p/old.md"}
    assert decide(post(), None, NOW, titles, 3).action == ACTION_DUPLICATE
    assert decide(post(title=" 제목  "), None, NOW, titles, 3).action == ACTION_DUPLICATE
    assert decide(post(extra="retry: x\n"), None, NOW, titles, 3).action == ACTION_UPLOAD
    assert decide(post(path="p/old.md"), None, NOW, titles, 3).action == ACTION_UPLOAD


def test_taken_titles_only_maybe_on_naver():
    st = {"posts": {"a": {"status": PUBLISHED, "title": "A"}, "b": {"status": FAILED, "title": "B"},
                    "c": {"status": NEEDS_CHECK, "title": "C"}}}
    assert taken_titles(st) == {"A": "a", "C": "c"}


def test_recover_interrupted():
    st = {"posts": {"a": {"status": PUBLISHING}, "b": {"status": PUBLISHED}}}
    assert recover_interrupted(st, NOW) == ["a"]
    assert st["posts"]["a"]["status"] == NEEDS_CHECK and st["posts"]["b"]["status"] == PUBLISHED


def test_merge_remote_local_wins_and_fills_gaps():
    local = {"posts": {"a": {"status": FAILED}}}
    remote = {"posts": {"a": {"status": PUBLISHED}, "b": {"status": PUBLISHED}}}
    m = merge_remote(local, remote)
    assert m["posts"]["a"]["status"] == FAILED and m["posts"]["b"]["status"] == PUBLISHED
    assert merge_remote(local, {})["posts"] == local["posts"]


def test_state_file_roundtrip_and_corrupt(tmp_path):
    sf = StateFile(tmp_path / "s.json")
    assert sf.load()["posts"] == {}
    sf.save({"version": 1, "posts": {"a": {"status": "published", "title": "한글"}}, "meta": {}})
    assert sf.load()["posts"]["a"]["title"] == "한글"
    assert not list(tmp_path.glob(".state-*"))     # 임시 파일 안 남음
    (tmp_path / "s.json").write_text("{broken")
    with pytest.raises(StateError):
        sf.load()
    (tmp_path / "s.json").write_text(json.dumps({"posts": []}))
    with pytest.raises(StateError):
        sf.load()


def test_run_lock_exclusive(tmp_path):
    a, b = RunLock(tmp_path / "l"), RunLock(tmp_path / "l")
    assert a.acquire() is True
    assert b.acquire() is False
    a.release()
    assert b.acquire() is True
    b.release()
