"""팩트 게이트(F1~F17) 시험 — 값이 없으면 BLOCK, 사람이 볼 것이면 REVIEW."""
import copy
from datetime import date, timedelta

import fact_gate
from course_helpers import sample_course

TODAY = date(2026, 11, 20)


def run(course):
    return fact_gate.check(course, today=TODAY)


def codes(rep, state):
    return [x["코드"] for x in rep["항목"] if x["판정"] == state]


def test_clean_course_has_no_block():
    rep = run(sample_course())
    assert rep["BLOCK"] == 0, rep["블록"]
    assert rep["통과"]


def test_missing_address_blocks():
    c = sample_course()
    c["places"][0]["addr_road"] = ""
    rep = run(c)
    assert "F1" in codes(rep, "BLOCK")


def test_domestic_needs_coords_and_naver_source():
    c = sample_course()
    c["places"][0]["lat"] = None
    c["places"][0]["map_source"] = "kakao"
    rep = run(c)
    assert "F10" in codes(rep, "BLOCK")


def test_overseas_needs_google_values():
    c = sample_course()
    p = c["places"][0]
    p.update(map_source="google", google_place_name="Example Tower")
    rep = run(c)
    assert "F11" in codes(rep, "BLOCK")
    p.update(google_addr="1 Example St", google_maps_url="https://maps.app.goo.gl/abc123")
    rep2 = run(c)
    assert "F11" not in codes(rep2, "BLOCK")


def test_price_without_basis_date_blocks():
    c = sample_course()
    c["places"][0]["price_items"][0]["basis_date"] = ""
    assert "F3" in codes(run(c), "BLOCK")


def test_stale_hours_is_review():
    c = sample_course()
    c["places"][0]["verified_at"] = (TODAY - timedelta(days=45)).isoformat()
    rep = run(c)
    assert "F2" in codes(rep, "REVIEW")


def test_missing_parking_is_review_and_compose_omits_line():
    c = sample_course()
    c["places"][0]["parking"] = {}
    assert "F4" in codes(run(c), "REVIEW")
    from course_compose import compose
    body = compose(c).body
    assert "주차: " not in body.split("> 2.")[1].split("> 3.")[0]


def test_missing_visit_date_blocks():
    c = sample_course()
    c["visit_date"] = ""
    assert "F8" in codes(run(c), "BLOCK")


def test_unknown_order_is_review():
    c = sample_course()
    c["order_status"] = "UNKNOWN"
    assert "F9" in codes(run(c), "REVIEW")


def test_far_apart_places_blocked():
    c = sample_course()
    c["places"][1]["lat"], c["places"][1]["lng"] = 35.16, 129.16      # 부산
    assert "F6" in codes(run(c), "BLOCK")


def test_search_result_address_mismatch_blocks_pin():
    c = sample_course()
    c["places"][0]["search_result_addr"] = "서울특별시 동대문구 전농로 100"
    rep = run(c)
    assert "F5" in codes(rep, "BLOCK")


def test_shorts_required_and_validated():
    c = sample_course()
    c["places"][0]["shorts"] = {}
    assert "F14" in codes(run(c), "REVIEW")
    c["places"][0]["shorts"] = {"url": "https://www.youtube.com/watch?v=abc"}
    assert "F14" in codes(run(c), "BLOCK")
    c["places"][0]["shorts"] = {"url": "https://www.youtube.com/shorts/aBcDeF12345", "place": "다른집"}
    assert "F14" in codes(run(c), "REVIEW")


def test_review_count_too_small_is_review():
    c = sample_course()
    c["places"][0]["reviews"]["count"] = 2
    assert "F15" in codes(run(c), "REVIEW")


def test_affiliate_slots_must_include_middle_and_end():
    c = sample_course()
    c["affiliates"] = [{"slot": "E", "provider": "naver_connect", "label": "확인하기",
                        "url": "https://shopping.naver.com/x"}]
    assert "F17" in codes(run(c), "REVIEW")


# ── F13 허위 경험 ──────────────────────────────────────
def test_taste_claim_for_unordered_menu_blocks():
    c = sample_course()
    body = "샘플튀김은 바삭했습니다."
    items = fact_gate.claim_items(body, c)
    assert items[0]["판정"] == "BLOCK" and "샘플튀김" in items[0]["내용"]


def test_taste_claim_with_review_source_passes():
    c = sample_course()
    body = "방문자 리뷰에서 샘플튀김이 바삭하다는 말이 많았어요."
    items = fact_gate.claim_items(body, c)
    assert items[0]["판정"] == "OK"


def test_taste_claim_for_ordered_menu_passes():
    c = sample_course()
    body = "샘플덮밥은 간이 세지 않고 딱 맞았습니다."
    assert fact_gate.claim_items(body, c)[0]["판정"] == "OK"
