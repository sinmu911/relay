"""S1 코스 클러스터링 — 장소 후보를 '하루 코스'로 묶는다 (R1~R8).

2026-11-23 서준님 확정 규칙: **식당 → 근처 카페 또는 여행지·공원** 동선을 먼저 확인하고 추천 코스로 묶는다.
그래서 이 모듈은 두 가지를 한다.
 1) 후보를 코스로 묶는다(R1~R8): 같은 날·가까운 거리·역할 중복 없음·3~5곳·순서 근거.
 2) 묶은 코스의 **동선**을 점검한다: 식사 뒤에 카페/산책/관광이 이어지는가, 그 거리가 걸어갈 만한가.

규칙을 못 지킨 후보는 버리지 않고 '왜 못 묶었는지'를 남긴다 — 판단은 사람이 한다.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional, Sequence, Tuple

from fact_gate import haversine_km

ROLES = ("meal", "cafe", "walk", "sight", "stay", "move")
ROLE_KR = {"meal": "식사", "cafe": "카페", "walk": "산책·공원", "sight": "관광", "stay": "숙소", "move": "이동"}
MAX_CITY_KM = 5.0            # R2 도심 반경
MAX_SUBURB_KM = 30.0         # R2 근교 반경
MAX_SEQ_KM = 60.0            # R7 무관 지역 차단
WALK_KM = 1.2                # '근처'라 부를 거리(도보 15분 안팎)
DATE_WINDOW_DAYS = 3         # R1 같은 방문일 ±3일


def _d(s: str) -> Optional[date]:
    for fmt in ("%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _coord(p: dict) -> Optional[Tuple[float, float]]:
    try:
        if p.get("lat") and p.get("lng"):
            return float(p["lat"]), float(p["lng"])
    except (TypeError, ValueError):
        return None
    return None


def _km(a: dict, b: dict) -> Optional[float]:
    ca, cb = _coord(a), _coord(b)
    if not ca or not cb:
        return None
    return haversine_km(ca, cb)


def r3_role_conflicts(places: Sequence[dict]) -> List[Tuple[str, str, str]]:
    """같은 역할이 두 번 이상 — (role, 남길 곳, 버릴 곳)."""
    seen: Dict[str, str] = {}
    out = []
    for p in places:
        role = str(p.get("role", "")).strip().lower()
        if role not in ROLES:
            continue
        if role in seen:
            out.append((role, seen[role], str(p.get("name", ""))))
        else:
            seen[role] = str(p.get("name", ""))
    return out


def cluster(candidates: Sequence[dict], visit_date: str = "") -> dict:
    """후보를 코스로 묶는다. 돌려줌: {places, moves, status, notes, order_status}"""
    notes: List[str] = []
    kept: List[dict] = []
    dropped: List[dict] = []
    base_date = _d(visit_date) if visit_date else None

    for p in candidates:
        pd = _d(p.get("visit_date", "")) if p.get("visit_date") else base_date
        if base_date and pd and abs((pd - base_date).days) > DATE_WINDOW_DAYS:
            dropped.append({"name": p.get("name", ""), "why": f"R1 방문일 차이 {abs((pd - base_date).days)}일"})
            continue
        kept.append(dict(p))

    # R7 무관 지역 먼저 — 다른 동네면 역할이 겹치든 말든 코스가 아니다(무주↔고성 사례).
    in_town: List[dict] = []
    for p in kept:
        if in_town:
            d = _km(in_town[0], p)
            if d is not None and d > MAX_SEQ_KM:
                dropped.append({"name": p.get("name", ""), "why": f"R7 첫 장소에서 {d:.0f}km — 한 코스로 묶지 않음"})
                continue
        in_town.append(p)

    # R3 역할 중복 — 뒤에 온 곳을 버린다(먼저 간 곳을 남긴다)
    kept = in_town
    for role, keep, drop in r3_role_conflicts(kept):
        kept = [p for p in kept if not (str(p.get("name", "")) == drop and str(p.get("role", "")).lower() == role)]
        dropped.append({"name": drop, "why": f"R3 역할 중복({ROLE_KR.get(role, role)}) — '{keep}' 유지"})
    final: List[dict] = kept

    # R4 3~5곳, 2곳이면 반나절, 1곳이면 단일 후기
    if len(final) >= 3:
        status = "course"
    elif len(final) == 2:
        status = "half_day"
        notes.append("2곳이라 '반나절'로 묶었어요(3곳 이상이면 코스형)")
    else:
        status = "single"
        notes.append("1곳이라 단일 후기로 돌려보냅니다")

    # R5 순서 — 근거(촬영·영수증 시각)가 있을 때만 정한다
    times = [str(p.get("visited_at", "")).strip() for p in final]
    if all(times) and len(times) > 1:
        final.sort(key=lambda p: str(p.get("visited_at")))
        order_status = "OK"
    else:
        order_status = "UNKNOWN"
        if final:
            notes.append("방문 순서 근거(촬영·영수증 시각)가 없어 '먼저/다음' 대신 '이날 간 곳'으로 씁니다")

    for i, p in enumerate(final, 1):
        p["seq"] = i
    moves = []
    for a, b in zip(final, final[1:]):
        km = _km(a, b)
        moves.append({"from": a.get("seq"), "to": b.get("seq"),
                      "km": round(km, 2) if km is not None else None,
                      "min": int(round(km * 15)) if km is not None else None,   # 차 4km/h… 도보 15분/km 기준
                      "method": "도보" if (km is not None and km <= WALK_KM) else "차"})
    return {"places": final, "moves": moves, "status": status, "order_status": order_status,
            "dropped": dropped, "notes": notes}


def route_check(places: Sequence[dict]) -> dict:
    """식당 뒤에 근처 카페·산책·관광이 이어지는가(2026-11-23 확정 규칙).

    돌려줌: {ok, next_stop, km, suggestion, issues[]}
      - 식사 다음에 카페/산책/관광이 없으면 suggestion 에 '근처 카페를 넣으세요'와 후보 거리를 적는다
      - 거리가 멀면(도보 1.2km 초과) '차로 몇 분'을 함께 적을 수 있게 km 를 돌려준다
    """
    issues: List[str] = []
    ordered = list(places)
    meal_idx = [i for i, p in enumerate(ordered) if str(p.get("role", "")).lower() == "meal"]
    if not meal_idx:
        issues.append("식사 장소가 없어 '식당 → 카페' 동선을 확인할 수 없어요")
        return {"ok": False, "next_stop": None, "km": None, "issues": issues}
    follow_roles = ("cafe", "walk", "sight")
    out = {"ok": True, "next_stop": None, "km": None, "issues": issues}
    for i in meal_idx:
        nxt = next((p for p in ordered[i + 1:] if str(p.get("role", "")).lower() in follow_roles), None)
        if not nxt:
            issues.append(f"'{ordered[i].get('name')}' 뒤에 카페·산책·관광이 없어요 — 근처 카페 한 곳을 붙이세요")
            out["ok"] = False
            continue
        km = _km(ordered[i], nxt)
        out["next_stop"] = nxt.get("name")
        out["km"] = round(km, 2) if km is not None else None
        if km is None:
            issues.append(f"'{ordered[i].get('name')}' → '{nxt.get('name')}' 거리를 몰라요(좌표 없음)")
        elif km > MAX_CITY_KM:
            issues.append(f"'{nxt.get('name')}'가 {km:.1f}km 떨어져 '근처'라고 쓰기 어려워요")
            out["ok"] = False
        elif km > WALK_KM:
            issues.append(f"'{nxt.get('name')}'까지 {km:.1f}km — '차로 {max(1, round(km * 3))}분'으로 쓰세요")
    return out


def link_candidates(places: Sequence[dict], published: Sequence[dict]) -> List[dict]:
    """R6·R8 내부 링크 후보 — 같은 역할은 달지 않는다(식사→카페/관광, 카페→식사/관광, 관광→식사)."""
    out = []
    for p in places:
        role = str(p.get("role", "")).lower()
        for pub in published:
            prole = str(pub.get("role", "")).lower()
            if not prole or prole == role:
                continue
            if role == "meal" and prole not in ("cafe", "sight", "walk"):
                continue
            if role == "cafe" and prole not in ("meal", "sight", "walk"):
                continue
            if role in ("sight", "walk") and prole not in ("meal", "cafe"):
                continue
            if not pub.get("log_no") or len(str(pub["log_no"])) < 9:
                continue
            out.append({"target_log_no": str(pub["log_no"]), "target_title": pub.get("title", ""),
                        "role_from": role, "role_to": prole, "decision": "PASS",
                        "reason": f"{ROLE_KR.get(role, role)}→{ROLE_KR.get(prole, prole)}"})
    return out
