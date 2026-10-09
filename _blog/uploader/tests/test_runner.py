"""올리기 흐름 시험 — 가짜 저장소·가짜 네이버로 '두 번 올리기 방지'를 중심으로 확인."""
import copy
import hashlib
from datetime import datetime

import pytest

from github_store import StoreError
from naver_editor import AmbiguousPublishError, EditorError, NotLoggedInError
from naver_upload import Runner
from queue_state import FAILED, INVALID, NEEDS_CHECK, PUBLISHED, PUBLISHING, DUPLICATE, RunLock, StateFile

NOW = datetime(2026, 10, 9, 12, 0)


def md(title, status="ready", extra="", body="본문입니다"):
    return f"---\ntitle: {title}\nstatus: {status}\n{extra}---\n{body}\n"


class FakeStore:
    def __init__(self, files=None, images=None):
        self.files = dict(files or {})
        self.images = dict(images or {})
        self.remote = {}
        self.remote_sha = None
        self.puts = 0
        self.fail_list = False
        self.fail_put = False

    def list_post_files(self):
        if self.fail_list:
            raise StoreError("네트워크 끊김")
        return [{"path": p, "sha": hashlib.sha1(t.encode()).hexdigest()} for p, t in sorted(self.files.items())]

    def read_post_text(self, path, sha):
        return self.files[path]

    def load_post(self, f):
        from blogpost import parse_post
        return parse_post(f["path"], self.read_post_text(f["path"], f["sha"]))

    def fetch_images(self, post, dest):
        return {p: self.download_image(p, dest) for p in post.image_paths}

    def download_image(self, rel, dest):
        if rel not in self.images:
            raise StoreError(f"파일이 없어요: {rel}")
        out = dest / rel.split("/")[-1]
        out.write_bytes(self.images[rel])
        return out

    def get_state(self):
        return copy.deepcopy(self.remote), self.remote_sha

    def put_state(self, data, sha):
        if self.fail_put:
            raise StoreError("쓰기 실패")
        self.remote = copy.deepcopy(data)
        self.puts += 1
        self.remote_sha = f"sha{self.puts}"
        return self.remote_sha


class FakePublisher:
    """mode: ok | before | after | login | interrupt"""

    def __init__(self, log, mode="ok"):
        self.log = log
        self.mode = mode

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def publish(self, post, images, before_final_click, dry_run=False):
        assert all(p.exists() for p in images.values())
        if self.mode == "login":
            raise NotLoggedInError("로그인")
        if self.mode == "before":
            raise EditorError("제목 칸 없음")
        if dry_run:
            self.log.append(("dry", post.path))
            return None
        before_final_click()
        self.log.append(("click", post.path))   # 이 줄이 '발행 확인 버튼 누름'
        if self.mode == "after":
            raise AmbiguousPublishError("주소 못 찾음")
        if self.mode == "interrupt":
            raise KeyboardInterrupt  # 맥이 꺼진 것처럼 — 기록은 publishing 에서 멈춤
        return f"https://blog.naver.com/me/{len(self.log)}"


@pytest.fixture
def env(tmp_path):
    class Env:
        store = FakeStore({"_blog/posts/a.md": md("첫 글")})
        clicks = []
        notes = []
        mode = "ok"
        cfg = {"max_attempts": 3, "max_posts_per_run": 1}
        state_file = StateFile(tmp_path / "state.json")
        lock = RunLock(tmp_path / "run.lock")

        feed = None

        def runner(self):
            return Runner(self.cfg, self.store, self.state_file, self.lock,
                          lambda: FakePublisher(self.clicks, self.mode),
                          lambda t, m: self.notes.append((t, m)), now_fn=lambda: NOW, feed=self.feed)

        def rec(self, path="_blog/posts/a.md"):
            return self.state_file.load()["posts"].get(path, {})
    return Env()


def test_publish_once_then_never_again(env):
    assert env.runner().run() == ["published:_blog/posts/a.md"]
    assert env.rec()["status"] == PUBLISHED and env.rec()["url"].startswith("https://blog.naver.com/")
    assert env.store.remote["posts"]["_blog/posts/a.md"]["status"] == PUBLISHED   # 글쓰기 화면용 사본
    puts = env.store.puts
    assert env.runner().run() == []
    assert len(env.clicks) == 1
    assert env.store.puts == puts   # 바뀐 게 없으면 저장소에 다시 안 씀


