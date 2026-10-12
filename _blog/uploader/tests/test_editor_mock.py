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
    assert "<strong>굵게</strong>" in html and "color:#0075c8" in html and "<h3><strong>하루 순서</strong></h3>" in html and "<blockquote>" in html


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


def test_save_draft_never_clicks_publish(base_url, tmp_path, images):
    Handler.submissions.clear()
    with publisher(tmp_path, f"{base_url}/editor.html") as pub:
        shot = pub.save_draft(POST, images)
    assert shot and shot.exists()
    assert len(Handler.submissions) == 1            # /draft 한 번(발행 /submit 은 없음)
    sub = Handler.submissions[-1]
    assert "comps" not in sub and sub["title"] == "모의 시험 글"
    assert sub["tags"] == ["화물", "운송"] and sub["category"] == "업무 일지"


def test_apply_edits_replaces_text_without_publishing(base_url, tmp_path):
    from naver_editor import apply_edits
    Handler.submissions.clear()
    post = parse_post("p.md", "---\ntitle: 옛 제목\nstatus: ready\n---\n요금 **1,200엔** 이에요\n\n끝 인사")
    with publisher(tmp_path, f"{base_url}/editor.html?notrail=1") as pub:
        assert pub.publish(post, {}, lambda: None, dry_run=True) is None
    # 모의 화면은 새로 열면 비어 있으니 같은 화면에 글을 채운 뒤 고치기를 시험한다
    with publisher(tmp_path, f"{base_url}/editor.html?owncaret=1") as pub:
        page = pub._ctx.new_page()
        frame = pub._open_editor(page)
        pub._dismiss_popups(frame)
        pub._fill_title(frame, "옛 제목 후기")
        pub._insert_html(page, frame, post.segments[0])
        pub.write_url = f"{base_url}/editor.html"
        spec = {"replace": [{"old": "옛 제목 후기", "new": "새 제목 2026"}, {"old": "1,200엔", "new": "1,300엔"},
                            {"old": "없는 글자", "new": "x"}]}
        import naver_editor
        orig = pub._open_editor
        pub._open_editor = lambda _p: frame
        _, _, done = apply_edits(pub, "1", spec, {}, edit_url=f"{base_url}/editor.html")
        pub._open_editor = orig
        text = frame.locator("#doc").inner_text()
    assert "새 제목 2026" in text and "1,300엔" in text and "1,200엔" not in text
    assert any(d.startswith("못 찾음") for d in done)
    assert Handler.submissions == []   # 발행 안 함


def test_apply_edits_deletes_without_backspace_and_checks_result(base_url, tmp_path):
    """지우기는 진짜 선택 + 지우기 키. 바꾼 결과가 예상과 다르면 '안 바뀜'(발행 막음)."""
    from naver_editor import apply_edits
    post = parse_post("p.md", "---\ntitle: t\nstatus: ready\n---\n**가족탕** 요금 **1,200엔**\n\n끝 인사")
    with publisher(tmp_path, f"{base_url}/editor.html?owncaret=1") as pub:
        page = pub._ctx.new_page()
        frame = pub._open_editor(page)
        pub._dismiss_popups(frame)
        pub._fill_title(frame, "제목")
        page.keyboard.press("Tab")
        frame.locator(".se-component.se-text .se-text-paragraph").last.click()
        page.keyboard.insert_text("**가족탕** 요금 **1,200엔** 끝")
        orig = pub._open_editor
        pub._open_editor = lambda _p: frame
        spec = {"replace": [{"old": "**", "new": "", "all": True}, {"old": "요금", "new": "가격"}]}
        _, _, done = apply_edits(pub, "1", spec, {}, edit_url=f"{base_url}/editor.html")
        pub._open_editor = orig
        text = frame.locator("#doc").inner_text()
    assert "**" not in text and "가족탕 가격 1,200엔 끝" in text
    assert done[0].startswith("바꿈 4곳") and done[1].startswith("바꿈 1곳")


def test_apply_edits_reports_when_text_does_not_change(base_url, tmp_path):
    from naver_editor import apply_edits
    with publisher(tmp_path, f"{base_url}/editor.html") as pub:
        page = pub._ctx.new_page()
        frame = pub._open_editor(page)
        pub._dismiss_popups(frame)
        frame.locator(".se-component.se-text .se-text-paragraph").last.click()
        page.keyboard.insert_text("요금 1,200엔")
        frame.evaluate("""() => document.getElementById('doc').addEventListener('beforeinput',
                          e => e.preventDefault(), true)""")   # 입력을 에디터가 무시하는 경우
        pub._open_editor = lambda _p: frame
        _, _, done = apply_edits(pub, "1", {"replace": [{"old": "1,200엔", "new": "1,300엔"}]}, {},
                                 edit_url=f"{base_url}/editor.html")
    assert done[0].startswith("안 바뀜")


def test_mock_owncaret_ignores_script_selection_like_naver(base_url, tmp_path):
    """모의 에디터가 진짜 네이버처럼 스크립트 선택을 무시하는지(위 시험들이 의미 있으려면)."""
    with publisher(tmp_path, f"{base_url}/editor.html?owncaret=1") as pub:
        page = pub._ctx.new_page()
        frame = pub._open_editor(page)
        pub._dismiss_popups(frame)
        frame.locator(".se-component.se-text .se-text-paragraph").last.click()
        page.keyboard.insert_text("요금 1,200엔 끝")
        frame.evaluate("""() => { const p = document.querySelector('.se-component.se-text .se-text-paragraph');
            const n = p.firstChild, i = n.nodeValue.indexOf('1,200엔'); const r = document.createRange();
            r.setStart(n, i); r.setEnd(n, i + 6); getSelection().removeAllRanges(); getSelection().addRange(r); }""")
        page.keyboard.insert_text("1,300엔")
        text = frame.locator("#doc").inner_text()
    assert "1,200엔" in text and "1,300엔" in text     # 옛 방식이면 안 바뀌고 엉뚱한 데 들어감


