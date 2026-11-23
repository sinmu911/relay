"""S4 수익 슬롯 분기 — 글 종류에 따라 제휴 카드를 몇 개, 어디에 두는지 정한다.

2026-11-18 확정(융합 가이드 §6-4·§7): 카드 2~3개, 정보표 직후(B 30~40%) · 비교표 직후(C 55~60%) · 마무리 직전(E 88~92%).
2026-11-23 추가 확정: **네이버 쇼핑 커넥트 광고**를 본문 중간과 마무리 직전에 두고, 도입부에 제휴 고지를 고정한다.
  - 여행·예약 글: 예약 제휴 2~3개(B·C·E)
  - 맛집·카페·일상: 쇼핑 커넥트 2개(B·E) — 가격 비교 상품이 자연스러운 것만
  - IT·생활용품(레뷰): 쇼핑 커넥트 2개(B·E) + '제공받아' 표기
카드가 상품과 맞지 않으면 넣지 않는 편이 낫다(신뢰). 상한을 넘으면 예외 없이 잘라 낸다.
"""
from __future__ import annotations

import re
from typing import Dict, List

TYPES = ("travel", "local", "it")
SLOT_PCT = {"B": (30, 40), "C": (55, 60), "E": (88, 92)}
PLAN = {
    "travel": ["B", "C", "E"],
    "local": ["B", "E"],
    "it": ["B", "E"],
}
MAX_CARDS = 3
BANNED_CTA = ("지금 안 사면", "마감 임박", "서두르세요", "클릭해서 확인", "손해", "무조건", "최저가 보장")
ACTION_WORDS = ("확인", "보기", "예약", "구매", "담기", "비교", "검색", "둘러보기", "고르기")
DISCLOSURE = ("내돈내산", "수수료")


def detect_type(course: dict) -> str:
    t = str(course.get("type", "")).strip().lower()
    if t in TYPES:
        return t
    text = " ".join(str(p.get("name", "")) + str(p.get("role", "")) for p in course.get("places") or [])
    text += " " + " ".join(str(a.get("provider", "")) for a in course.get("affiliates") or [])
    if re.search(r"항공|숙소|호텔|티켓|이심|렌터카|투어|예약", text):
        return "travel"
    if re.search(r"레뷰|체험단|보조배터리|충전기|거치대|차량용품", text):
        return "it"
    return "local"


def ad_line(a: dict) -> str:
    return f"【제휴】 {str(a.get('label', '')).strip()} {str(a.get('url', '')).strip()}"


def plan(course: dict) -> dict:
    """코스 하나의 카드 배치를 정한다. 돌려줌: {type, slots[], cards[], disclosure[], issues[]}"""
    t = detect_type(course)
    slots = PLAN[t]
    aff = [dict(a) for a in course.get("affiliates") or []]
    issues: List[str] = []
    cards: List[dict] = []
    seen_urls = set()
    for s in slots:
        cand = next((a for a in aff if str(a.get("slot", "")).upper() == s and a.get("url")), None)
        if not cand:
            issues.append(f"{s} 슬롯({SLOT_PCT[s][0]}~{SLOT_PCT[s][1]}%)에 놓을 제휴 링크가 없어요")
            continue
        url = str(cand["url"]).strip()
        if url in seen_urls:
            issues.append(f"같은 링크를 두 번 쓰지 않아요: {url[:40]}")
            continue
        seen_urls.add(url)
        label = str(cand.get("label", "")).strip()
        if any(b in label for b in BANNED_CTA):
            issues.append(f"카드 문구가 압박형이에요: {label[:30]}")
        if label and not any(w in label for w in ACTION_WORDS):
            issues.append(f"카드 문구를 '독자가 할 일'로 쓰세요(예: 내 날짜의 가격 확인하기): {label[:30]}")
        cards.append({"slot": s, "label": label or "가격·조건 확인하기", "url": url,
                      "provider": str(cand.get("provider", "")).strip()})
    extra = [a for a in aff if str(a.get("slot", "")).upper() not in slots and a.get("url")]
    if extra:
        issues.append(f"쓰지 않는 제휴 {len(extra)}개는 넣지 않아요(상한 {len(slots)}개)")
    if len(cards) > MAX_CARDS:
        cards = cards[:MAX_CARDS]
        issues.append(f"카드 {MAX_CARDS}개 상한으로 잘랐어요")
    disclosure = []
    if cards:
        providers = {c["provider"] for c in cards if c["provider"]}
        name = "네이버 쇼핑 커넥트" if any("naver" in p.lower() for p in providers) else (sorted(providers)[0] if providers else "제휴")
        disclosure = [
            "내돈내산 · {방문일} 방문",
            f"이 글에는 {name} 제휴 링크가 있어요. 링크로 구매하시면 저에게 수수료가 적립돼요(가격은 같아요).",
        ]
    return {"type": t, "slots": slots, "cards": cards, "disclosure": disclosure, "issues": issues}


def check_cards(cards: List[dict]) -> List[str]:
    """배치 상한·중복·금지 문구만 다시 본다(본문 위치는 검문소 B17이 잰다)."""
    issues = []
    if len(cards) > MAX_CARDS:
        issues.append(f"카드 {len(cards)}개(최대 {MAX_CARDS})")
    urls = [c.get("url") for c in cards]
    if len(set(urls)) != len(urls):
        issues.append("같은 링크 반복")
    for c in cards:
        if any(b in str(c.get("label", "")) for b in BANNED_CTA):
            issues.append("압박형 문구: " + str(c.get("label", ""))[:30])
    return issues