def test_draft_and_scheduled_not_published(env):
    env.store.files = {"_blog/posts/d.md": md("임시", status="draft"),
                       "_blog/posts/s.md": md("예약", extra="publish_at: 2026-10-09 13:00\n")}
    assert env.runner().run() == [] and env.clicks == []


def test_failure_before_click_retries_up_to_limit_then_edit_resets(env):
    env.mode = "before"
    for i in range(1, 4):
        assert env.runner().run() == ["failed:_blog/posts/a.md"]
        assert env.rec()["status"] == FAILED and env.rec()["attempts"] == i
    assert env.runner().run() == []            # 3번 실패 뒤엔 멈춤
    env.store.files["_blog/posts/a.md"] = md("첫 글", body="고친 본문")
    env.mode = "ok"
    assert env.runner().run() == ["published:_blog/posts/a.md"]
    assert env.rec()["attempts"] == 1
    assert env.clicks == [("click", "_blog/posts/a.md")]


def test_unclear_after_click_becomes_needs_check_and_waits_for_retry(env):
    env.mode = "after"
    assert env.runner().run() == ["needs_check:_blog/posts/a.md"]
    assert env.rec()["status"] == NEEDS_CHECK
    env.mode = "ok"
    assert env.runner().run() == []            # 자동으로 다시 안 올림
    assert len(env.clicks) == 1
    env.store.files["_blog/posts/a.md"] = md("첫 글", extra="retry: 2026-10-09T12:30\n")
    assert env.runner().run() == ["published:_blog/posts/a.md"]
    assert env.rec()["retry"] == "2026-10-09T12:30"
    assert env.runner().run() == []            # 같은 retry 값으로는 한 번만


def test_crash_after_click_is_not_reposted(env):
    env.mode = "interrupt"
    with pytest.raises(KeyboardInterrupt):
        env.runner().run()
    assert env.rec()["status"] == PUBLISHING
    env.mode = "ok"
    assert env.runner().run() == ["recovered:_blog/posts/a.md"]
    assert env.rec()["status"] == NEEDS_CHECK and len(env.clicks) == 1
    assert any(t == "확인 필요" for t, _ in env.notes)


def test_state_save_failure_blocks_click(env, monkeypatch):
    real_save = env.state_file.save
    calls = {"n": 0}

    def flaky_save(data):
        if any(r.get("status") == PUBLISHING for r in data["posts"].values()):
            calls["n"] += 1
            raise OSError("디스크 가득")
        real_save(data)
    monkeypatch.setattr(env.state_file, "save", flaky_save)
    assert env.runner().run() == ["failed:_blog/posts/a.md"]
    assert env.clicks == [] and calls["n"] == 1
    assert env.rec()["status"] == FAILED


def test_lock_held_means_no_run(env):
    other = RunLock(env.lock.path)
    assert other.acquire()
    try:
        assert env.runner().run() == ["locked"]
    finally:
        other.release()
    assert env.clicks == []


def test_one_post_per_run(env):
    env.store.files = {"_blog/posts/a.md": md("A"), "_blog/posts/b.md": md("B")}
    assert env.runner().run() == ["published:_blog/posts/a.md", "later:_blog/posts/b.md"]
    assert env.runner().run() == ["published:_blog/posts/b.md"]
    assert env.runner().run() == []


def test_login_lost_counts_no_attempt_and_alerts_once(env):
    env.mode = "login"
    assert env.runner().run() == ["login:_blog/posts/a.md"]
    assert env.runner().run() == ["login:_blog/posts/a.md"]
    assert env.rec() == {}
    assert sum(t == "로그인 필요" for t, _ in env.notes) == 1


def test_dry_run_records_nothing(env):
    assert env.runner().run(dry_run=True) == ["dryrun:_blog/posts/a.md"]
    assert env.clicks == [("dry", "_blog/posts/a.md")] and env.rec() == {}


def test_lost_local_state_uses_remote_copy(env, tmp_path):
    env.runner().run()
    (tmp_path / "state.json").unlink()        # 맥 재설치
    assert env.runner().run() == []
    assert len(env.clicks) == 1


