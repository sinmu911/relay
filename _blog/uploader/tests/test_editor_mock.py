"""네이버 에디터 조작 시험 — 진짜 네이버 대신 같은 구조의 모의 화면(mock_site)으로.
진짜 네이버 화면과 100% 같다는 보장은 없다. 첫 사용 때 setup_mac.sh test(발행 직전까지만)로 확인할 것."""
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from blogpost import parse_post
from naver_editor import EditorError, NaverPublisher, NotLoggedInError

SITE = Path(__file__).parent / "mock_site"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                    "0000000d49444154789c6360f8cf000000030101005d8a1e0b0000000049454e44ae426082")


class Handler(SimpleHTTPRequestHandler):
    submissions = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Handler.submissions.append(json.loads(body))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def base_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(SITE)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def images(tmp_path):
    for n in ("one.png", "two.png"):
        (tmp_path / n).write_bytes(PNG)
    return {"images/one.png": tmp_path / "one.png", "images/two.png": tmp_path / "two.png"}


POST = parse_post("_blog/posts/t.md", """---
title: 모의 시험 글
status: ready
tags: 화물, 운송
category: 업무 일지
---
첫 문단 **굵게**

![](images/one.png)

- 목록 하나
- 목록 둘

![](images/two.png)
""")


def publisher(tmp_path, url, **kw):
    return NaverPublisher("me", tmp_path / "profile", tmp_path / "shots", headless=True, write_url=url, **kw)


@pytest.mark.parametrize("page", ["editor.html", "wrapper.html", "editor.html?notrail=1"])
def test_full_publish(base_url, tmp_path, images, page):
    Handler.submissions.clear()
    marks = []
    with publisher(tmp_path, f"{base_url}/{page}") as pub:
        url = pub.publish(POST, images, lambda: marks.append(1))
    assert url == "https://blog.naver.com/me/223344556677"
    assert marks == [1]
    sub = Handler.submissions[-1]
    assert sub["title"] == "모의 시험 글"
    assert sub["tags"] == ["화물", "운송"] and sub["category"] == "업무 일지"
    order = ["img:" + c["img"] if "img" in c else "text" for c in sub["comps"] if "img" in c or c["text"]]
    assert order == ["text", "img:one.png", "text", "img:two.png"]   # 글·사진 순서 유지
    texts = [c for c in sub["comps"] if c.get("text")]
    assert "<strong>굵게</strong>" in texts[0]["html"] and "<li>목록 하나</li>" in texts[1]["html"]


def test_dry_run_stops_before_publish(base_url, tmp_path, images):
    Handler.submissions.clear()
    marks = []
    with publisher(tmp_path, f"{base_url}/editor.html") as pub:
        assert pub.publish(POST, images, lambda: marks.append(1), dry_run=True) is None
    assert marks == [] and Handler.submissions == []
    assert list((tmp_path / "shots").glob("dryrun-*.png"))


def test_unknown_category_stops_before_publish(base_url, tmp_path, images):
    Handler.submissions.clear()
    post = parse_post("p.md", "---\ntitle: 카테고리 없음\nstatus: ready\ncategory: 없는칸\n---\n본문")
    marks = []
    with publisher(tmp_path, f"{base_url}/editor.html") as pub:
        with pytest.raises(EditorError, match="없는칸"):
            pub.publish(post, {}, lambda: marks.append(1))
    assert marks == [] and Handler.submissions == []
    assert list((tmp_path / "shots").glob("fail-*.png"))


def test_paste_not_supported_falls_back_to_typing(base_url, tmp_path):
    Handler.submissions.clear()
    post = parse_post("p.md", "---\ntitle: 직접 입력\nstatus: ready\n---\n첫째 줄\n\n둘째 문단")
    with publisher(tmp_path, f"{base_url}/editor.html?nopaste=1") as pub:
        assert pub.publish(post, {}, lambda: None)
    text = " ".join(c.get("text", "") for c in Handler.submissions[-1]["comps"])
    assert "첫째 줄" in text and "둘째 문단" in text


