"""조립기 시험 — 사실이 없으면 문장을 만들지 않고, 있으면 규칙대로 배치한다."""
import re

from course_compose import compose
from course_helpers import sample_course


def test_title_is_22_to_30_chars_with_number():
    rep = compose(sample_course())
    plain = re.sub(r"\s", "", rep.title)
    assert 22 <= len(plain) <= 30 and re.search(r"\d", rep.title)
    assert rep.title.count("?") <= 1 and rep.title.count(",") <= 1


def test_intro_has_three_paragraphs_and_disclosure():
    rep = compose(sample_course())
    head = rep.body.split("> 1.")[0]
    paras = [p for p in head.split("\n\n") if p.strip() and not p.startswith(("【", "▶", "="))]
    assert len(paras) == 3
    assert "내돈내산" in paras[2] and "2026년 11월 16일" in paras[2]
    assert "수수료" in paras[2]


def test_affiliate_cards_at_middle_and_end():
    rep = compose(sample_course())
    body = rep.body
    lines = body.split("\n")
    idx = [i for i, l in enumerate(lines) if l.startswith("【제휴】")]
    assert len(idx) == 2
    total = len(re.sub(r"\s", "", body))
    pcts = [len(re.sub(r"\s", "", "\n".join(lines[:i + 1]))) * 100 / total for i in idx]
    assert 25 <= pcts[0] <= 45, pcts
    assert 80 <= pcts[1] <= 95, pcts


def test_missing_hours_and_parking_are_omitted_not_faked():
    c = sample_course()
    c["places"][0]["hours"] = {}
    c["places"][0]["parking"] = {}
    rep = compose(c)
    section = rep.body.split("> 2.")[1].split("> 3.")[0]
    assert "영업:" not in section and "주차:" not in section
    assert any("영업시간" in o for o in rep.omitted)
    assert any("주차" in o for o in rep.omitted)


def test_missing_shorts_leaves_link_out():
    c = sample_course()
    c["places"][0]["shorts"] = {}
    rep = compose(c)
    assert len([l for l in rep.body.split("\n") if l.startswith("【쇼츠】")]) == 1
    assert any("쇼츠" in o for o in rep.omitted)


def test_no_placeholder_left_behind():
    c = sample_course()
    c["places"][0]["story"] = []
    c["cost"]["items"] = []
    rep = compose(c)
    assert "[확인 필요]" not in rep.markdown and "[사장님 한 줄]" not in rep.markdown
    assert rep.unfilled and any("총비용" in u for u in rep.unfilled)


def test_tags_include_brand_and_stay_in_range():
    rep = compose(sample_course())
    assert 10 <= len(rep.tags) <= 15
    assert blog_brand() in rep.tags


def blog_brand():
    import gates
    return gates.BRAND_TAG


def test_story_text_is_not_rewritten():
    c = sample_course()
    c["places"][0]["story"] = ["첫 문장은 그대로 들어가야 합니다.", "둘째 문장도 그대로입니다."]
    rep = compose(c)
    assert "첫 문장은 그대로 들어가야 합니다." in rep.body
    assert "둘째 문장도 그대로입니다." in rep.body


def test_closing_and_faq_are_three_questions():
    rep = compose(sample_course())
    assert rep.body.count("【한줄평】") == 4
    faq = rep.body.split("자주 묻는 질문")[1]
    assert len([l for l in faq.split("\n") if re.match(r"^\d\. .+\?$", l.strip())]) == 3
    assert "댓글로" in rep.body
