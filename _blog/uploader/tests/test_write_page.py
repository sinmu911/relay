"""글쓰기 화면(blog/write.html) 시험 — 가짜 GitHub 로. 화면이 저장한 파일을 업로더(blogpost.py)가 그대로 읽는지 확인."""
import base64
import hashlib
import json
import re
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from blogpost import parse_post

REPO_ROOT = Path(__file__).resolve().parents[3]
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                    "0000000d49444154789c6360f8cf000000030101005d8a1e0b0000000049454e44ae426082")
TOKEN = "github_pat_" + "A" * 30
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, accept, content-type",
        "Access-Control-Allow-Methods": "GET, PUT, OPTIONS"}


class FakeGitHub:
    def __init__(self):
        self.files = {}   # path -> bytes
        self.puts = []

    def sha(self, path):
        return hashlib.sha1(self.files[path]).hexdigest()

    def add(self, path, text):
        self.files[path] = text.encode("utf-8") if isinstance(text, str) else text

    def handle(self, route):
        req = route.request
        if req.method == "OPTIONS":
            return route.fulfill(status=204, headers=CORS)
        assert req.headers.get("authorization") == f"Bearer {TOKEN}"
        url = req.url.split("?")[0]
        if re.search(r"/repos/me/blog$", url):
            return self._json(route, 200, {"full_name": "me/blog"})
        m = re.search(r"/repos/me/blog/contents/(.+)$", url)
        path = "/".join(__import__("urllib.parse").parse.unquote(p) for p in m.group(1).split("/"))
        if req.method == "GET":
            if path in self.files:
                return self._json(route, 200, {"path": path, "sha": self.sha(path),
                                               "content": base64.encodebytes(self.files[path]).decode()})
            kids = [{"name": p.split("/")[-1], "path": p, "sha": self.sha(p), "type": "file"}
                    for p in self.files if p.rsplit("/", 1)[0] == path]
            return self._json(route, 200, kids) if kids else self._json(route, 404, {"message": "Not Found"})
        body = json.loads(req.post_data)
        if path in self.files and body.get("sha") != self.sha(path):
            return self._json(route, 409, {"message": "sha does not match"})
        self.files[path] = base64.b64decode(body["content"])
        self.puts.append((path, body))
        return self._json(route, 200, {"content": {"path": path, "sha": self.sha(path)}})

    @staticmethod
    def _json(route, status, data):
        route.fulfill(status=status, headers=dict(CORS, **{"Content-Type": "application/json"}), body=json.dumps(data))


@pytest.fixture(scope="module")
def base_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(REPO_ROOT)))
    srv.RequestHandlerClass.log_message = lambda *a: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def ui(base_url):
    gh = FakeGitHub()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        ctx.route("https://api.github.com/**", gh.handle)
        page = ctx.new_page()
        page.on("dialog", lambda d: d.accept())
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        def open_page(configured=True):
            if configured:
                page.add_init_script("localStorage.setItem('blog_cfg', JSON.stringify("
                                     + json.dumps({"token": TOKEN, "repo": "me/blog", "branch": "main"}) + "))")
            page.goto(f"{base_url}/blog/write.html")
            return page
        yield gh, open_page, errors
        assert errors == []
        browser.close()


def saved_posts(gh):
    return {p: parse_post(p, t.decode()) for p, t in gh.files.items() if p.startswith("_blog/posts/")}


def test_settings_then_new_post_roundtrip(ui):
    gh, open_page, _ = ui
    page = open_page(configured=False)
    expect(page.locator("#v_set")).to_be_visible()
    page.fill("#s_token", TOKEN)
    page.fill("#s_repo", "me/blog")
    page.click("#s_save")
    expect(page.locator("#list")).to_contain_text("아직 글이 없어요")
    page.click("#b_new")
    page.fill("#e_title", "첫 글: 테스트\n둘째줄")
    page.fill("#e_body", "안녕하세요 😀\n\n**굵게** 줄\n---\n끝")
    page.fill("#e_tags", "#화물, 운송, 화물")
    page.fill("#e_cat", "업무 일지")
    page.click("#e_go")
    expect(page.locator("#list .chip")).to_have_text("올라갈 차례")
    (path, post), = saved_posts(gh).items()
    assert re.fullmatch(r"_blog/posts/\d{4}-\d\d-\d\d-\d{6}\.md", path)
    assert post.errors == [] and post.status == "ready"
    assert post.title == "첫 글: 테스트 둘째줄"
    assert post.tags == ["화물", "운송"] and post.category == "업무 일지"
    assert "😀" in post.body and post.body.endswith("끝")