def test_same_title_under_new_file_is_blocked(env):
    env.runner().run()
    env.store.files["_blog/posts/z.md"] = md("첫 글")
    assert env.runner().run() == ["duplicate:_blog/posts/z.md"]
    assert env.runner().run() == []            # 알림은 한 번
    assert env.rec("_blog/posts/z.md")["status"] == DUPLICATE
    assert len(env.clicks) == 1


def test_invalid_post_reported_once(env):
    env.store.files = {"_blog/posts/x.md": md("", body="본문")}
    assert env.runner().run() == ["invalid:_blog/posts/x.md"]
    assert env.runner().run() == []
    assert env.rec("_blog/posts/x.md")["status"] == INVALID
    assert sum(t == "글 형식 오류" for t, _ in env.notes) == 1


def test_missing_image_fails_without_click(env):
    env.store.files = {"_blog/posts/i.md": md("사진글", body="글\n\n![](images/none.jpg)")}
    assert env.runner().run() == ["failed:_blog/posts/i.md"]
    assert env.clicks == [] and "none.jpg" in env.rec("_blog/posts/i.md")["error"]


def test_image_downloaded_and_passed(env):
    env.store.files = {"_blog/posts/i.md": md("사진글", body="글\n\n![](images/ok.jpg)")}
    env.store.images = {"images/ok.jpg": b"\xff\xd8jpeg"}
    assert env.runner().run() == ["published:_blog/posts/i.md"]


def test_network_down_is_quiet(env):
    env.store.fail_list = True
    assert env.runner().run() == ["store_error"] and env.clicks == []


def test_remote_copy_write_failure_does_not_break(env):
    env.store.fail_put = True
    assert env.runner().run() == ["published:_blog/posts/a.md"]
    assert env.rec()["status"] == PUBLISHED


def test_browser_launch_failure_counts_no_attempt(env):
    def broken():
        raise RuntimeError("Executable doesn't exist")
    r = env.runner()
    r.publisher_factory = broken
    assert r.run() == ["browser_error"]
    assert env.rec() == {}


class FakeFeed:
    def __init__(self, titles=None, fail=False):
        self._titles = titles or []
        self.fail = fail
        self.calls = 0

    def titles(self):
        self.calls += 1
        if self.fail:
            raise StoreError("RSS 못 받음")
        return self._titles


def test_post_already_on_blog_is_not_reposted(env):
    env.feed = FakeFeed(["다른 글", "첫 글 "])          # 사장님이 손으로 올린 글
    assert env.runner().run() == ["on_blog:_blog/posts/a.md"]
    assert env.clicks == [] and env.rec()["status"] == DUPLICATE
    assert sum(t == "이미 올라간 글" for t, _ in env.notes) == 1
    assert env.runner().run() == []                     # 다시 안 알림·안 올림
    env.store.files["_blog/posts/a.md"] = md("첫 글", extra="retry: 2026-10-09T13:00\n")
    assert env.runner().run() == ["published:_blog/posts/a.md"]   # [다시 올리기]면 올림


def test_series_titles_with_different_number_are_not_confused(env):
    env.store.files = {"_blog/posts/a.md": md("[두바이 ④] 두바이 3일 실제 쓴 돈 정리")}
    env.feed = FakeFeed(["[두바이 ③] 렌트카로 하루 만에 도는 아부다비 코스",
                         "[두바이 ②] 두바이 렌트카 처음이라면"])
    assert env.runner().run() == ["published:_blog/posts/a.md"]


def test_feed_failure_means_no_upload_and_no_attempt(env):
    env.feed = FakeFeed(fail=True)
    assert env.runner().run() == ["feed_error"]
    assert env.clicks == [] and env.rec() == {}


def test_feed_fetched_once_per_run(env):
    env.store.files = {"_blog/posts/a.md": md("A"), "_blog/posts/b.md": md("B")}
    env.cfg = {"max_attempts": 3, "max_posts_per_run": 2}
    env.feed = FakeFeed([])
    env.runner().run()
    assert env.feed.calls == 2 and len(env.clicks) == 2   # FakeFeed 는 캐시 안 함 — 진짜 BlogFeed 는 1번
