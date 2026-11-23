"""코스형 게이트(B16~B28) 시험 — 좋은 글은 통과하고, 규칙 하나를 어기면 그 코드가 잡는지."""
import copy

import pytest

import gates
from course_compose import compose
from course_helpers import sample_course


def body_of(course=None):
    rep = compose(course or sample_course())
    return rep.body, rep.title, rep.tags


def codes(items, state="걸림"):
    return {i["코드"] for i in items if i["판정"] == state}


def test_clean_course_passes_all_gates():
    body, title, tags = body_of()
    items = gates.run(body, title, tags)
    stuck = [i for i in items if i["판정"] == "걸림"]
    assert stuck == [], stuck
    assert gates.is_course(body)


def test_emoji_blocks_publish():
    body, title, tags = body_of()
    bad = body.replace("11시 40분에 들어가니", "11시 40분에 들어가니 📍")
    items = gates.run(bad, title, tags)
    b20 = next(i for i in items if i["코드"] == "B20")
    assert b20["판정"] == "걸림" and "이모지" in b20["내용"]


def test_graphic_symbols_like_checkbox_also_blocked():
    body, title, tags = body_of()
    bad = body.replace("카드 결제만 됩니다.", "☐ 카드 결제만 됩니다.")
    b20 = next(i for i in gates.run(bad, title, tags) if i["코드"] == "B20")
    assert b20["판정"] == "걸림"


@pytest.mark.parametrize("count", [9, 16])
def test_tag_count_must_be_10_to_15(count):
    body, title, tags = body_of()
    many = [f"태그{i}" for i in range(count - 1)] + [gates.BRAND_TAG]
    b24 = next(i for i in gates.run(body, title, many) if i["코드"] == "B24")
    assert b24["판정"] == "걸림"


def test_brand_tag_required_and_legacy_tag_allowed():
    body, title, tags = body_of()
    no_brand = [t for t in tags if t != gates.BRAND_TAG]
    b24 = next(i for i in gates.run(body, title, no_brand) if i["코드"] == "B24")
    assert b24["판정"] == "걸림" and gates.BRAND_TAG in b24["내용"]
    with_legacy = [gates.LEGACY_TAG if i == 1 else t for i, t in enumerate(tags)]
    b24b = next(i for i in gates.run(body, title, with_legacy) if i["코드"] == "B24")
    assert b24b["판정"] != "걸림" and "달리는이기사" in b24b["내용"]


def test_missing_disclosure_blocks():
    course = sample_course()
    rep = compose(course)
    bad = rep.body.replace("내돈내산 · 2026년 11월 16일 방문", "2026년 11월 16일 방문")
    b18 = next(i for i in gates.run(bad, rep.title, rep.tags) if i["코드"] == "B18")
    assert b18["판정"] == "걸림" and "내돈내산" in b18["내용"]


def test_photo_not_separated_by_blank_line_blocks():
    body, title, tags = body_of()
    bad = body.replace("【그림 1】 01_대표.jpg\n\n▶", "【그림 1】 01_대표.jpg\n▶")
    b25 = next(i for i in gates.run(bad, title, tags) if i["코드"] == "B25")
    assert b25["판정"] == "걸림"


def test_heading_without_bold_blocks():
    body, title, tags = body_of()
    bad = body.replace("> 1. **코스 한눈에**", "> 1. 코스 한눈에")
    b26 = next(i for i in gates.run(bad, title, tags) if i["코드"] == "B26")
    assert b26["판정"] == "걸림" and "코스 한눈에" in b26["내용"]


def test_black_body_color_and_color_spam_blocked():
    body, title, tags = body_of()
    bad = body.replace("샘플덮밥 2그릇", "{검정: 샘플덮밥 2그릇}")
    b27 = next(i for i in gates.run(bad, title, tags) if i["코드"] == "B27")
    assert b27["판정"] == "걸림"
    spam = body.replace("11시 40분에 들어가니 앞 테이블",
                        "{주황: 11시 40분} {청록: 앞 테이블}")
    b27b = next(i for i in gates.run(spam, title, tags) if i["코드"] == "B27")
    assert b27b["판정"] != "OK" and "포인트" in b27b["내용"] or "색" in b27b["내용"]


def test_place_line_without_address_blocks_pin():
    body, title, tags = body_of()
    bad = body.replace("【장소】 샘플덮밥 세마점 | 경기도 오산시 샘플로 12", "【장소】 샘플덮밥 세마점")
    b23 = next(i for i in gates.run(bad, title, tags) if i["코드"] == "B23")
    assert b23["판정"] == "걸림" and "주소" in b23["내용"]


def test_overseas_map_must_be_google_link():
    body, title, tags = body_of()
    bad = body.replace("【그림 1】 01_대표.jpg", "【지도】 https://blog.naver.com/x\n\n【그림 1】 01_대표.jpg")
    b23 = next(i for i in gates.run(bad, title, tags) if i["코드"] == "B23")
    assert b23["판정"] == "걸림"


def test_slot_without_mid_body_card_blocks():
    course = sample_course()
    course["affiliates"] = [{"slot": "E", "provider": "naver_connect", "label": "가격 확인하기",
                             "url": "https://shopping.naver.com/connect/e"}]
    rep = compose(course)
    b17 = next(i for i in gates.run(rep.body, rep.title, rep.tags) if i["코드"] == "B17")
    assert b17["판정"] == "걸림" and "중간" in b17["내용"]


def test_shorts_and_internal_link_lines_are_parsed():
    body, title, tags = body_of()
    assert len([l for l in body.split("\n") if l.startswith("【쇼츠】")]) == 2
    assert len([l for l in body.split("\n") if l.startswith("【링크】")]) == 1
    assert "youtube.com/shorts" in body


def test_one_liner_count_and_reason():
    course = sample_course()
    course["places"] = course["places"][:1]
    course["moves"] = []
    rep = compose(course)
    b21 = next(i for i in gates.run(rep.body, rep.title, rep.tags) if i["코드"] == "B21")
    assert b21["판정"] == "걸림" and "4~5" in b21["내용"]
