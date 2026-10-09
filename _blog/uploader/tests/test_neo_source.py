"""블로그 섹션(블로그_NEO) 완성본 읽기 시험 — 형식은 블로그 섹션 완성본과 같은 모양의 시험용 글."""
import json
import os
import unicodedata
from datetime import datetime

import pytest

from github_store import StoreError
from naver_upload import Runner
from neo_source import KEY_PREFIX, NeoStore, parse_when
from queue_state import PUBLISHED, RunLock, StateFile
from sources import BlogFeed, MultiStore, find_similar

PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                    "0000000d49444154789c6360f8cf000000030101005d8a1e0b0000000049454e44ae426082")
BAR = "=" * 40
WANSEONG = f"""목표 검색어: 테스트 코스
글 종류: 일정 · 시리즈: [테스트 ①]
이미지: 대표 1 + 지도 1 = 2장 (폴더 `2026-10-14_테스트코스_이미지/`)

{BAR}
제목
{BAR}
[테스트 ①] 렌트카로 도는 하루 코스

{BAR}
본문
{BAR}
【그림 0】 테스트_00_대표.png

내돈내산 · 2026년 5월 다녀온 기록이에요.

첫 줄은 **굵게** 강조했어요.
{{파랑: 파란 글씨}} 도 있어요.

▶ 하루 비용 · 400디르함

← 이전 편: ① 준비 (발행 후 링크)


■ 하루 순서

【그림 1】 테스트_01_지도.png

👉 자세히 → 지난 글 https://blog.naver.com/mose_love/224288164082
<script>alert(1)</script> 같은 글자도 그대로 보여야 해요.
{BAR}
태그 (3개)
{BAR}
#테스트 #렌트카여행 #달리는이기사

{BAR}
점검
{BAR}
- 내부 메모: 이 줄은 올라가면 안 돼요
"""


def make_neo(tmp_path, posts=None, month="2026년 10월", text=WANSEONG, images=("테스트_00_대표.png", "테스트_01_지도.png")):
    root = tmp_path / "블로그_NEO"
    (root / "초안" / "2026-10-14_테스트코스_이미지").mkdir(parents=True)
    (root / "상태").mkdir()
    (root / "초안" / "2026-10-14_테스트코스_완성본.md").write_text(text, encoding="utf-8")
    for name in images:
        (root / "초안" / "2026-10-14_테스트코스_이미지" / name).write_bytes(PNG)
    if posts is None:
        posts = [{"id": "①", "md": "초안/2026-10-14_테스트코스_완성본.md", "when": "10/14(화) 20:22", "kind": "new"}]
    (root / "상태" / "자동발행_대기.json").write_text(json.dumps({"month": month, "posts": posts}, ensure_ascii=False),
                                                 encoding="utf-8")
    return root


def load_one(root, **kw):
    st = NeoStore(root, **kw)
    files = st.list_post_files()
    assert len(files) == 1
    return st, files[0], st.load_post(files[0])


def test_reads_blog_section_format(tmp_path):
    root = make_neo(tmp_path)
    _, f, post = load_one(root, default_category="두바이")
    assert f["path"] == KEY_PREFIX + "초안/2026-10-14_테스트코스_완성본.md"
    assert post.errors == []
    assert post.title == "[테스트 ①] 렌트카로 도는 하루 코스"
    assert post.tags == ["테스트", "렌트카여행", "달리는이기사"]
    assert post.publish_at == datetime(2026, 10, 14, 20, 22)
    assert post.category == "두바이" and post.status == "ready"
    assert [s.kind for s in post.segments] == ["image", "html", "image", "html"]
    assert post.image_paths == ["테스트_00_대표.png", "테스트_01_지도.png"]
    first, second = post.segments[1].html, post.segments[3].html
    assert "<strong>굵게</strong>" in first
    assert '<span style="color:#0075c8">파란 글씨</span>' in first
    assert "<p><strong>▶ 하루 비용 · 400디르함</strong></p>" in first
    assert "<p><strong>■ 하루 순서</strong></p>" in first
    assert "← 이전 편: ① 준비</p>" in first and "발행 후 링크" not in first   # 자리표시는 뺌
    assert '<a href="https://blog.naver.com/mose_love/224288164082">' in second
    assert "&lt;script&gt;" in second and "<script>" not in second
    everything = "".join(s.html for s in post.segments)
    assert "내부 메모" not in everything and "목표 검색어" not in everything   # 점검·머리글은 안 올라감
    assert "<p><br></p>" in first                                               # 빈 줄 = 빈 문단


