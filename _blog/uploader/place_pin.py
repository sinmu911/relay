"""지도 장소 핀 — 검색 결과가 '내가 간 곳'인지 주소로 대조한다 (B23 · F5 · §5-3).

왜 필요한가: 예전 `_insert_place()` 는 이름을 넣고 Enter 를 누른 뒤 **첫 번째 '추가' 버튼**을 눌렀다.
이름이 같은 다른 지역 장소가 먼저 나오면 엉뚱한 동네에 핀이 꽂힌다(화암사 글의 '바다정원' → 서울 동대문).
문구 규칙으로는 못 막는다. 값을 3종(장소명·도로명주소·좌표)으로 들고 다니고, 넣기 전에 주소를 읽어 대조해야 막힌다.

이 파일은 화면(Playwright)을 모르는 순수 판정만 담는다 — 시험이 브라우저 없이 돌 수 있게.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

GOOGLE_MAPS_RE = re.compile(r"(google\.[a-z.]+/maps|maps\.app\.goo\.gl|goo\.gl/maps|maps\.google\.com)")
YOUTUBE_SHORTS_RE = re.compile(r"^https?://(?:www\.|m\.)?(?:youtube\.com/shorts/[\w-]{6,}|youtu\.be/[\w-]{6,})")
ROAD_RE = re.compile(r"([가-힣A-Za-z0-9]+(?:로|길))(?:\s|$|\d)")
SIGUNGU_RE = re.compile(r"([가-힣]+(?:시|군|구))(?:\s|$)")


def norm(s: str) -> str:
    return re.sub(r"\s", "", (s or "").replace("\u00a0", " ")).lower()


def addr_tokens(road_addr: str) -> List[str]:
    """도로명주소에서 대조 토큰을 뽑는다 — '시/군/구' + 도로명(로·길). 모르면 빈 목록.

    '경기도 오산시 세교로 12' → ['오산시', '세교로']
    '경기도 광주시 고산별빛로 57' → ['광주시', '고산별빛로']
    """
    addr = (road_addr or "").strip()
    if not addr:
        return []
    out: List[str] = []
    for m in SIGUNGU_RE.finditer(addr):
        tok = m.group(1)
        if tok not in out:
            out.append(tok)
    rm = ROAD_RE.search(addr)
    if rm:
        out.append(rm.group(1))
    # 도로명이 없으면 마지막 동/읍/면이라도
    if not rm:
        dm = re.search(r"([가-힣]+(?:동|읍|면))(?:\s|$)", addr)
        if dm:
            out.append(dm.group(1))
    return out[:3]


def is_google_maps(url: str) -> bool:
    return bool(GOOGLE_MAPS_RE.search(url or ""))


def is_youtube_shorts(url: str) -> bool:
    return bool(YOUTUBE_SHORTS_RE.match(url or ""))


def score(candidate_addr: str, tokens: Sequence[str]) -> int:
    """주소 안에 들어 있는 토큰 수."""
    hay = norm(candidate_addr)
    return sum(1 for t in tokens if norm(t) and norm(t) in hay)


def choose(candidates: List[Dict[str, str]], tokens: Sequence[str], limit: int = 3) -> Dict:
    """검색 결과 후보 중 주소가 맞는 첫 후보를 고른다.

    candidates: [{"name": 화면에 보인 이름, "addr": 화면에 보인 주소}] — 위에서부터(검색 순위)
    돌려줌: {"index": int|None, "checked": n, "reason": str}
      - 토큰이 없으면(주소를 모른다) 고르지 않는다 → 부르는 쪽이 '핀 생략'으로 처리
      - 읽을 수 있는 주소가 하나도 없으면 고르지 않는다(첫 결과 클릭 금지)
      - 앞 limit 개까지 보고, 전부 불일치면 고르지 않는다
    """
    if not tokens:
        return {"index": None, "checked": 0, "reason": "주소 토큰이 없어 대조할 수 없음"}
    usable = [c for c in candidates[:limit] if str(c.get("addr", "")).strip()]
    if not usable:
        return {"index": None, "checked": 0, "reason": "검색 결과의 주소를 읽지 못함"}
    for i, c in enumerate(candidates[:limit]):
        if not str(c.get("addr", "")).strip():
            continue
        if score(c["addr"], tokens) >= len(tokens):
            return {"index": i, "checked": i + 1, "reason": "주소 일치: " + str(c["addr"])[:40]}
    best = max(candidates[:limit], key=lambda c: score(str(c.get("addr", "")), tokens), default=None)
    got = score(str((best or {}).get("addr", "")), tokens)
    return {"index": None, "checked": min(limit, len(candidates)),
            "reason": f"주소 불일치(가장 비슷한 후보 {got}/{len(tokens)} 토큰): " + str((best or {}).get("addr", ""))[:40]}


def pin_line_ok(line: str) -> Optional[str]:
    """`【장소】 이름 | 주소` 줄이 대조 가능한 모양인지. 문제가 있으면 이유를 돌려준다."""
    m = re.match(r"^\s*【장소】\s*(.+?)(?:\s*[|｜]\s*(.+?))?\s*$", line or "")
    if not m:
        return None
    if not (m.group(2) or "").strip():
        return "'【장소】 이름 | 도로명주소' 형식으로 주소를 함께 적어 주세요(이름만으로는 핀 오매핑을 막을 수 없음)"
    if not addr_tokens(m.group(2)):
        return f"주소에서 시/군/구·도로명을 못 읽었어요: {m.group(2)[:30]}"
    return None
