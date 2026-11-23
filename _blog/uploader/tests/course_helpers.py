"""시험용 코스 자료 — course.json 과 같은 모양(값은 전부 지어낸 샘플).

실제 업소·금액이 아니다. 조립기와 게이트가 '무엇을 보고 무엇을 빼는지'만 확인한다.
"""
import copy

BASE = {
    "course_id": "test_osan",
    "type": "local",
    "region": {"sido": "경기", "sigungu": "오산시", "dong": "세교동"},
    "visit_date": "2026-11-16",
    "order_status": "OK",
    "duration_text": "1시간 40분",
    "theme": "점심",
    "places": [
        {
            "seq": 1, "role": "meal", "name": "샘플덮밥 세마점", "short_name": "샘플덮밥",
            "visited_at": "2026-11-16T11:40", "map_source": "naver",
            "naver_place_name": "샘플덮밥 세마점",
            "addr_road": "경기도 오산시 샘플로 12", "lat": 37.1889, "lng": 127.0419,
            "search_result_addr": "경기도 오산시 샘플로 12 1층",
            "hours": {"월": "11:00~20:00"}, "hours_source": "네이버 플레이스",
            "parking": {"type": "무료", "fee": "3대"},
            "price_items": [{"label": "샘플덮밥", "amount": 4500, "basis_date": "2026-11-16"}],
            "verified_at": "2026-11-16", "evidence": ["02.jpg"],
            "ordered_items": ["샘플덮밥"],
            "reviews": {"source": "naver", "count": 128, "recent_months": 1,
                        "keywords": ["양이 많다"], "menus": [{"name": "샘플덮밥", "mentions": 41},
                                                              {"name": "샘플튀김", "mentions": 7}]},
            "shorts": {"url": "https://www.youtube.com/shorts/dQw4w9WgXcQ",
                       "title": "샘플덮밥 다녀온 30초", "place": "샘플덮밥 세마점"},
            "story": ["11시 40분에 들어가니 앞 테이블 두 곳만 차 있었어요. 샘플덮밥은 4,500원이었습니다. 영수증에는 2인 10,000원으로 찍혔습니다.",
                      "밥 양이 많아서 곱빼기는 필요 없었어요. 간은 세지 않았습니다."],
            "one_liner": "4,500원에 이 양이면 점심으로는 기본이 낫습니다.",
        },
        {
            "seq": 2, "role": "cafe", "name": "샘플카페 세마점", "short_name": "샘플카페",
            "visited_at": "2026-11-16T12:50", "map_source": "naver",
            "naver_place_name": "샘플카페 세마점",
            "addr_road": "경기도 오산시 샘플로 24", "lat": 37.1895, "lng": 127.0431,
            "search_result_addr": "경기도 오산시 샘플로 24",
            "hours": {"월": "09:00~18:00"}, "hours_source": "네이버 플레이스",
            "parking": {"type": "무료", "fee": "2대"},
            "price_items": [{"label": "아메리카노", "amount": 3000, "basis_date": "2026-11-16"}],
            "verified_at": "2026-11-16", "evidence": ["04.jpg"],
            "ordered_items": ["아메리카노"],
            "reviews": {"source": "naver", "count": 64, "recent_months": 2,
                        "keywords": ["조용하다"], "menus": [{"name": "아메리카노", "mentions": 18}]},
            "shorts": {"url": "https://www.youtube.com/shorts/aBcDeF12345",
                       "title": "샘플카페 창가 자리", "place": "샘플카페 세마점"},
            "story": ["덮밥집에서 걸어서 4분 거리였어요. 12시 50분에 갔는데 창가 자리가 비어 있었습니다. 주차는 건물 앞 2대뿐이라 12시가 넘으면 자리가 없을 수 있어요.",
                      "아메리카노 3,000원이었어요. 라테는 마시지 않아서 맛은 말하지 않겠습니다."],
            "one_liner": "커피 3,000원이면 점심 뒤 30분 쓰기에는 충분했어요.",
        },
    ],
    "moves": [{"from": 1, "to": 2, "km": 0.35, "min": 4, "method": "도보"}],
    "cost": {"items": [{"label": "샘플덮밥 2그릇", "amount": 10000, "basis_date": "2026-11-16"},
                       {"label": "아메리카노 2잔", "amount": 6000, "basis_date": "2026-11-16"}],
             "total": 16000, "currency": "KRW"},
    "checklist": ["주차 입구는 건물 뒤쪽입니다.", "브레이크타임 15:00~16:30은 피하세요.",
                  "카페는 18시에 닫습니다.", "카드 결제만 됩니다."],
    "internal_links": [{"target_log_no": "224459436953", "target_title": "오산 세교 추막골 남원추어탕 본점 방문 후기",
                        "role_from": "cafe", "role_to": "meal", "decision": "PASS", "reason": "역할 교차"}],
    "affiliates": [
        {"slot": "B", "provider": "naver_connect", "label": "오산 근처 카페 가격 비교하기",
         "url": "https://shopping.naver.com/connect/example-b"},
        {"slot": "E", "provider": "naver_connect", "label": "이 지역 식당 가격 확인하기",
         "url": "https://shopping.naver.com/connect/example-e"},
    ],
    "disclosure_confirmed": True,
    "faq": [{"q": "주차 되나요?", "a": "두 곳 다 무료이고 자리는 3대와 2대입니다."},
            {"q": "2인 얼마인가요?", "a": "덮밥 두 그릇과 커피 두 잔 해서 16,000원이었습니다."},
            {"q": "언제 가야 하나요?", "a": "평일 11시 40분에 갔고 기다리지 않았습니다."}],
    "closing": ["두 곳 다 세마역에서 걸어갈 거리였고 총 16,000원이면 점심 코스로 충분했어요.",
                "차로 오고 주차를 먼저 보는 분께 맞습니다. 대중교통만 쓰면 두 곳 사이는 걸어서 4분이에요."],
    "images": [{"file": "01_대표.jpg"},
               {"file": "02.jpg", "place": "샘플덮밥 세마점"},
               {"file": "03.jpg", "place": "샘플덮밥 세마점"},
               {"file": "04.jpg", "place": "샘플카페 세마점"}],
    "tags": ["오산맛집", "세교동", "세마역", "오산카페", "덮밥", "점심코스"],
}


def sample_course(**over):
    d = copy.deepcopy(BASE)
    d.update(over)
    return d
