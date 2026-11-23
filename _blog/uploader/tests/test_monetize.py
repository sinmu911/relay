"""수익 슬롯 분기 시험 — 맛집은 중간·마무리 직전 2개, 여행은 3개, 문구·중복·상한."""
import monetize
from course_helpers import sample_course


def test_local_type_gets_middle_and_end_cards():
    plan = monetize.plan(sample_course())
    assert plan["type"] == "local"
    assert [c["slot"] for c in plan["cards"]] == ["B", "E"]
    assert any("수수료" in d for d in plan["disclosure"])


def test_travel_type_gets_three_cards():
    c = sample_course(type="travel")
    c["affiliates"] = [
        {"slot": "B", "provider": "myrealtrip", "label": "내 날짜의 가격 확인하기", "url": "https://myrealt.rip/a"},
        {"slot": "C", "provider": "myrealtrip", "label": "같은 조건 예약 가능 날짜 보기", "url": "https://myrealt.rip/b"},
        {"slot": "E", "provider": "myrealtrip", "label": "예약 조건 확인하기", "url": "https://myrealt.rip/c"},
    ]
    plan = monetize.plan(c)
    assert plan["type"] == "travel"
    assert [x["slot"] for x in plan["cards"]] == ["B", "C", "E"]


def test_duplicate_url_dropped():
    c = sample_course()
    c["affiliates"][1]["url"] = c["affiliates"][0]["url"]
    plan = monetize.plan(c)
    assert len(plan["cards"]) == 1 and any("같은 링크" in i for i in plan["issues"])


def test_banned_cta_flagged():
    c = sample_course()
    c["affiliates"][0]["label"] = "지금 안 사면 손해"
    plan = monetize.plan(c)
    assert any("압박형" in i for i in plan["issues"])


def test_label_should_be_reader_action():
    c = sample_course()
    c["affiliates"][0]["label"] = "오산 카페"
    plan = monetize.plan(c)
    assert any("독자가 할 일" in i for i in plan["issues"])


def test_detect_type_from_places_when_missing():
    c = sample_course()
    c.pop("type", None)
    c["places"][0]["name"] = "오사카 호텔"
    assert monetize.detect_type(c) == "travel"


def test_missing_slot_reported():
    c = sample_course()
    c["affiliates"] = [{"slot": "B", "provider": "naver_connect", "label": "가격 확인하기",
                        "url": "https://shopping.naver.com/x"}]
    plan = monetize.plan(c)
    assert any("E 슬롯" in i for i in plan["issues"])