def test_edit_kind_and_duplicates_are_skipped(tmp_path):
    md = "초안/2026-10-14_테스트코스_완성본.md"
    root = make_neo(tmp_path, posts=[
        {"id": "①", "md": md, "when": "10/14(화) 20:22", "kind": "new"},
        {"id": "①again", "md": "초안/../초안/2026-10-14_테스트코스_완성본.md", "when": "10/15(수) 20:22", "kind": "new"},
        {"id": "②-a", "md": md, "when": "10/20(화) 21:05", "kind": "edit", "edit_link": "https://blog.naver.com/x/1"},
    ])
    files = NeoStore(root).list_post_files()
    assert [f["entry"]["id"] for f in files] == ["①"]


def test_absolute_path_from_other_mac_user_is_mapped(tmp_path):
    other = "/Users/someone/Library/CloudStorage/GoogleDrive-x/내 드라이브/블로그_NEO/도구/../초안/2026-10-14_테스트코스_완성본.md"
    root = make_neo(tmp_path, posts=[{"id": "①", "md": other, "when": "2026-10-14 20:22", "kind": "new"}])
    _, f, post = load_one(root)
    assert f["path"] == KEY_PREFIX + "초안/2026-10-14_테스트코스_완성본.md" and post.errors == []


def test_path_outside_folder_is_refused(tmp_path):
    root = make_neo(tmp_path, posts=[{"id": "x", "md": "../../etc/passwd", "when": "2026-10-14 20:22"}])
    _, _, post = load_one(root)
    assert post.errors and "밖" in post.errors[0]


def test_missing_image_file_and_folder(tmp_path):
    root = make_neo(tmp_path, images=("테스트_00_대표.png",))
    assert any("테스트_01_지도.png" in e for e in load_one(root)[2].errors)
    root2 = make_neo(tmp_path / "b", text=WANSEONG.replace("(폴더 `2026-10-14_테스트코스_이미지/`)", ""), images=())
    os.rmdir(root2 / "초안" / "2026-10-14_테스트코스_이미지")
    assert any("그림 폴더" in e for e in load_one(root2)[2].errors)


def test_bad_or_missing_when(tmp_path):
    root = make_neo(tmp_path, posts=[{"id": "①", "md": "초안/2026-10-14_테스트코스_완성본.md", "when": "다음주", "kind": "new"}])
    assert any("발행 시각" in e for e in load_one(root)[2].errors)


def test_missing_sections_and_file(tmp_path):
    root = make_neo(tmp_path, text="그냥 글")
    assert any("제목" in e for e in load_one(root)[2].errors)
    root2 = make_neo(tmp_path / "b", posts=[{"id": "①", "md": "초안/없는파일_완성본.md", "when": "2026-10-14 20:22"}])
    assert any("못 읽어요" in e for e in load_one(root2)[2].errors)


def test_parse_when_formats():
    assert parse_when("10/14(화) 20:22", "2026년 10월") == datetime(2026, 10, 14, 20, 22)
    assert parse_when("1/05(월) 09:00", "2026년 12월") == datetime(2027, 1, 5, 9, 0)
    assert parse_when("2026-10-14T20:22", "") == datetime(2026, 10, 14, 20, 22)
    assert parse_when("10/14 20:22", "") is None          # 연도 단서 없음
    assert parse_when("13/40(화) 20:22", "2026년 10월") is None


def test_nfd_file_names_on_mac(tmp_path):
    nfd = unicodedata.normalize("NFD", "테스트_01_지도.png")
    root = make_neo(tmp_path, images=("테스트_00_대표.png", nfd))
    st, _, post = load_one(root)
    assert post.errors == []
    out = st.fetch_images(post, tmp_path)
    assert set(out) == {"테스트_00_대표.png", "테스트_01_지도.png"} and all(p.exists() for p in out.values())


