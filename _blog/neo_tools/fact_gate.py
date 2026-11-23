"""S2 팩트·지도 핀 게이트 — 코스 하나를 발행 전에 검사한다 (F1~F15).

무엇을 하나
 - 장소마다 지도 소스가 규칙대로인가: 국내는 **네이버 지도**(장소명·도로명주소·좌표), 해외는 **구글 지도**(공식 장소명·주소·링크)
 - 영업시간·브레이크타임·휴무·주차·가격이 그 소스에서 확인된 값인가(확인일 필수)
 - 순서(동선) 근거가 있는가, 방문일이 있는가, 코스가 한 도시 안인가
 - 리뷰로 보강한 맛·분위기 표현이 **실제로 주문·촬영한 메뉴**의 것인가(허위 경험 금지)
 - 그 장소로 만든 유튜브 쇼츠가 본문에 들어갈 수 있는 형식인가(2026-11-23 확정)

BLOCK 이 하나라도 있으면 S3(본문 조립)로 넘어가지 않는다. REVIEW 는 해당 문장을 빼고 진행한다.

값을 만들지 않는다: course.json 에 없는 사실은 '없음'으로 보고하고, 본문 조립기는 그 문장을 쓰지 않는다.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 지도 핀·주소 판정은 발행기(uploader/place_pin.py)와 같은 함수를 쓴다 — 두 곳에 규칙을 적으면 갈라진다.
_UPLOADER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploader")
if _UPLOADER not in sys.path:
    sys.path.insert(0, _UPLOADER)
import place_pin  # noqa: E402

BLOCK, REVIEW, OK = "BLOCK", "REVIEW", "OK"
DOMESTIC_SIGUNGUS = ()          # 판정은 map_source 값으로 한다(주소 문자열 추측 금지)
MAX_HOURS_AGE_DAYS = 30         # 영업시간 확인일이 30일을 넘으면 다시 확인
MAX_KM_FROM_CENTER = 50
MAX_KM_BETWEEN = 60
MAX_GEOCODE_DRIFT_KM = 2.0
TASTE_WORDS = ("바삭", "쫄깃", "부드럽", "짜", "싱거", "맵", "달콤", "담백", "고소", "촉촉",
               "퍽퍽", "얼큰", "칼칼", "느끼", "깔끔", "두툼", "도톰", "쫀득", "바삭바삭")
REVIEW_SOURCE_WORDS = ("방문자 리뷰", "리뷰에서", "리뷰에", "구글 리뷰", "네이버 리뷰", "후기에서")


def item(code: str, name: str, state: str, detail: str = "", where: Optional[List] = None) -> dict:
    return {"코드": code, "항목": name, "판정": state, "내용": detail, "위치": where or []}


def _today(today: Optional[date] = None) -> date:
    return today or datetime.now().date()


def _parse_date(s: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lng1 = a
    lat2, lng2 = b
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _place_label(p: dict) -> str:
    return f"{p.get('seq', '?')}. {p.get('name', '(이름 없음)')}"


# ── 장소 단위 검사 ──────────────────────────────────────
def check_place(p: dict, today: Optional[date] = None) -> List[dict]:
    out: List[dict] = []
    label = _place_label(p)
    src = str(p.get("map_source", "")).strip().lower()
    domestic = src == "naver"
    overseas = src == "google"

    # F1 주소
    addr = (p.get("addr_road") if domestic else p.get("google_addr")) or p.get("addr_road") or ""
    if not str(addr).strip():
        out.append(item("F1", f"{label} 주소", BLOCK, "주소가 없어요(국내 도로명 / 해외 구글 공식 주소)"))

    # F10 국내 지도
    if src and not domestic and not overseas:
        out.append(item("F10", f"{label} 지도 소스", BLOCK, f"map_source='{src}' — 국내 'naver' / 해외 'google'"))
    if domestic:
        miss = [k for k in ("naver_place_name", "addr_road") if not str(p.get(k, "")).strip()]
        if not (p.get("lat") and p.get("lng")):
            miss.append("lat/lng")
        if miss:
            out.append(item("F10", f"{label} 네이버 지도 값", BLOCK, "빠진 값: " + ", ".join(miss)))
        tokens = place_pin.addr_tokens(str(addr))
        if addr and not tokens:
            out.append(item("F5", f"{label} 주소 토큰", BLOCK, f"주소에서 시/군/구·도로명을 못 읽음: {str(addr)[:30]}"))
        seam = str(p.get("search_result_addr", "")).strip()
        if seam and tokens:
            got = place_pin.score(seam, tokens)
            if got < len(tokens):
                out.append(item("F5", f"{label} 장소명↔주소 대조", BLOCK,
                                f"검색 결과 주소 불일치({got}/{len(tokens)}): {seam[:40]} — 핀 삽입 금지"))
    # F11 해외 지도
    if overseas:
        miss = [k for k in ("google_place_name", "google_addr", "google_maps_url") if not str(p.get(k, "")).strip()]
        if miss:
            out.append(item("F11", f"{label} 구글 지도 값", BLOCK, "빠진 값: " + ", ".join(miss)))
        if p.get("google_maps_url") and not place_pin.is_google_maps(str(p["google_maps_url"])):
            out.append(item("F11", f"{label} 구글 지도 링크", BLOCK, "구글 지도 주소가 아님: " + str(p["google_maps_url"])[:50]))

    # F2 영업시간 · F12 출처/확인일
    verified = _parse_date(p.get("verified_at", ""))
    if not p.get("hours"):
        out.append(item("F2", f"{label} 영업시간", REVIEW, "영업시간 미확인 — 본문에서 시간 문장을 빼세요"))
    elif not verified:
        out.append(item("F12", f"{label} 영업시간 확인일", REVIEW, "확인일(verified_at)이 없어요"))
    elif (_today(today) - verified).days > MAX_HOURS_AGE_DAYS:
        out.append(item("F2", f"{label} 영업시간", REVIEW,
                        f"확인일이 {(_today(today) - verified).days}일 전 — 다시 확인하거나 시간 문장을 빼세요"))
    if p.get("hours") and not str(p.get("hours_source", "")).strip():
        out.append(item("F12", f"{label} 영업시간 출처", REVIEW, "출처(네이버 플레이스/구글 지도)가 없어요"))

    # F3 가격 기준일 · F4 주차
    for pr in p.get("price_items") or []:
        if not _parse_date(pr.get("basis_date", "")):
            out.append(item("F3", f"{label} 가격 기준일", BLOCK,
                            f"'{pr.get('label', '')}' 가격에 기준일이 없어요"))
            break
    if not p.get("parking"):
        out.append(item("F4", f"{label} 주차", REVIEW, "주차 정보 없음 — '주차' 항목을 빼세요"))

    # F6·F7 거리
    if domestic and p.get("lat") and p.get("lng"):
        if p.get("geocoded_lat") and p.get("geocoded_lng"):
            d = haversine_km((float(p["lat"]), float(p["lng"])), (float(p["geocoded_lat"]), float(p["geocoded_lng"])))
            if d > MAX_GEOCODE_DRIFT_KM:
                out.append(item("F7", f"{label} 좌표↔주소", BLOCK, f"지오코딩 거리 {d:.1f}km — 좌표를 다시 확인"))
        else:
            out.append(item("F7", f"{label} 좌표 검증", REVIEW, "좌표↔주소 지오코딩 대조를 하지 못했어요"))

    # F14 쇼츠 (2026-11-23 확정 — 그 장소로 만든 유튜브 쇼츠를 본문에 넣는다)
    shorts = p.get("shorts") or {}
    if not shorts:
        out.append(item("F14", f"{label} 유튜브 쇼츠", REVIEW, "이 장소로 만든 쇼츠가 없어요 — 본문 영상 줄을 빼고 촬영 뒤 추가"))
    else:
        url = str(shorts.get("url", ""))
        if not place_pin.is_youtube_shorts(url):
            out.append(item("F14", f"{label} 유튜브 쇼츠 링크", BLOCK, f"쇼츠 주소 형식이 아님: {url[:50]}"))
        if str(shorts.get("place", "")).strip() and p.get("name") and str(shorts["place"]).strip() not in str(p["name"]):
            out.append(item("F14", f"{label} 쇼츠 장소 연결", REVIEW,
                            f"쇼츠가 다른 장소('{shorts['place']}')로 만들어졌어요"))

    # F15 리뷰 신뢰 경계
    rv = p.get("reviews") or {}
    if rv:
        if str(rv.get("source", "")).lower() not in ("naver", "google", "네이버", "구글"):
            out.append(item("F15", f"{label} 리뷰 출처", REVIEW, "리뷰 출처(네이버 플레이스/구글 지도)가 없어요"))
        if int(rv.get("count") or 0) < 5:
            out.append(item("F15", f"{label} 리뷰 수", REVIEW, f"리뷰 {rv.get('count', 0)}건 — 키워드로 쓰지 마세요"))
        if int(rv.get("recent_months") or 0) > 12:
            out.append(item("F15", f"{label} 최근 리뷰", REVIEW, "최근 1년 리뷰가 없어요 — 키워드로 쓰지 마세요"))
    return out


# ── 글 전체 검사 ────────────────────────────────────────
def check(course: dict, today: Optional[date] = None) -> dict:
    items: List[dict] = []
    places = course.get("places") or []
    if not places:
        items.append(item("F0", "장소", BLOCK, "places 가 비어 있어요"))
    if not _parse_date(course.get("visit_date", "")):
        items.append(item("F8", "방문일", BLOCK, "visit_date 가 없어요(내돈내산 근거)"))
    if str(course.get("order_status", "")).upper() != "OK":
        items.append(item("F9", "방문 순서", REVIEW, "순서 근거 없음 — '먼저/다음' 대신 '이날 간 곳'으로 쓰세요"))

    for p in places:
        items += check_place(p, today)

    # F6 코스 범위
    coords = [(float(p["lat"]), float(p["lng"])) for p in places if p.get("lat") and p.get("lng")]
    if len(coords) >= 2:
        center = (sum(c[0] for c in coords) / len(coords), sum(c[1] for c in coords) / len(coords))
        for p, c in zip([p for p in places if p.get("lat") and p.get("lng")], coords):
            d = haversine_km(center, c)
            if d > MAX_KM_FROM_CENTER:
                items.append(item("F6", f"{_place_label(p)} 코스 범위", BLOCK, f"코스 중심에서 {d:.0f}km"))
        for (a, ca), (b, cb) in zip(zip(places, coords), zip(places[1:], coords[1:])):
            d = haversine_km(ca, cb)
            if d > MAX_KM_BETWEEN:
                items.append(item("F6", f"{_place_label(a)} → {_place_label(b)}", BLOCK, f"구간 이동 {d:.0f}km"))

    # 내부 링크: 역할이 겹치는 링크는 달지 않는다(R8)
    for lk in course.get("internal_links") or []:
        if lk.get("role_from") and lk.get("role_to") and lk["role_from"] == lk["role_to"]:
            items.append(item("F16", "내부 링크 역할", REVIEW,
                              f"{lk.get('role_from')}→{lk.get('role_to')} 같은 역할 링크: {lk.get('target_title', '')[:30]}"))
        if str(lk.get("decision", "")).upper() == "HOLD":
            items.append(item("F16", "내부 링크 보류", REVIEW, f"{lk.get('reason', '')} — 링크를 빼세요"))

    # 제휴: 쇼핑 커넥트 광고 위치(중간·마무리 직전)와 고지
    aff = course.get("affiliates") or []
    slots = [str(a.get("slot", "")).upper() for a in aff]
    if aff:
        if "B" not in slots and "C" not in slots:
            items.append(item("F17", "제휴 위치", REVIEW, "본문 중간(C) 슬롯이 없어요 — 중간·마무리 직전 두 곳"))
        if "E" not in slots:
            items.append(item("F17", "제휴 위치", REVIEW, "마무리 직전(E) 슬롯이 없어요"))
        for a in aff:
            if not str(a.get("url", "")).startswith("http"):
                items.append(item("F17", "제휴 링크", BLOCK, f"주소가 아님: {a.get('label', '')[:30]}"))
            if not str(a.get("provider", "")).strip():
                items.append(item("F17", "제휴 종류", REVIEW, "제휴처(쇼핑커넥트·예약처)가 비어 있어요"))
    if any(str(a.get("provider", "")).lower().startswith("naver") for a in aff) and not course.get("disclosure_confirmed"):
        items.append(item("F17", "쇼핑 커넥트 고지", REVIEW, "네이버 쇼핑 커넥트는 도입부 제휴 고지 문구가 필요해요"))

    block = [x for x in items if x["판정"] == BLOCK]
    review = [x for x in items if x["판정"] == REVIEW]
    return {"course_id": course.get("course_id", ""), "통과": not block,
            "BLOCK": len(block), "REVIEW": len(review),
            "항목": items, "블록": block, "검토": review}


# ── F13 리뷰 근거 없는 맛 단정(본문 검사) ────────────────
def _sentences(text: str) -> List[Tuple[int, str]]:
    out = []
    for i, l in enumerate(text.split("\n"), 1):
        s = l.strip()
        if not s or s.startswith(("【", "■", ">", "|", "▶")):
            continue
        for part in re.split(r"(?<=[.!?])\s+", s):
            if part.strip():
                out.append((i, part.strip()))
    return out


def find_unverified_claims(body: str, places: List[dict]) -> List[dict]:
    """리뷰 키워드만 보고 '내가 먹은 것처럼' 쓴 문장을 찾는다.

    조건: (1) 맛 표현이 있다 (2) 메뉴 이름이 있다 (3) 그 메뉴가 ordered_items 에 없다
          (4) 같은 문장에 리뷰 출처 표기가 없다  → BLOCK
    """
    bad = []
    for p in places or []:
        ordered = {str(x).strip() for x in (p.get("ordered_items") or [])}
        menus = []
        for m in (p.get("reviews") or {}).get("menus") or []:
            if isinstance(m, dict) and m.get("name"):
                menus.append(str(m["name"]))
        menus += [str(x.get("label", "")) for x in (p.get("price_items") or []) if x.get("label")]
        for line_no, sent in _sentences(body):
            if not any(w in sent for w in TASTE_WORDS):
                continue
            if any(w in sent for w in REVIEW_SOURCE_WORDS):
                continue
            hit = next((m for m in menus if m and m in sent), None)
            if hit and hit not in ordered:
                bad.append({"place": p.get("name", ""), "menu": hit, "line": line_no, "sentence": sent[:80]})
    return bad


def claim_items(body: str, course: dict) -> List[dict]:
    bad = find_unverified_claims(body, course.get("places") or [])
    if not bad:
        return [item("F13", "리뷰 근거 없는 맛 단정", OK, "")]
    return [item("F13", "리뷰 근거 없는 맛 단정", BLOCK,
                 f"'{b['menu']}'를 먹은 것처럼 썼는데 주문 목록에 없어요 — '방문자 리뷰에서 많이 언급되는'으로 바꾸세요",
                 [(b["line"], b["sentence"]) for b in bad[:3]]) for b in bad[:3]]


# ── CLI ────────────────────────────────────────────────
def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="코스 팩트 게이트(F1~F17)")
    ap.add_argument("course", help="course.json 경로")
    ap.add_argument("--out", default="", help="fact_report.json 쓸 경로(기본: course.json 옆)")
    ap.add_argument("--body", default="", help="완성본 본문 파일(있으면 F13도 검사)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    course = json.loads(Path(a.course).read_text(encoding="utf-8"))
    rep = check(course)
    if a.body:
        rep["항목"] += claim_items(Path(a.body).read_text(encoding="utf-8"), course)
        rep["F13"] = [x for x in rep["항목"] if x["코드"] == "F13"]
    out = Path(a.out) if a.out else Path(a.course).with_name("fact_report.json")
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print(f"팩트 게이트 {rep['course_id']} · BLOCK {rep['BLOCK']} · REVIEW {rep['REVIEW']} → {out}")
        for x in rep["항목"]:
            if x["판정"] != OK:
                print(f"  [{x['판정']}] {x['코드']} {x['항목']}: {x['내용']}")
    return 0 if rep["통과"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
