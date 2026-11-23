"""완성본 → 발행기 입력 변환 시험(표·쇼츠·제휴·내부 링크·색·고지) + 마지막 관문(blog_policy)."""
from pathlib import Path

import blog_policy
import neo_source


# ── blog_policy (RULE_VERSION 1.3) ─────────────────────
def test_policy_tags_10_to_15_and_brand():
    tags = [blog_policy.BRAND_TAG] + [f"t{i}" for i in range(9)]
    assert blog_policy.check("제목", "본문", tags) == []
    assert any("10~15" in p for p in blog_policy.check("제목", "본문", tags[:9]))
    assert any("10~15" in p for p in blog_policy.check("제목", "본문", tags + [f"x{i}" for i in range(7)]))
    assert any(blog_policy.BRAND_TAG in p for p in blog_policy.check("제목", "본문", tags[1:]))


def test_policy_rule_version_and_legacy_tag():
    assert blog_policy.RULE_VERSION == "1.3"
    assert blog_policy.REQUIRED_TAG == "서준의여행한입"
    tags = [blog_policy.BRAND_TAG] + [f"t{i}" for i in range(9)] + [blog_policy.LEGACY_TAG]
    assert blog_policy.check("제목", "본문", tags) == []      # 옛 태그는 막지 않는다


def test_policy_counts_faq_with_bold_heading():
    body = "■ **자주 묻는 질문**\n\n1. 주차?\n\n됩니다.\n\n2. 얼마?\n\n만원.\n\n3. 언제?\n\n평일.\n"
    assert blog_policy.count_faq(body) == 3
    body4 = body + "\n4. 또?\n\n없습니다.\n"
    assert any("3개까지" in p for p in blog_policy.check("제목", body4, [blog_policy.BRAND_TAG] + [f"t{i}" for i in range(9)]))


# ── neo_source 표기 ───────────────────────────────────
def test_pipe_table_becomes_html_table():
    html = neo_source.render_block(["| 순서 | 장소 |", "| --- | --- |", "| 1 | 샘플덮밥 |"])
    assert "<table" in html and "<th" in html and "<td" in html
    assert "샘플덮밥" in html and "|" not in html.split("<table")[1].split("</table>")[0].replace("|", "|")[:0] + ""
    assert html.count("<tr>") == 2


def test_numbered_quote_heading_becomes_bold_heading():
    html = neo_source.render_block(["> 1. **코스 한눈에**"])
    assert html.startswith("<h3><strong>") and "코스 한눈에" in html and "**" not in html


def test_one_liner_becomes_blockquote():
    html = neo_source.render_block(["【한줄평】 주차 무료라 4,000원 값"])
    assert html.startswith("<blockquote><p><strong>") and "4,000원" in html


def test_body_default_color_is_dark_gray():
    html = neo_source.render_block(["본문 한 줄"])
    assert "color:#333333" in html and "#000" not in html


def test_point_colors_teal_and_orange():
    assert "<span style=\"color:#168F88\">청록</span>" in neo_source.render_inline("{청록: 청록}")
    assert "<span style=\"color:#E58A35\">주황</span>" in neo_source.render_inline("{주황: 주황}")


def test_marker_lines_become_their_own_segments():
    body = "\n".join([
        "본문", "",
        "【장소】 샘플덮밥 세마점 | 경기도 오산시 샘플로 12", "",
        "【쇼츠】 다녀온 영상 https://www.youtube.com/shorts/dQw4w9WgXcQ", "",
        "【제휴】 가격 확인하기 https://shopping.naver.com/connect/b", "",
        "【링크】 지난 글 https://blog.naver.com/mose_love/224459436953", "",
    ])
    errs = []
    segs = neo_source.build_segments(body, errs)
    kinds = [s.kind for s in segs]
    assert "place" in kinds and "shorts" in kinds and "ad" in kinds and "link" in kinds
    place = next(s for s in segs if s.kind == "place")
    assert place.addr_tokens == ["오산시", "샘플로"]
    assert not errs


def test_invalid_shorts_and_map_url_reported():
    errs = []
    neo_source.build_segments("【쇼츠】 영상 https://www.youtube.com/watch?v=x\n", errs)
    neo_source.build_segments("【지도】 https://blog.naver.com/x\n", errs)
    assert any("쇼츠" in e for e in errs) and any("구글 지도" in e for e in errs)


def test_ai_note_is_removed_but_disclosure_is_not():
    errs = []
    segs = neo_source.build_segments(
        "직접 다녀온 기록을 AI 도움으로 정리했고, 그림은 AI로 만든 일러스트입니다.\n\n"
        "이 글에는 네이버 쇼핑 커넥트 제휴 링크가 있어요. 링크로 구매하시면 저에게 수수료가 적립돼요.\n"
        "내돈내산 · 2026년 11월 16일 방문\n", errs)
    text = " ".join(s.text for s in segs)
    assert "AI" not in text
    assert "수수료" in text and "내돈내산" in text


def test_blank_lines_survive_as_empty_paragraphs():
    segs = []
    html = neo_source.render_block(["사진 설명", "", "본문"])
    assert "<p><br></p>" in html
