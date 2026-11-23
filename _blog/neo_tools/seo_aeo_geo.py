"""SEO · AEO · GEO 지문 점검 — 검문소 B28.

세 가지를 한 번에 본다(2026-11-23 서준님 확정 규칙 "SEO·AEO·GEO 기준 최적화").
 SEARCH(SEO)  사람이 검색창에 넣는 말이 제목·첫 문단·소제목에 들어 있는지, 분량이 목표 안인지
 ANSWER(AEO)  질문에 먼저 답하는 구조인지 — 도입 첫 문장이 결론·숫자로 시작하고, FAQ 가 3문항이며
              답이 두 문장 안에 끝나는지
 LOCAL(GEO)   지역·장소 개체가 문서 전체에 일관되게 나오고, 확인 가능한 값(주소·영업·가격)에
              출처와 확인일이 붙었는지, 확인할 수 없는 최상급(최고·1위·가장 맛있는)이 없는지

점수 게이트가 아니라 '사람이 한 번 볼 것'(주의)이다. 걸림으로 올리지 않는 이유:
검색 유입과의 인과는 아직 측정하지 않았고(융합 가이드 §8), 문장을 기계적으로 고치면 오히려 글이 망가진다.
"""
from __future__ import annotations

import re
from typing import List

from gates import (FAQ_HEAD_RE, FAQ_Q_RE, PLACE_RE, SECTION_RE, VISIT_DATE_RE, _intro_lines, _lines,
                   _sections, item)

SUPERLATIVE = ("최고", "최상", "1위", "원탑", "가장 맛있는", "가장 저렴", "무조건", "100% 만족",
               "인생 맛집", "실패 없", "후회 없")
ANSWER_HINT = re.compile(r"\d|원|분|km|무료|유료|가능|불가|없|있")
DATE_RE = re.compile(r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일|\d{4}-\d{2}-\d{2}|\d{1,2}\s*월\s*\d{1,2}\s*일")
SOURCE_RE = re.compile("|".join(("네이버 플레이스", "네이버 지도", "구글 지도", "구글 리뷰", "방문자 리뷰")))
FACT_LINE_RE = re.compile(r"^(?:영업|주소|주차|가격|메뉴|요금|시간)\s*[:：]\s*(.+)$")


def _norm(s: str) -> str:
    return re.sub(r"[^가-힣A-Za-z0-9]", "", s)


def check(body: str, title: str) -> dict:
    issues: List[str] = []
    lines = _lines(body)
    intro = _intro_lines(body)
    secs = _sections(body)
    plain_title = _norm(title)
    body_norm = _norm(body)

    # ── SEO ──
    if not 1800 <= len(re.sub(r"\s", "", body)) <= 2400:
        issues.append(f"본문 {len(re.sub(chr(92) + 's', '', body))}자(목표 1,800~2,200자)")
    title_tokens = [t for t in re.split(r"[\s,·]+", title) if len(_norm(t)) >= 2][:6]
    if len([t for t in title_tokens if _norm(t) in body_norm]) < max(2, len(title_tokens) // 2):
        issues.append("제목 낱말이 본문에 거의 안 나옴(제목·본문 같은 말을 쓰세요)")
    first_para = next((l.strip() for l in intro if l.strip() and not l.strip().startswith(("【", "—", "▶", "="))), "")
    if first_para and not ANSWER_HINT.search(first_para):
        issues.append("도입 첫 문장에 결론(숫자·가능/불가)이 없음")
    heads = [s["title"] for s in secs] + [l.strip().lstrip("■").strip() for l in lines if l.strip().startswith("■ **")]
    if heads and not any(any(_norm(t) in _norm(h) for t in title_tokens[:3] if len(_norm(t)) >= 2) for h in heads):
        issues.append("소제목에 제목 핵심 낱말이 한 번도 안 들어감")

    # ── AEO ──
    faq_i = next((i for i, l in enumerate(lines) if FAQ_HEAD_RE.match(l.strip())), None)
    if faq_i is None:
        issues.append("자주 묻는 질문(FAQ) 소제목이 없음")
    else:
        qs, answers, j = 0, [], faq_i + 1
        while j < len(lines):
            s = lines[j].strip()
            if s.startswith(("■", ">", "#")) and j > faq_i:
                break
            if FAQ_Q_RE.match(s):
                qs += 1
                ans = []
                k = j + 1
                while k < len(lines) and not FAQ_Q_RE.match(lines[k].strip()) and not lines[k].strip().startswith(("■", ">")):
                    if lines[k].strip():
                        ans.append(lines[k].strip())
                    k += 1
                answers.append(" ".join(ans))
            j += 1
        if qs == 0:
            issues.append("FAQ 질문 줄이 없음")
        elif qs > 3:
            issues.append(f"FAQ {qs}문항(3문항 이하)")
        long_ans = [a for a in answers if len(re.split(r"(?<=[.!?])\s+", a)) > 2]
        if long_ans:
            issues.append(f"FAQ 답이 3문장 이상인 항목 {len(long_ans)}개(두 문장 안으로)")
        if answers and any(not a for a in answers):
            issues.append("FAQ 답이 비어 있는 항목이 있음")

    # ── GEO ──
    for i, l in enumerate(lines):
        s = l.strip()
        if any(w in s for w in SUPERLATIVE):
            issues.append(f"{i + 1}번째 줄: 확인할 수 없는 최상급 표현({next(w for w in SUPERLATIVE if w in s)})")
            break
    places = [m.group(1) for l in lines if (m := PLACE_RE.match(l.strip()))]
    for name in places:
        if _norm(name) not in body_norm.replace(_norm(name), "", 1):
            issues.append(f"장소명 '{name}'이 본문에 한 번만 나옴(소제목·본문에 같은 이름으로)")
            break
    fact_lines = [l.strip() for l in lines if FACT_LINE_RE.match(l.strip())]
    undated = [l[:30] for l in fact_lines if not (DATE_RE.search(l) or SOURCE_RE.search(l))]
    if undated and len(undated) == len(fact_lines):
        issues.append("영업·주차·가격 줄에 출처·확인일이 하나도 없음")
    visits = [l for l in intro if VISIT_DATE_RE.search(l)]
    if not visits:
        issues.append("방문일이 도입부에 없음(내돈내산 근거)")

    return item("B28", "SEO·AEO·GEO", "주의" if issues else "OK",
                " · ".join(issues[:5]) + (f" 외 {len(issues) - 5}개" if len(issues) > 5 else ""))