def test_mirror_written_only_when_changed(tmp_path):
    root = make_neo(tmp_path)
    st = NeoStore(root)
    state = {"posts": {"neo:a.md": {"status": "published"}, "_blog/posts/x.md": {"status": "published"}}}
    st.put_state(state, None)
    data = json.loads((root / "상태" / "자동발행_기록.json").read_text(encoding="utf-8"))
    assert list(data["posts"]) == ["neo:a.md"]           # 글쓰기 화면 글은 안 섞음
    before = (root / "상태" / "자동발행_기록.json").stat().st_mtime_ns
    st.put_state(state, None)
    assert (root / "상태" / "자동발행_기록.json").stat().st_mtime_ns == before
    assert st.get_state()[0]["posts"] == {"neo:a.md": {"status": "published"}}


def test_no_queue_file_means_nothing_to_do(tmp_path):
    root = make_neo(tmp_path)
    (root / "상태" / "자동발행_대기.json").unlink()
    assert NeoStore(root).list_post_files() == []
    with pytest.raises(StoreError):
        NeoStore(tmp_path / "없음").list_post_files()
    (root / "상태" / "자동발행_대기.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(StoreError):
        NeoStore(root).list_post_files()


class Pub:
    def __init__(self):
        self.posts = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def publish(self, post, images, before_final_click, dry_run=False):
        assert [p.name for p in images.values()] == post.image_paths
        before_final_click()
        self.posts.append(post.title)
        return "https://blog.naver.com/mose_love/1"


def test_runner_publishes_blog_section_post_once_at_its_time(tmp_path):
    root = make_neo(tmp_path)
    pub = Pub()
    now = {"t": datetime(2026, 10, 14, 20, 0)}

    def runner():
        return Runner({"max_attempts": 3, "max_posts_per_run": 1}, MultiStore([NeoStore(root)]),
                      StateFile(tmp_path / "state.json"), RunLock(tmp_path / "l"), lambda: pub,
                      lambda t, m: None, now_fn=lambda: now["t"])
    assert runner().run() == []                       # 20:22 전엔 안 올림
    now["t"] = datetime(2026, 10, 14, 20, 25)
    assert runner().run() == ["published:neo:초안/2026-10-14_테스트코스_완성본.md"]
    assert runner().run() == []
    assert pub.posts == ["[테스트 ①] 렌트카로 도는 하루 코스"]
    mirror = json.loads((root / "상태" / "자동발행_기록.json").read_text(encoding="utf-8"))
    assert mirror["posts"]["neo:초안/2026-10-14_테스트코스_완성본.md"]["status"] == PUBLISHED


class BrokenStore:
    def list_post_files(self):
        raise StoreError("GitHub 끊김")

    def get_state(self):
        raise StoreError("GitHub 끊김")


def test_one_broken_source_does_not_stop_the_other(tmp_path):
    root = make_neo(tmp_path)
    ms = MultiStore([BrokenStore(), NeoStore(root)])
    assert ms.get_state()[0] == {"posts": {}}
    assert [f["path"] for f in ms.list_post_files()] == [KEY_PREFIX + "초안/2026-10-14_테스트코스_완성본.md"]
    with pytest.raises(StoreError):
        MultiStore([BrokenStore()]).list_post_files()


def test_blog_feed_parses_rss_and_similarity():
    rss = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>달리는 이기사</title>
    <item><title><![CDATA[[두바이 ②] 두바이 렌트카 처음이라면]]></title><link>https://blog.naver.com/mose_love/1</link></item>
    <item><title>망원시장 김 후기</title></item></channel></rss>""".encode("utf-8")
    calls = []
    feed = BlogFeed("mose_love", fetch=lambda url: calls.append(url) or rss)
    assert feed.titles() == ["[두바이 ②] 두바이 렌트카 처음이라면", "망원시장 김 후기"]
    feed.titles()
    assert calls == ["https://rss.blog.naver.com/mose_love.xml"]          # 한 번만 받음
    assert find_similar("[두바이 ②]  두바이 렌트카 처음이라면!", feed.titles())
    assert not find_similar("[두바이 ③] 렌트카로 하루 만에 도는 아부다비 코스", feed.titles())
    with pytest.raises(StoreError):
        BlogFeed("x", fetch=lambda url: b"<rss><broken").titles()
