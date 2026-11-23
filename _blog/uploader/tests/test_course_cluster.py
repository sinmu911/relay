"""코스 클러스터링(R1~R8)·동선 점검 시험 — 실데이터(2026-11-18 RSS) 사례로."""
import course_cluster as cc


def _p(name, role, lat, lng, visited="", date=""):
    return {"name": name, "role": role, "lat": lat, "lng": lng, "visited_at": visited, "visit_date": date}


OSAN_DEOBAP = _p("덮밥장사장 세마역점", "meal", 37.1889, 127.0419, "2026-10-29T11:40", "2026-10-29")
OSAN_CHUEO = _p("추막골 남원추어탕 본점", "meal", 37.1902, 127.0475, "2026-10-30T12:10", "2026-10-30")
OSAN_CAFE = _p("카페폴 오포점", "cafe", 37.1871, 127.0398, "2026-10-29T13:20", "2026-10-29")
MUJU = _p("덕유산", "sight", 35.86, 127.75, "2026-10-23T09:00", "2026-10-23")
GOSEONG = _p("화암사", "sight", 38.36, 128.44, "2026-10-22T10:00", "2026-10-22")


def test_role_duplicate_drops_second_meal():
    out = cc.cluster([OSAN_DEOBAP, OSAN_CHUEO], visit_date="2026-10-29")
    names = [p["name"] for p in out["places"]]
    assert names == ["덮밥장사장 세마역점"]
    assert any("R3" in d["why"] for d in out["dropped"])


def test_meal_then_cafe_is_a_course():
    out = cc.cluster([OSAN_DEOBAP, OSAN_CAFE], visit_date="2026-10-29")
    assert out["status"] == "half_day"
    assert [p["seq"] for p in out["places"]] == [1, 2]
    assert out["moves"][0]["method"] == "도보"


def test_unrelated_region_is_blocked():
    out = cc.cluster([MUJU, GOSEONG], visit_date="2026-10-22")
    assert len(out["places"]) == 1
    assert any("R7" in d["why"] for d in out["dropped"])


def test_date_window_drops_other_trip():
    out = cc.cluster([OSAN_DEOBAP, MUJU], visit_date="2026-10-29")
    assert any("R1" in d["why"] for d in out["dropped"])


def test_order_unknown_when_no_time_evidence():
    a = {k: v for k, v in OSAN_DEOBAP.items() if k != "visited_at"}
    b = {k: v for k, v in OSAN_CAFE.items() if k != "visited_at"}
    out = cc.cluster([a, b], visit_date="2026-10-29")
    assert out["order_status"] == "UNKNOWN"
    assert any("순서" in n for n in out["notes"])


def test_route_check_flags_meal_without_next_stop():
    r = cc.route_check([OSAN_DEOBAP])
    assert not r["ok"] and any("카페" in i for i in r["issues"])


def test_route_check_accepts_near_cafe():
    r = cc.route_check([OSAN_DEOBAP, OSAN_CAFE])
    assert r["ok"] and r["next_stop"] == "카페폴 오포점"


def test_route_check_flags_far_cafe():
    far = _p("먼카페", "cafe", 37.30, 127.20)
    r = cc.route_check([OSAN_DEOBAP, far])
    assert not r["ok"] and any("떨어져" in i for i in r["issues"])


def test_internal_link_skips_same_role():
    published = [{"log_no": "224459436953", "title": "추어탕 후기", "role": "meal"},
                 {"log_no": "224456901326", "title": "카페폴 후기", "role": "cafe"}]
    links = cc.link_candidates([OSAN_DEOBAP], published)
    assert [l["target_log_no"] for l in links] == ["224456901326"]