def test_draft_and_schedule(ui):
    gh, open_page, _ = ui
    page = open_page()
    page.click("#b_new")
    page.fill("#e_title", "임시")
    page.click("#e_draft")
    expect(page.locator("#list .chip")).to_have_text("임시저장")
    page.click("#list .item")
    page.fill("#e_body", "본문")
    page.fill("#e_when", "2099-01-02T03:04")
    page.click("#e_go")
    expect(page.locator("#list .chip")).to_have_text("예약 1/2 03:04")
    post, = saved_posts(gh).values()
    assert post.status == "ready" and str(post.publish_at) == "2099-01-02 03:04:00"
    assert [b.get("sha") is not None for _, b in gh.puts] == [False, True]   # 고칠 땐 sha 붙여 덮어씀


def test_ready_requires_title_and_body(ui):
    gh, open_page, _ = ui
    page = open_page()
    page.click("#b_new")
    page.click("#e_go")
    expect(page.locator("#toast")).to_have_text("제목을 써 주세요.")
    assert gh.puts == []


def test_failed_post_retry_sets_token(ui):
    gh, open_page, _ = ui
    gh.add("_blog/posts/2026-10-09-120000.md", "---\ntitle: 실패글\nstatus: ready\n---\n본문\n")
    sha = gh.sha("_blog/posts/2026-10-09-120000.md")
    gh.add("_blog/state.json", json.dumps({"posts": {"_blog/posts/2026-10-09-120000.md": {
        "status": "failed", "attempts": 3, "blob_sha": sha, "error": "제목 칸을 못 찾았어요"}}}))
    page = open_page()
    expect(page.locator("#list .chip")).to_have_text("실패 3회")
    page.click("#list .item")
    expect(page.locator("#e_note")).to_contain_text("제목 칸을 못 찾았어요")
    page.click("#e_note button")
    post = saved_posts(gh)["_blog/posts/2026-10-09-120000.md"]
    assert post.retry and post.status == "ready" and post.errors == []


def test_published_is_read_only_with_link(ui):
    gh, open_page, _ = ui
    gh.add("_blog/posts/2026-10-09-120000.md", "---\ntitle: 올린글\nstatus: ready\n---\n본문\n")
    gh.add("_blog/state.json", json.dumps({"posts": {"_blog/posts/2026-10-09-120000.md": {
        "status": "published", "url": "https://blog.naver.com/me/1", "blob_sha": "old"}}}))
    page = open_page()
    expect(page.locator("#list .chip")).to_have_text("올라감")
    page.click("#list .item")
    expect(page.locator("#e_note a")).to_have_attribute("href", "https://blog.naver.com/me/1")
    expect(page.locator("#e_acts")).to_be_hidden()
    assert page.locator("#e_title").evaluate("e => e.readOnly")


def test_bad_url_in_state_is_not_linked(ui):
    gh, open_page, _ = ui
    gh.add("_blog/posts/2026-10-09-120000.md", "---\ntitle: x\nstatus: ready\n---\n본문\n")
    gh.add("_blog/state.json", json.dumps({"posts": {"_blog/posts/2026-10-09-120000.md": {
        "status": "published", "url": "javascript:alert(1)"}}}))
    page = open_page()
    page.click("#list .item")
    assert page.locator("#e_note a").get_attribute("href") is None


def test_image_upload_inserts_valid_reference(ui, tmp_path):
    gh, open_page, _ = ui
    (tmp_path / "p.png").write_bytes(PNG)
    page = open_page()
    page.click("#b_new")
    page.fill("#e_title", "사진글")
    page.fill("#e_body", "위 글")
    page.locator("#e_file").set_input_files(str(tmp_path / "p.png"))
    expect(page.locator("#e_imgmsg")).to_have_text("사진 1장 넣었어요.")
    page.click("#e_go")
    expect(page.locator("#list .chip")).to_have_text("올라갈 차례")
    post, = saved_posts(gh).values()
    assert post.errors == [] and len(post.image_paths) == 1
    img = gh.files["_blog/" + post.image_paths[0]]
    assert img[:3] == b"\xff\xd8\xff"     # jpg 로 바뀜


def test_unsaved_text_survives_reload(ui):
    gh, open_page, _ = ui
    page = open_page()
    page.click("#b_new")
    page.fill("#e_title", "쓰다 만 글")
    page.reload()
    page.click("#b_new")
    expect(page.locator("#e_title")).to_have_value("쓰다 만 글")


def test_conflict_message(ui):
    gh, open_page, _ = ui
    gh.add("_blog/posts/2026-10-09-120000.md", "---\ntitle: a\nstatus: draft\n---\n본문\n")
    page = open_page()
    page.click("#list .item")
    gh.add("_blog/posts/2026-10-09-120000.md", "---\ntitle: a\nstatus: draft\n---\n다른 곳에서 고침\n")
    page.click("#e_draft")
    expect(page.locator("#toast")).to_contain_text("다른 곳에서 먼저 바뀌었어요")