def test_login_page_detected(base_url, tmp_path):
    marks = []
    with publisher(tmp_path, f"{base_url}/nidlogin.html", login_marker="nidlogin") as pub:
        with pytest.raises(NotLoggedInError):
            pub.publish(POST, {}, lambda: marks.append(1))
    assert marks == []


def test_before_click_failure_prevents_click(base_url, tmp_path, images):
    Handler.submissions.clear()

    def boom():
        raise OSError("기록 실패")
    with publisher(tmp_path, f"{base_url}/editor.html") as pub:
        with pytest.raises(OSError):
            pub.publish(POST, images, boom)
    assert Handler.submissions == []


def test_blog_section_post_in_editor(base_url, tmp_path):
    """블로그 섹션 완성본(■·▶·굵게·파랑·그림 자리)이 모의 에디터에 순서대로 들어가는지."""
    from neo_source import NeoStore
    from test_neo_source import make_neo
    root = make_neo(tmp_path / "neo")
    st = NeoStore(root)
    post = st.load_post(st.list_post_files()[0])
    images = st.fetch_images(post, tmp_path)
    Handler.submissions.clear()
    with publisher(tmp_path, f"{base_url}/editor.html") as pub:
        assert pub.publish(post, images, lambda: None)
    sub = Handler.submissions[-1]
    assert sub["title"] == "[테스트 ①] 렌트카로 도는 하루 코스"
    assert sub["tags"] == ["테스트", "렌트카여행", "달리는이기사"]
    order = ["img:" + c["img"] if "img" in c else "text" for c in sub["comps"] if "img" in c or c["text"]]
    assert order == ["img:테스트_00_대표.png", "text", "img:테스트_01_지도.png", "text"]
    html = " ".join(c["html"] for c in sub["comps"] if c.get("text"))
    assert "<strong>굵게</strong>" in html and "color:#0075c8" in html and "<strong>■ 하루 순서</strong>" in html


@pytest.mark.parametrize("persist,expected", [("1", []), ("0", ["NID_AUT", "NID_SES"])])
def test_interactive_login_waits_for_flow_end_and_reports_session_cookies(base_url, tmp_path, persist, expected):
    from naver_editor import interactive_login
    status, session_only = interactive_login(
        tmp_path / "profile", f"{base_url}/loginflow.html?persist={persist}", wait_seconds=20,
        login_marker="loginflow", cookie_urls=(base_url,), headless=True, settle_ms=200)
    assert status == "ok"
    assert session_only == expected


def test_check_login(base_url, tmp_path):
    with publisher(tmp_path, f"{base_url}/editor.html") as pub:
        assert pub.check_login() is True
    with publisher(tmp_path, f"{base_url}/nidlogin.html", login_marker="nidlogin") as pub:
        assert pub.check_login() is False


def test_brief_pass_through_login_host_is_not_logged_out(base_url, tmp_path):
    # 다시 연 브라우저가 로그인 이어주기로 nid 주소를 잠깐 거쳐도 '풀림'으로 보지 않는다
    with publisher(tmp_path, f"{base_url}/nidlogin_bounce.html", login_marker="nidlogin") as pub:
        assert pub.check_login() is True


def test_untrusted_paste_ignored_uses_real_clipboard_keeps_format(base_url, tmp_path):
    Handler.submissions.clear()
    post = parse_post("p.md", "---\ntitle: 클립보드\nstatus: ready\n---\n첫째 **굵게** 줄\n\n둘째 문단")
    with publisher(tmp_path, f"{base_url}/editor.html?trustedpaste=1") as pub:
        assert pub.publish(post, {}, lambda: None)
    comps = Handler.submissions[-1]["comps"]
    html = " ".join(c.get("html", "") for c in comps)
    text = " ".join(c.get("text", "") for c in comps)
    assert "둘째 문단" in text and text.count("둘째 문단") == 1
    assert "<strong>" in html or "<b>" in html, html