def test_join_prev_stops_if_extra_backspace_eats_text(base_url, tmp_path):
    """빈 줄 없애기(join_prev)는 글자 수가 그대로일 때만 — 글자를 먹으면 '안 바뀜'(발행 막음)."""
    from naver_editor import apply_edits
    with publisher(tmp_path, f"{base_url}/editor.html?owncaret=1") as pub:
        page = pub._ctx.new_page()
        frame = pub._open_editor(page)
        pub._dismiss_popups(frame)
        frame.locator(".se-component.se-text .se-text-paragraph").last.click()
        page.keyboard.insert_text("앞 글자 지울말")
        pub._open_editor = lambda _p: frame
        _, _, done = apply_edits(pub, "1", {"replace": [{"old": "지울말", "new": "", "join_prev": True}]}, {},
                                 edit_url=f"{base_url}/editor.html")
    assert done[0].startswith("안 바뀜") and "빈 줄" in done[0]


def test_diff_note_shows_only_unexpected_change():
    from naver_editor import _diff_note, _expected_doc
    before = "앞 글 **진한** 뒤 글 끝"
    after_ok = "앞 글 진한** 뒤 글 끝"
    after_bad = "앞 글 진한** 뒤 글 엉뚱 끝"
    exp = _expected_doc(before, "앞 글 **진한", "**", "")
    assert _diff_note(exp, after_ok) == "(없음)"
    assert "엉뚱" in _diff_note(exp, after_bad) and "**진한" not in _diff_note(exp, after_bad)


def test_edit_ignores_editor_button_text_changes(base_url, tmp_path):
    """사진 옆 버튼 글씨처럼 본문 밖 글자가 바뀌어도 '안 바뀜'으로 보지 않는다(본문 문단만 센다)."""
    from naver_editor import apply_edits
    with publisher(tmp_path, f"{base_url}/editor.html?owncaret=1") as pub:
        page = pub._ctx.new_page()
        frame = pub._open_editor(page)
        pub._dismiss_popups(frame)
        frame.locator(".se-component.se-text .se-text-paragraph").last.click()
        page.keyboard.insert_text("특징은 **진한** 유황")
        frame.evaluate("""() => { const b = document.createElement('span'); b.textContent = '사진 삭제';
            document.getElementById('doc').appendChild(b);
            document.addEventListener('keydown', () => { b.textContent = '대표사진 삭제'; }, true); }""")
        pub._open_editor = lambda _p: frame
        _, _, done = apply_edits(pub, "1", {"replace": [{"old": "**", "new": "", "all": True}]}, {},
                                 edit_url=f"{base_url}/editor.html")
        text = frame.locator(".se-component.se-text").first.inner_text()
    assert done[0].startswith("바꿈 2곳") and "**" not in text


def test_all_with_old_inside_new_is_refused(base_url, tmp_path):
    """'all' 인데 새 글자에 옛 글자가 들어 있으면 같은 자리를 끝없이 바꾼다 → 거절(발행 막음)."""
    from naver_editor import apply_edits
    with publisher(tmp_path, f"{base_url}/editor.html?owncaret=1") as pub:
        page = pub._ctx.new_page()
        frame = pub._open_editor(page)
        pub._dismiss_popups(frame)
        frame.locator(".se-component.se-text .se-text-paragraph").last.click()
        page.keyboard.insert_text("가격 1,200엔")
        pub._open_editor = lambda _p: frame
        _, _, done = apply_edits(pub, "1", {"replace": [{"old": "가격", "new": "가격(2026)", "all": True}]}, {},
                                 edit_url=f"{base_url}/editor.html")
        text = frame.locator("#doc").inner_text()
    assert done[0].startswith("안 바뀜") and "(2026)" not in text


def test_misaimed_edit_is_caught_by_whole_doc_check(base_url, tmp_path):
    """클릭이 한 글자 어긋나 엉뚱한 글자를 지워도 글자 수는 맞을 수 있다 — 문서 전체 비교로 잡는다."""
    import naver_editor
    from naver_editor import apply_edits
    with publisher(tmp_path, f"{base_url}/editor.html?owncaret=1") as pub:
        page = pub._ctx.new_page()
        frame = pub._open_editor(page)
        pub._dismiss_popups(frame)
        frame.locator(".se-component.se-text .se-text-paragraph").last.click()
        page.keyboard.insert_text("2025년 가격")
        pub._open_editor = lambda _p: frame
        real = naver_editor._select_like_person

        def off_by_one(page_, frame_, sel):          # 한 글자 뒤를 잡음: "025년 " → 지우면 "2가격"
            ok = real(page_, frame_, sel)
            page_.keyboard.press("Shift+ArrowLeft") if False else None
            page_.keyboard.press("ArrowLeft")
            page_.keyboard.press("ArrowRight")
            for _ in range(sel["n"]):
                page_.keyboard.press("Shift+ArrowRight")
            return ok
        naver_editor._select_like_person = off_by_one
        try:
            _, _, done = apply_edits(pub, "1", {"replace": [{"old": "2025년", "new": ""}]}, {},
                                     edit_url=f"{base_url}/editor.html")
        finally:
            naver_editor._select_like_person = real
    assert done[0].startswith("안 바뀜")
