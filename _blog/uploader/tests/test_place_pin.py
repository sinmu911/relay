"""지도 장소 핀 주소 대조 시험 — 화암사 글의 '바다정원' 오매핑이 다시 나지 않는지.

사고: 2026-10-22 화암사 글에서 '바다정원' 핀이 강원 고성이 아니라 서울 동대문구로 꽂혔다.
원인: 이름으로 검색해 첫 '추가' 버튼을 누르는 코드. 주소를 보지 않았다.
"""
import place_pin


GOSEONG = {"name": "바다정원", "addr": "강원특별자치도 고성군 죽왕면 바다정원길 12"}
DONGDAEMUN = {"name": "바다정원", "addr": "서울특별시 동대문구 전농로 100"}


def test_tokens_from_road_address():
    assert place_pin.addr_tokens("경기도 오산시 샘플로 12") == ["오산시", "샘플로"]
    assert place_pin.addr_tokens("강원특별자치도 고성군 죽왕면 바다정원길 12") == ["고성군", "바다정원길"]
    assert place_pin.addr_tokens("") == []


def test_picks_matching_candidate_even_when_second():
    tokens = place_pin.addr_tokens("강원특별자치도 고성군 죽왕면 바다정원길 12")
    got = place_pin.choose([DONGDAEMUN, GOSEONG], tokens)
    assert got["index"] == 1 and "고성군" in got["reason"]


def test_skips_when_only_wrong_town_matches():
    tokens = place_pin.addr_tokens("강원특별자치도 고성군 죽왕면 바다정원길 12")
    got = place_pin.choose([DONGDAEMUN, {"name": "바다정원", "addr": "부산광역시 해운대구 해운대로 1"}], tokens)
    assert got["index"] is None and "불일치" in got["reason"]


def test_skips_when_addresses_unreadable():
    tokens = place_pin.addr_tokens("경기도 오산시 샘플로 12")
    got = place_pin.choose([{"name": "샘플덮밥 세마점", "addr": ""}], tokens)
    assert got["index"] is None and "읽지 못함" in got["reason"]


def test_skips_when_no_tokens():
    got = place_pin.choose([GOSEONG], [])
    assert got["index"] is None and "토큰" in got["reason"]


def test_only_checks_first_three_candidates():
    tokens = place_pin.addr_tokens("경기도 오산시 샘플로 12")
    cands = [{"name": "x", "addr": "서울특별시 중구 세종대로 1"}] * 3 + [
        {"name": "샘플덮밥 세마점", "addr": "경기도 오산시 샘플로 12"}]
    assert place_pin.choose(cands, tokens)["index"] is None


def test_map_and_shorts_url_checks():
    assert place_pin.is_google_maps("https://maps.app.goo.gl/abc123")
    assert place_pin.is_google_maps("https://www.google.com/maps/place/x")
    assert not place_pin.is_google_maps("https://blog.naver.com/mose_love/1")
    assert place_pin.is_youtube_shorts("https://www.youtube.com/shorts/dQw4w9WgXcQ")
    assert place_pin.is_youtube_shorts("https://youtu.be/dQw4w9WgXcQ")
    assert not place_pin.is_youtube_shorts("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert not place_pin.is_youtube_shorts("https://blog.naver.com/x")


def test_pin_line_ok_messages():
    assert place_pin.pin_line_ok("【장소】 샘플덮밥 세마점 | 경기도 오산시 샘플로 12") is None
    assert "주소를 함께" in place_pin.pin_line_ok("【장소】 샘플덮밥 세마점")
    assert "못 읽었어요" in place_pin.pin_line_ok("【장소】 어딘가 | 12-3")
