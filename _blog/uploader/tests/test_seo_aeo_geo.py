"""SEO·AEO·GEO 지문 점검(B28) 시험 — 좋은 글은 OK, 빠지면 이유를 말한다."""
import seo_aeo_geo
from course_compose import compose
from course_helpers import sample_course


def test_clean_course_has_no_structural_issue():
    """시험 자료는 분량(1,800자)을 조금 못 채우므로 '분량' 말고 구조 문제가 없는지만 본다."""
    rep = compose(sample_course())
    item = seo_aeo_geo.check(rep.body, rep.title)
    content = item["내용"]
    for bad in ("자주 묻는 질문", "방문일", "최상급", "제목 낱말", "소제목", "영업·주차"):
        assert bad not in content, content
    assert "본문 " in content and "자(목표" in content


def test_missing_faq_is_flagged():
    rep = compose(sample_course())
    body = "\n".join(l for l in rep.body.split("\n") if "자주 묻는 질문" not in l and not l.strip().startswith(("1. ", "2. ", "3. ")))
    item = seo_aeo_geo.check(body, rep.title)
    assert item["판정"] == "주의" and "FAQ" in item["내용"]


def test_unverifiable_superlative_is_flagged():
    rep = compose(sample_course())
    body = rep.body.replace("이날 이어서", "가장 맛있는 집이에요. 이날 이어서")
    item = seo_aeo_geo.check(body, rep.title)
    assert "최상급" in item["내용"]


def test_short_body_is_flagged():
    item = seo_aeo_geo.check("짧은 글\n\n1. 주차?\n\n됩니다.\n", "오산 2곳")
    assert "본문" in item["내용"]


def test_missing_visit_date_is_flagged():
    rep = compose(sample_course())
    body = rep.body.replace("내돈내산 · 2026년 11월 16일 방문", "내돈내산")
    item = seo_aeo_geo.check(body, rep.title)
    assert "방문일" in item["내용"]
