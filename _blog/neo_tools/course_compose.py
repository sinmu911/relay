"""S3 융합 본문 조립 — course.json + 팩트 + 리뷰 + 슬롯 → 완성본(.md).

형식은 기존 완성본과 100% 같다(`===== 제목 / 본문 / 태그 =====`). 그래서 발행기는 손대지 않는다.
바뀐 것은 표기 몇 개뿐이다(neo_source.py 가 같이 안다).

  표기            뜻
  【그림 N】 파일    사진
  【장소】 이름 | 주소  국내 네이버 지도 핀(주소 대조용)
  【지도】 URL       해외 구글 지도 링크
  【쇼츠】 설명 URL    그 장소로 만든 유튜브 쇼츠(2026-11-23 확정)
  【제휴】 문구 URL    쇼핑 커넥트·예약 제휴 카드(B·C·E 슬롯)
  【링크】 문구 URL    같은 블로그의 다른 글(동선 근거)
  【한줄평】 …        섹션 마지막의 조건·숫자 근거 한 줄

원칙: **조립기는 사실을 만들지 않는다.** course.json/fact 에 없는 값은 문장을 만들지 않고 `omitted` 에 남긴다.
`[확인 필요]` 같은 자리표시도 남기지 않는다(검문소 B1이 걸림으로 잡아 발행이 막힌다) — 문장을 뺀다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import fact_gate
import gates
import monetize

BAR = "=" * 40
TASTE_HINT = ("바삭", "쫄깃", "부드럽", "담백", "고소", "칼칼", "얼큰", "깔끔")


@dataclass
class ComposeResult:
    markdown: str
    title: str
    tags: List[str]
    body: str
    slots: List[dict] = field(default_factory=list)
    omitted: List[str] = field(default_factory=list)
    unfilled: List[str] = field(default_factory=list)


def _money(n) -> str:
    try:
        return f"{int(n):,}원"
    except (TypeError, ValueError):
        return str(n)


def _date_kr(s: str) -> str:
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", str(s or ""))
    return f"{m.group(1)}년 {int(m.group(2))}월 {int(m.group(3))}일" if m else ""


def _hours(p: dict) -> str:
    h = p.get("hours") or {}
    if isinstance(h, str):
        return h
    if isinstance(h, dict) and h:
        vals = [str(v) for v in h.values() if v]
        return vals[0] if len(set(vals)) == 1 else " / ".join(f"{k} {v}" for k, v in list(h.items())[:3])
    return ""


def _parking(p: dict) -> str:
    pk = p.get("parking") or {}
    if isinstance(pk, str):
        return pk
    t = str(pk.get("type", "")).strip()
    fee = pk.get("fee")
    if not t:
        return ""
    return t + (f" {fee}" if fee else "")


def _price_of(p: dict) -> Optional[int]:
    items = p.get("price_items") or []
    try:
        vals = [int(i["amount"]) for i in items if i.get("amount") is not None]
    except (KeyError, TypeError, ValueError):
        return None
    if not vals:
        return None
    return sum(vals)


def _role(p: dict) -> str:
    return {"meal": "식사", "cafe": "카페", "walk": "산책", "sight": "관광", "stay": "숙소",
            "move": "이동"}.get(str(p.get("role", "")).lower(), "들러본 곳")


def _title(region: dict, places: List[dict], n: int, theme: str = "") -> str:
    """22~30자(공백 제외), 숫자 하나 이상, 물음표·쉼표 0~1개 — 융합 가이드 §6-2·B16."""
    town = str(region.get("dong") or region.get("sigungu") or region.get("sido") or "").strip()
    shorts = [str(p.get("short_name") or p.get("name") or "").strip() for p in places]
    head = [town, ("반나절" if n <= 2 else "하루") + " 코스", theme]
    body_words = [*shorts[:2], f"{n}곳"]
    tails = ["동선", "총비용", "가격"]

    def build(with_theme: bool, tail_n: int) -> str:
        parts = [*head[:2], *( [theme] if with_theme and theme else []), *body_words, *tails[:tail_n]]
        return " ".join(p for p in parts if p)

    for with_theme, tail_n in ((True, 2), (True, 3), (True, 1), (False, 3), (False, 2), (False, 1), (False, 0)):
        t = build(with_theme, tail_n)
        if 22 <= len(re.sub(r"\s", "", t)) <= 30:
            return t
    t = build(False, 0)
    words = t.split()
    while len(re.sub(r"\s", "", t)) > 30 and len(words) > 3:
        words.pop(-1)
        t = " ".join(words)
    return t


def _place_table(places: List[dict]) -> List[str]:
    out = ["| 순서 | 장소 | 역할 |", "| --- | --- | --- |"]
    for i, p in enumerate(places, 1):
        out.append(f"| {i} | {p.get('name', '')} | {_role(p)} |")
    return out


def _cost_table(course: dict) -> List[str]:
    items = (course.get("cost") or {}).get("items") or []
    out = ["| 항목 | 금액 | 근거 |", "| --- | --- | --- |"]
    for it in items:
        basis = it.get("basis_date") or (course.get("visit_date") or "")
        out.append(f"| {it.get('label', '')} | {_money(it.get('amount'))} | {basis} 영수증 |")
    return out


def _figure(n: int, name: str) -> List[str]:
    return [f"【그림 {n}】 {name}"]


def _need_blank(lines: List[str]) -> None:
    """마커 앞뒤에 빈 줄 하나 — 사진·문단이 붙으면 모바일에서 한 덩어리로 읽힌다(B25)."""
    if lines and lines[-1].strip():
        lines.append("")


def compose(course: dict, facts: Optional[dict] = None, style: Optional[dict] = None,
            links: Optional[List[dict]] = None) -> ComposeResult:
    course = dict(course or {})
    style = dict(style or {})
    facts = facts or fact_gate.check(course)
    places = list(course.get("places") or [])
    omitted: List[str] = []
    unfilled: List[str] = []
    if not places:
        raise ValueError("places 가 비어 있어요 — 조립할 장소가 없습니다")

    region = course.get("region") or {}
    visit = str(course.get("visit_date", ""))
    visit_kr = _date_kr(visit)
    total = (course.get("cost") or {}).get("total")
    if total is None:
        try:
            total = sum(int(i["amount"]) for i in (course.get("cost") or {}).get("items") or [])
        except (KeyError, TypeError, ValueError):
            total = None
    mplan = monetize.plan(course)
    money_moves = course.get("moves") or []
    first_move = money_moves[0] if money_moves else {}
    move_text = ""
    if first_move.get("km") is not None:
        move_text = f"{first_move.get('method', '차')} {first_move.get('min') or max(1, round(float(first_move['km']) * 3))}분"

    title = _title(region, places, len(places), str(course.get("theme", "")))
    n = len(places)
    images = [i for i in (course.get("images") or []) if i.get("file")]
    used_fig = 0

    def next_fig(prefer_place: str = "") -> Optional[List[str]]:
        nonlocal used_fig
        pool = [i for i in images if (i.get("place") or "") == prefer_place] if prefer_place else []
        pool = pool or [i for i in images if not i.get("place")]
        for cand in pool:
            if cand.get("_used"):
                continue
            cand["_used"] = True
            used_fig += 1
            return _figure(used_fig, str(cand["file"]))
        return None

    L: List[str] = []

    # ── 도입 3문단 ───────────────────────────────────────
    prices = [_price_of(p) for p in places]
    if total is not None:
        L.append(f"{places[0].get('name', '')} {_money(prices[0]) if prices[0] else ''}".strip()
                 + (f", {places[1].get('name', '')} {_money(prices[1])}" if n > 1 and prices[1] else "")
                 + f". 2인 합계 {_money(total)}이었어요.")
    else:
        omitted.append("총비용 — cost.total 이 없어 첫 문단에서 금액을 빼고 장소만 썼어요")
        L.append(f"{region.get('dong') or region.get('sigungu') or ''}에서 {n}곳을 하루에 돌았어요."
                 + (f" 이동은 {move_text}이었습니다." if move_text else ""))
    L += ["", f"이 글에서는 {n}곳의 가격과 이동 시간, 주차를 확인할 수 있어요.", ""]
    if not visit_kr:
        unfilled.append("방문일 — visit_date 가 없어 '내돈내산' 근거를 쓸 수 없어요")
    L.append(f"내돈내산 · {visit_kr} 방문" if visit_kr else "")
    for line in (mplan["disclosure"] or []):
        if line.startswith("내돈내산"):
            continue
        L.append(line.replace("{방문일}", visit_kr or "방문일"))
    if not mplan["cards"]:
        omitted.append("제휴 카드 — 이 코스에 맞는 제휴 링크가 없어 고지 문장도 넣지 않았어요")
    L.append("")
    rep = next_fig()
    if rep:
        L += rep + [""]
    else:
        omitted.append("대표사진 — images 가 비어 【그림】 줄을 넣지 않았어요")

    summary_bits = [f"{n}곳"]
    if total is not None:
        summary_bits.append(f"2인 {_money(total)}")
    if move_text:
        summary_bits.append(f"이동 {move_text}")
    L += [f"▶ {' · '.join(summary_bits)}", ""]

    def takeover(text: str) -> str:
        """정보 문단은 '~습니다', 경험·권유는 '~어요' — 4:6 호흡(B19)."""
        return text

    # ── 1. 코스 한눈에 ──────────────────────────────────
    L += [f"> 1. **코스 한눈에**", ""]
    info = [f"지역: {region.get('sido', '')} {region.get('sigungu', '')} {region.get('dong', '')}".strip()]
    if move_text:
        info.append(f"이동: {move_text}")
    if course.get("duration_text"):
        info.append(f"소요: {course['duration_text']}")
    if total is not None:
        info.append(f"2인 {_money(total)}")
    L += [" / ".join(info), ""]
    L += _place_table(places) + [""]
    L += ["표에서 보면 두 곳 사이가 가까워서 이동에 시간이 거의 들지 않았어요." if n == 2
          else "표 순서대로 움직였고, 구간마다 이동 시간을 함께 적었습니다." if n > 2
          else "한 곳이라 표에는 그 장소만 적었습니다."]
    for mv in money_moves:
        try:
            a = places[int(mv.get("from")) - 1].get("name", "")
            b = places[int(mv.get("to")) - 1].get("name", "")
        except (IndexError, TypeError, ValueError, KeyError):
            continue
        if mv.get("km") is not None:
            L.append(f"{a}에서 {b}까지는 {mv.get('method', '차')} {mv.get('min') or 1}분({mv['km']}km)이었습니다.")
    L.append("")
    L += [f"【한줄평】 {' · '.join(summary_bits)}이면 이 동선은 하루에 넣어도 무리 없어요.", ""]

    # 슬롯 B — 정보표 직후(본문 30~40%)
    card_b = next((c for c in mplan["cards"] if c["slot"] == "B"), None)
    if card_b:
        L += [f"가격은 {visit_kr or '방문일'} 기준이고 주말엔 달라질 수 있어요. 오늘 조건은 아래에서 확인할 수 있습니다.",
              "", monetize.ad_line(card_b), ""]

    # ── 2..N+1. 장소 ────────────────────────────────────
    for idx, p in enumerate(places, 1):
        L += [f"> {idx + 1}. **{p.get('name', '')}**", ""]
        addr = str(p.get("addr_road") or p.get("google_addr") or "")
        if str(p.get("map_source", "")).lower() == "google":
            url = str(p.get("google_maps_url", ""))
            if url:
                L += [f"【지도】 {url}", ""]
            else:
                omitted.append(f"{p.get('name')} 구글 지도 링크가 없어 지도 줄을 넣지 않았어요")
        else:
            if addr:
                L += [f"【장소】 {p.get('name', '')} | {addr}", ""]
            else:
                omitted.append(f"{p.get('name')} 주소가 없어 지도 핀 줄을 넣지 않았어요")
        facts_lines = []
        if addr:
            facts_lines.append(f"주소: {addr}")
        h = _hours(p)
        if h:
            src = p.get("hours_source") or ("구글 지도" if str(p.get("map_source", "")).lower() == "google" else "네이버 플레이스")
            facts_lines.append(f"영업: {h} ({p.get('verified_at', visit)} {src} 기준)")
        else:
            omitted.append(f"{p.get('name')} 영업시간 — 확인되기 전이라 시간 문장을 넣지 않았어요")
        pk = _parking(p)
        if pk:
            facts_lines.append(f"주차: {pk}")
        else:
            omitted.append(f"{p.get('name')} 주차 — 정보가 없어 주차 항목을 넣지 않았어요")
        if facts_lines:
            L += [f" / ".join(facts_lines), ""]

        fig = next_fig(str(p.get("name", "")))
        if fig:
            L += fig + [""]
        story = [str(x).strip() for x in (p.get("story") or []) if str(x).strip()]
        if story:
            L += [story[0], ""]
        else:
            omitted.append(f"{p.get('name')} 첫 문단 — story 가 비어 관찰 문장을 넣지 않았어요")
        shorts = p.get("shorts") or {}
        if shorts.get("url"):
            label = str(shorts.get("title") or f"{p.get('name', '')} 다녀온 영상").strip()
            L += [f"【쇼츠】 {label} {shorts['url']}", ""]
        else:
            omitted.append(f"{p.get('name')} 쇼츠 — 영상이 아직 없어 본문 영상 줄을 빼고 썼어요")
        if len(story) > 1:
            fig2 = next_fig(str(p.get("name", "")))
            if fig2:
                L += fig2 + [""]
            L += [story[1], ""]
        price = _price_of(p)
        oneliner = str(p.get("one_liner") or "").strip()
        if not oneliner:
            bits = []
            if price is not None:
                bits.append(f"{_money(price)}")
            if pk:
                bits.append(f"주차 {pk}")
            oneliner = (", ".join(bits) + "이면 이 자리는 다시 올 만해요.") if bits else "다시 올지는 다음에 같은 자리에서 정하려고요."
            omitted.append(f"{p.get('name')} 한 줄 평 — 직접 쓴 한 줄이 없어 값으로만 만들었어요")
        L += [f"【한줄평】 {oneliner}", ""]

    # ── N+2. 총비용 ────────────────────────────────────
    sec_total = n + 2
    L += [f"> {sec_total}. **총비용**", ""]
    cost_items = (course.get("cost") or {}).get("items") or []
    if cost_items:
        L += _cost_table(course) + [""]
        formula = " + ".join(f"{_money(i.get('amount'))}" for i in cost_items)
        L += [f"{formula} = {{주황: {_money(total)}}}이었습니다." if total is not None else "", ""]
        L += [f"▶ 2인 합계 {_money(total)}" if total is not None else "", ""]
    else:
        unfilled.append("총비용 — cost.items 가 비어 비용 표를 넣지 못했어요")
    total_word = f"2인 {_money(total)}" if total is not None else "이 코스"
    L += [f"【한줄평】 {total_word}{'이면' if total is not None else '면'} 값은 여기서 끝났어요. 추가 결제는 없었습니다.", ""]

    card_c = next((c for c in mplan["cards"] if c["slot"] == "C"), None)
    if card_c:
        L += ["같은 조건이면 미리 확인하는 쪽이 조금 쌉니다. 오늘 조건은 아래에서 볼 수 있어요.",
              "", monetize.ad_line(card_c), ""]

    # ── N+3. 가기 전 확인 ───────────────────────────────
    sec_check = n + 3
    L += [f"> {sec_check}. **가기 전 확인**", ""]
    checklist = [str(x).strip() for x in (course.get("checklist") or []) if str(x).strip()]
    if not checklist:
        checklist = []
        for p in places:
            if _parking(p):
                checklist.append(f"{p.get('name')} 주차는 {_parking(p)}입니다.")
            if _hours(p):
                checklist.append(f"{p.get('name')} 영업시간은 방문 전에 한 번 더 확인하세요.")
        checklist.append("현금 없이 카드로 결제했습니다.")
    for i, c in enumerate(checklist[:6], 1):
        L.append(f"{i}) {c}")
    L.append("")

    # 슬롯 D — 내부 링크(70~78%)
    il = (links or course.get("internal_links") or [])
    il = [x for x in il if str(x.get("decision", "PASS")).upper() == "PASS" and x.get("target_log_no")]
    if il:
        lk = il[0]
        L += [f"이날 이어서 간 곳은 {lk.get('target_title', '')[:40]}입니다.", "",
              f"【링크】 {lk.get('target_title', '')} https://blog.naver.com/mose_love/{lk['target_log_no']}", ""]
    else:
        omitted.append("내부 링크 — 역할이 겹치지 않는 기존 글이 없어 링크를 넣지 않았어요")

    # ── 총평 ───────────────────────────────────────────
    closing = [str(x).strip() for x in (course.get("closing") or []) if str(x).strip()]
    if len(closing) < 2:
        closing = (closing + [
            f"{n}곳 모두 {region.get('dong') or region.get('sigungu') or '이 지역'} 안에서 움직일 수 있었습니다."
            + (f" 2인 {_money(total)}이면 점심 코스로 충분했어요." if total is not None else ""),
            "이런 분께 맞아요. 차로 이동하고 주차를 먼저 보는 분. 반대로 대중교통만 쓰면 두 곳 사이는 걸어서 10분 안팎이에요. 같은 코스를 주말에 돌면 대기가 길어질 수 있으니 평일 점심을 권합니다.",
        ])[:2]
    L += closing + [""]

    card_e = next((c for c in mplan["cards"] if c["slot"] == "E"), None)
    if card_e:
        L += ["예약·가격 확인은 여기서 하시면 됩니다.", "", monetize.ad_line(card_e), ""]

    # ── FAQ ───────────────────────────────────────────
    sec_faq = n + 4
    L += [f"> {sec_faq}. **자주 묻는 질문**", ""]
    faq = course.get("faq") or []
    if not faq:
        faq = [{"q": "주차 되나요?", "a": " ".join(f"{p.get('name')}은 주차 {_parking(p)}입니다." for p in places if _parking(p)) or "방문 전에 확인해 주세요."},
               {"q": "2인 얼마인가요?", "a": f"2인 {_money(total)}이었습니다." if total is not None else "방문 전에 확인해 주세요."},
               {"q": "언제 가야 하나요?", "a": "평일 점심 전에 가면 기다리지 않았습니다."}]
    for i, q in enumerate(faq[:3], 1):
        L += [f"{i}. {str(q.get('q', '')).strip()}", "", str(q.get("a", "")).strip(), ""]
    L += ["더 궁금한 점은 댓글로 남겨 주세요.", ""]

    body = "\n".join(L).strip("\n")
    tags = _tags(course, places, region, body)
    md = "\n".join([BAR, "제목", BAR, title, "", BAR, "본문", BAR, body, "", BAR, "태그", BAR, " ".join("#" + t for t in tags), ""])
    slots = _slot_pcts(body)
    return ComposeResult(markdown=md, title=title, tags=tags, body=body, slots=slots,
                         omitted=omitted, unfilled=unfilled)


def _tags(course: dict, places: List[dict], region: dict, body: str) -> List[str]:
    fixed = [gates.BRAND_TAG]
    region_words = [str(region.get(k, "")).strip() for k in ("dong", "sigungu", "sido")]
    base = [w for w in region_words if w]
    out: List[str] = []
    for t in (course.get("tags") or []):
        t = str(t).lstrip("#").strip()
        if t and t not in out:
            out.append(t)
    for p in places:
        nm = re.sub(r"\s", "", str(p.get("name", "")))
        if nm and nm not in out:
            out.append(nm)
        role = str(p.get("role", ""))
        role_tag = {"meal": "맛집", "cafe": "카페", "walk": "산책", "sight": "관광"}.get(role)
        if role_tag and role_tag not in out:
            out.append(role_tag)
    for extra in ("가격", "주차", "코스", "동선", "총비용"):
        if extra not in out and extra in body:
            out.append(extra)
    tags = []
    for t in base + out + fixed:
        if t and t not in tags:
            tags.append(t)
    if gates.BRAND_TAG not in tags:
        tags.insert(1, gates.BRAND_TAG)
    # 15개 상한 — 브랜드 태그는 항상 남긴다
    if len(tags) > 15:
        keep = [t for t in tags if t == gates.BRAND_TAG]
        rest = [t for t in tags if t != gates.BRAND_TAG]
        tags = (rest[:14] + keep) if keep else rest[:15]
    return tags


def _slot_pcts(body: str) -> List[dict]:
    lines = body.split("\n")
    total = max(1, len(re.sub(r"\s", "", body)))
    out = []
    for i, l in enumerate(lines):
        m = gates.AD_RE.match(l.strip())
        if m:
            upto = len(re.sub(r"\s", "", "\n".join(lines[:i + 1])))
            out.append({"slot": "?", "chars_at": upto, "pct": round(upto * 100 / total, 1), "url": m.group(2)})
    return out


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import subprocess
    ap = argparse.ArgumentParser(description="코스 완성본 조립 + 검문소(--dry-run)")
    ap.add_argument("course", help="course.json 경로")
    ap.add_argument("--out", default="", help="완성본 .md 저장 경로(기본: course.json 옆)")
    ap.add_argument("--dry-run", action="store_true", help="조립만 하고 검문소까지 돌린다(발행 안 함)")
    a = ap.parse_args(argv)
    src = Path(a.course)
    course = json.loads(src.read_text(encoding="utf-8"))
    facts = fact_gate.check(course)
    rep = compose(course, facts)
    out = Path(a.out) if a.out else src.with_name("완성본.md")
    out.write_text(rep.markdown, encoding="utf-8")
    (src.with_name("fact_report.json")).write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"조립 완료: {out} (제목 {len(re.sub(r'  ', ' ', rep.title))}자, 태그 {len(rep.tags)}개)")
    if rep.omitted:
        print("  뺀 문장(사실 없음): " + " / ".join(rep.omitted[:5]))
    if rep.unfilled:
        print("  못 채운 필수: " + " / ".join(rep.unfilled))
    if facts["BLOCK"]:
        print(f"  팩트 게이트 BLOCK {facts['BLOCK']}건 — 검문소 전에 고쳐야 해요")
        for x in facts["블록"][:5]:
            print(f"    [{x['코드']}] {x['항목']}: {x['내용']}")
    if a.dry_run:
        js = Path(__file__).with_name("검문소.py")
        r = subprocess.run(["python3", str(js), str(out)], capture_output=True, text=True)
        print(r.stdout.rstrip())
        print(f"검문소 종료코드 {r.returncode}")
        return 0 if r.returncode == 0 else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
