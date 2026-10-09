"""네이버 블로그 스마트에디터 ONE 을 브라우저로 직접 눌러 글을 올린다.

네이버는 블로그 글쓰기 API를 열어 두지 않아서 사람이 하는 것과 같은 순서로 화면을 조작한다.
네이버가 화면을 바꾸면 아래 SELECTORS 만 고치면 되게 한곳에 모았다.
로그인은 사장님이 처음 한 번 직접 한다(login 명령). 비밀번호는 어디에도 저장하지 않는다.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Frame, Locator, Page, sync_playwright

from blogpost import Post, Segment, html_to_lines

log = logging.getLogger(__name__)

WRITE_URL = "https://blog.naver.com/{blog_id}?Redirect=Write&"
LOGIN_URL = "https://nid.naver.com/nidlogin.login"
LOGIN_MARKER = "nid.naver.com"
AUTH_COOKIES = ("NID_AUT", "NID_SES")

# 각 항목은 앞에서부터 차례로 찾아 처음 보이는 것을 쓴다(네이버 화면이 조금 바뀌어도 버티게)
SELECTORS = {
    "title": [".se-documentTitle .se-text-paragraph", ".se-title-text .se-text-paragraph", ".se-title-text"],
    "body_paragraph": ".se-component.se-text .se-text-paragraph",
    "text_component": ".se-component.se-text",
    "component": ".se-component:not(.se-documentTitle)",
    "image_component": ".se-component.se-image",
    "image_button": ["button.se-image-toolbar-button", "button[data-name='image']"],
    "popup_cancel": [".se-popup-button-cancel"],          # '작성 중인 글이 있습니다' → 취소(새로 쓰기)
    "help_close": [".se-help-panel-close-button"],
    "publish_open": ["button[class*='publish_btn']", "button[data-click-area='tpb.publish']"],
    "publish_confirm": ["button[class*='confirm_btn']", "button[data-testid='seOnePublishBtn']"],
    "category_open": ["button[class*='selectbox_button']"],
    "category_list": "[class*='option_list']",
    "tag_input": ["#tag-input", "input[placeholder*='태그']"],
}

T_EDITOR_MS = 30000
T_SHORT_MS = 3000
T_IMAGE_MS = 60000
T_AFTER_PUBLISH_MS = 40000

PASTE_JS = """([html, text]) => {
  const target = document.activeElement || document.body;
  const dt = new DataTransfer();
  dt.setData('text/html', html);
  dt.setData('text/plain', text);
  const ev = new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true});
  target.dispatchEvent(ev);
  return ev.defaultPrevented;
}"""
CARET_END_JS = """el => { const r = document.createRange(); r.selectNodeContents(el); r.collapse(false);
  const s = window.getSelection(); s.removeAllRanges(); s.addRange(r); }"""
IMG_READY_JS = "img => img.complete && img.naturalWidth > 0"

Scope = Union[Page, Frame]


class NotLoggedInError(Exception):
    """네이버 로그인이 풀렸다 — login 명령으로 다시 로그인해야 한다."""


class EditorError(Exception):
    """[발행] 확인을 누르기 전 문제 — 네이버엔 아무것도 안 올라갔다."""


class AmbiguousPublishError(Exception):
    """[발행] 확인을 누른 뒤 결과를 못 봤다 — 올라갔을 수도 있다."""


def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def _first_visible(scope: Scope, selectors: List[str], timeout_ms: int) -> Optional[Locator]:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        for sel in selectors:
            loc = scope.locator(sel)
            try:
                for i in range(loc.count()):
                    if loc.nth(i).is_visible():
                        return loc.nth(i)
            except PlaywrightError:
                continue  # 찾는 사이 화면이 바뀜 — 다음 바퀴에 다시
        if time.monotonic() >= deadline:
            return None
        scope.wait_for_timeout(200)


def _wait_until(scope: Scope, check: Callable[[], bool], timeout_ms: int) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        try:
            if check():
                return True
        except PlaywrightError:
            pass
        if time.monotonic() >= deadline:
            return False
        scope.wait_for_timeout(250)


class NaverPublisher:
    def __init__(self, blog_id: str, profile_dir: Path, shots_dir: Path, headless: bool = False,
                 write_url: str = WRITE_URL, login_marker: str = LOGIN_MARKER):
        self.blog_id = blog_id
        self.profile_dir = Path(profile_dir)
        self.shots_dir = Path(shots_dir)
        self.headless = headless
        self.write_url = write_url
        self.login_marker = login_marker
        self._pw = None
        self._ctx = None
        self._dialogs: List[str] = []

    def __enter__(self) -> "NaverPublisher":
        self._pw = sync_playwright().start()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._ctx = self._pw.chromium.launch_persistent_context(
            str(self.profile_dir), headless=self.headless, locale="ko-KR",
            viewport={"width": 1280, "height": 900})
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self._ctx:
                self._ctx.close()
        finally:
            if self._pw:
                self._pw.stop()

    # ── 한 편 올리기 ──────────────────────────────────────────────
    def publish(self, post: Post, images: Dict[str, Path], before_final_click: Callable[[], None],
                dry_run: bool = False) -> Optional[str]:
        """올린 글 주소를 돌려준다. dry_run 이면 발행 창까지만 채우고 None."""
        page = self._ctx.new_page()
        self._dialogs = []
        page.on("dialog", self._on_dialog)
        clicked_final = False
        try:
            frame = self._open_editor(page)
            self._dismiss_popups(frame)
            self._fill_title(frame, post.title)
            self._fill_body(page, frame, post.segments, images)
            self._verify_body(frame, post)
            confirm = self._open_publish_layer(frame)
            self._set_category(frame, post.category)
            self._set_tags(page, frame, post.tags)
            if dry_run:
                shot = self._shot(page, "dryrun")
                log.info("시험 실행: 발행 직전에서 멈춤. 화면 저장: %s", shot)
                return None
            before_final_click()   # 여기서 기록 저장이 실패하면 예외 → 발행을 누르지 않는다
            seen_urls = {f.url for f in page.frames}
            clicked_final = True
            confirm.click()
            url = self._wait_post_url(page, seen_urls)
            if not url:
                raise AmbiguousPublishError("발행은 눌렀는데 글 주소가 안 나왔어요" + self._dialog_note())
            return url
        except (NotLoggedInError, EditorError, AmbiguousPublishError):
            self._shot(page, "fail")
            raise
        except PlaywrightError as e:
            self._shot(page, "fail")
            if clicked_final:
                raise AmbiguousPublishError(f"발행 누른 뒤 오류: {e}") from e
            raise EditorError(f"화면 조작 오류: {e}{self._dialog_note()}") from e
        finally:
            try:
                page.close()
            except PlaywrightError:
                pass

    def _on_dialog(self, dialog) -> None:
        self._dialogs.append(dialog.message)
        log.info("네이버 알림창: %s", dialog.message)
        dialog.dismiss()

    def _dialog_note(self) -> str:
        return (" / 알림창: " + " | ".join(self._dialogs)) if self._dialogs else ""

    def _shot(self, page: Page, kind: str) -> Optional[Path]:
        try:
            self.shots_dir.mkdir(parents=True, exist_ok=True)
            path = self.shots_dir / f"{kind}-{datetime.now():%Y%m%d-%H%M%S}.png"
            page.screenshot(path=str(path))
            return path
        except PlaywrightError:
            return None

    def _is_login_page(self, page: Page) -> bool:
        return any(self.login_marker in (f.url or "") for f in page.frames)

    def _open_editor(self, page: Page) -> Frame:
        page.goto(self.write_url.format(blog_id=self.blog_id), wait_until="domcontentloaded")
        deadline = time.monotonic() + T_EDITOR_MS / 1000
        while True:
            if self._is_login_page(page):
                raise NotLoggedInError("네이버 로그인이 필요해요")
            for fr in page.frames:   # 글쓰기 화면은 mainFrame 안에 뜨기도 하고 바로 뜨기도 해서 다 찾아본다
                try:
                    if fr.locator(SELECTORS["title"][0]).count() or fr.locator(SELECTORS["title"][-1]).count():
                        return fr
                except PlaywrightError:
                    continue
            if time.monotonic() >= deadline:
                raise EditorError("글쓰기 화면을 못 찾았어요(네이버 화면이 바뀌었을 수 있음)")
            page.wait_for_timeout(300)

    def _dismiss_popups(self, frame: Frame) -> None:
        for key in ("popup_cancel", "help_close"):
            btn = _first_visible(frame, SELECTORS[key], T_SHORT_MS)
            if btn:
                btn.click()

    def _fill_title(self, frame: Frame, title: str) -> None:
        box = _first_visible(frame, SELECTORS["title"], T_SHORT_MS)
        if not box:
            raise EditorError("제목 칸을 못 찾았어요")
        box.click()
        frame.page.keyboard.insert_text(title)
        if not _wait_until(frame, lambda: _squash(title) in _squash(box.inner_text()), T_SHORT_MS):
            raise EditorError("제목이 안 들어갔어요")

    def _fill_body(self, page: Page, frame: Frame, segments: List[Segment], images: Dict[str, Path]) -> None:
        for seg in segments:
            if seg.kind == "image":
                self._insert_image(page, frame, images[seg.image_path])
            else:
                self._insert_html(page, frame, seg)

    def _body_text(self, frame: Frame) -> str:
        return _squash(" ".join(frame.locator(SELECTORS["text_component"]).all_inner_texts()))

    def _focus_end(self, page: Page, frame: Frame) -> None:
        """본문 맨 끝 글 칸에 커서를 둔다. 맨 끝이 사진이면 그 뒤에 빈 글 칸을 만든다."""
        last = frame.locator(SELECTORS["component"]).last
        if last.count() and not last.evaluate("el => el.classList.contains('se-text')"):
            last.click()
            page.keyboard.press("Enter")
            last = frame.locator(SELECTORS["component"]).last
            if not last.evaluate("el => el.classList.contains('se-text')"):
                raise EditorError("사진 뒤에 글을 이어 쓸 칸을 못 만들었어요")
        para = frame.locator(SELECTORS["body_paragraph"]).last
        if not para.count():
            raise EditorError("본문 칸을 못 찾았어요")
        para.click()
        para.evaluate(CARET_END_JS)

    def _insert_html(self, page: Page, frame: Frame, seg: Segment) -> None:
        self._focus_end(page, frame)
        probe = _squash(seg.text)[:15]
        before = len(self._body_text(frame))
        handled = frame.evaluate(PASTE_JS, [seg.html, seg.text])
        if handled:
            # 에디터가 받았다고 했는데 글이 안 보이면 직접 치지 않는다(나중에 들어와 두 번 써질 수 있어서)
            if _wait_until(frame, lambda: len(self._body_text(frame)) > before
                           and probe in self._body_text(frame), 10000):
                return
            raise EditorError(f"붙여넣은 본문이 안 보여요: {seg.text[:30]}")
        # 붙여넣기를 에디터가 아예 안 받았으면 서식 없이 한 줄씩 친다(글이 빠지는 것보다 낫다)
        log.warning("붙여넣기가 안 돼서 글자만 직접 입력해요(굵게·목록 등 서식 빠짐)")
        for i, line in enumerate(html_to_lines(seg.html)):
            if i:
                page.keyboard.press("Enter")
            page.keyboard.insert_text(line)

    def _insert_image(self, page: Page, frame: Frame, path: Path) -> None:
        self._focus_end(page, frame)
        images = frame.locator(SELECTORS["image_component"])
        before = images.count()
        btn = _first_visible(frame, SELECTORS["image_button"], T_SHORT_MS)
        if not btn:
            raise EditorError("사진 버튼을 못 찾았어요")
        with page.expect_file_chooser(timeout=15000) as chooser:
            btn.click()
        chooser.value.set_files(str(path))
        if not _wait_until(frame, lambda: images.count() > before, T_IMAGE_MS):
            raise EditorError(f"사진이 안 들어갔어요: {path.name}")
        img = images.last.locator("img").first
        if not _wait_until(frame, lambda: img.evaluate(IMG_READY_JS), T_IMAGE_MS):
            raise EditorError(f"사진 올리기가 안 끝났어요: {path.name}")
        page.wait_for_timeout(800)  # 사진 서버 업로드가 화면 표시보다 조금 늦게 끝나는 것 대비

    def _verify_body(self, frame: Frame, post: Post) -> None:
        """발행 전에 글·사진이 다 들어갔는지 확인 — 빠진 채로 올라가는 것 방지."""
        want_images = len(post.image_paths)
        got_images = frame.locator(SELECTORS["image_component"]).count()
        if got_images != want_images:
            raise EditorError(f"사진 개수가 안 맞아요(넣을 것 {want_images}, 들어간 것 {got_images})")
        body = self._body_text(frame)
        for seg in post.segments:
            if seg.kind == "html" and _squash(seg.text)[:15] not in body:
                raise EditorError(f"본문 일부가 안 들어갔어요: {seg.text[:30]}")

    def _open_publish_layer(self, frame: Frame) -> Locator:
        btn = _first_visible(frame, SELECTORS["publish_open"], T_SHORT_MS)
        if not btn:
            raise EditorError("[발행] 버튼을 못 찾았어요")
        btn.click()
        confirm = _first_visible(frame, SELECTORS["publish_confirm"], 8000)
        if not confirm:
            raise EditorError("발행 설정 창이 안 열렸어요")
        return confirm

    def _set_category(self, frame: Frame, category: str) -> None:
        if not category:
            return
        opener = _first_visible(frame, SELECTORS["category_open"], T_SHORT_MS)
        if not opener:
            raise EditorError("카테고리 선택 칸을 못 찾았어요")
        opener.click()
        option = frame.locator(SELECTORS["category_list"]).get_by_text(category, exact=True)
        if not _wait_until(frame, lambda: option.count() > 0 and option.first.is_visible(), T_SHORT_MS):
            raise EditorError(f"블로그에 '{category}' 카테고리가 없어요")
        option.first.click()

    def _set_tags(self, page: Page, frame: Frame, tags: List[str]) -> None:
        if not tags:
            return
        box = _first_visible(frame, SELECTORS["tag_input"], T_SHORT_MS)
        if not box:
            raise EditorError("태그 칸을 못 찾았어요")
        for tag in tags:
            box.click()
            page.keyboard.insert_text(tag)
            page.keyboard.press("Enter")

    def _wait_post_url(self, page: Page, seen_urls: set) -> Optional[str]:
        """발행 뒤 새로 열린 글 주소(logNo)를 찾는다. 발행 전부터 있던 주소는 무시."""
        patterns = [re.compile(r"[?&]logNo=(\d+)"),
                    re.compile(r"blog\.naver\.com/" + re.escape(self.blog_id) + r"/(\d+)")]
        deadline = time.monotonic() + T_AFTER_PUBLISH_MS / 1000
        while time.monotonic() < deadline:
            for fr in page.frames:
                if fr.url in seen_urls:
                    continue
                for pat in patterns:
                    m = pat.search(fr.url or "")
                    if m:
                        return f"https://blog.naver.com/{self.blog_id}/{m.group(1)}"
            page.wait_for_timeout(500)
        return None


def interactive_login(profile_dir: Path, login_url: str = LOGIN_URL, wait_seconds: int = 600) -> bool:
    """로그인 창을 띄우고 사장님이 직접 로그인할 때까지 기다린다. 로그인 정보는 profile_dir 에만 남는다."""
    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(profile_dir), headless=False, locale="ko-KR", viewport=None)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(login_url)
        print("열린 창에서 네이버에 로그인하세요. ('로그인 상태 유지'를 꼭 켜 주세요)")
        deadline = time.monotonic() + wait_seconds
        try:
            while time.monotonic() < deadline:
                names = {c["name"] for c in ctx.cookies(["https://nid.naver.com", "https://blog.naver.com"])}
                if all(n in names for n in AUTH_COOKIES):
                    page.wait_for_timeout(1500)
                    print("로그인 확인됐어요. 창을 닫습니다.")
                    return True
                page.wait_for_timeout(1000)
        except PlaywrightError:
            print("창이 닫혔어요.")
            return False
        finally:
            try:
                ctx.close()
            except PlaywrightError:
                pass
    print("시간 안에 로그인이 안 됐어요. 다시 해 주세요.")
    return False
