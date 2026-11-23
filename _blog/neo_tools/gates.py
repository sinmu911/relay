"""코스형(융합 템플릿) 발행 게이트 — 검문소 B16~B28.

검문소.py 가 부르는 순수 함수 모음. 파일을 읽거나 쓰지 않고, 완성본 본문(문자열)만 본다.
자료 출처·사실 대조는 fact_gate.py(팩트 게이트 F1~F15), 본문 조립은 course_compose.py 몫이다.

2026-11-18 확정 스펙(융합 가이드 §10 · 코스 로직 §14)과 2026-11-23 서준님 추가 확정 규칙 반영:
 - 이모지·그림문자 0개(B20) · 태그 10~15 + #서준의여행한입(B3·B24) · AI 고지 강제 없음
 - 태그 구형 #달리는이기사 자동 주입 중단
 - 사진 → 빈 줄 → 본문 → 빈 줄 → 사진(B25) · 소제목 볼드(B26) · 본문 진그레이(B27)
 - 지도: 국내 네이버(주소 토큰 대조) / 해외 구글 지도 링크(B23)
 - 쇼핑 커넥트 광고는 본문 중간·마무리 직전(B17) + 제휴 고지(B18)
 - SEO·AEO·GEO(B28, seo_aeo_geo.py)
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

# ── 공통 표기 ─────────────────────────────────────────────
# 코스형 완성본이 쓰는 줄 표기(neo_source.py 와 같은 규칙). 늘리거나 바꾸면 양쪽을 같이 고친다.
SECTION_RE = re.compile(r"^>\s*(\d+)\.\s*(.+?)\s*$")                  # > 1. **코스 한눈에**
PLACE_RE = re.compile(r"^【장소】\s*(.+?)(?:\s*[|｜]\s*(.+?))?\s*$")      # 【장소】 이름 | 도로명주소
MAP_RE = re.compile(r"^【지도】\s*(\S+)\s*$")                            # 【지도】 https://maps.app.goo.gl/…
SHORTS_RE = re.compile(r"^【쇼츠】\s*(.*?)\s*(https?://\S+)\s*$")          # 【쇼츠】 다녀온 영상 https://youtube.com/shorts/…
FIGURE_RE = re.compile(r"^【그림\s*(\w+)】\s*(\S+)\s*$")
AD_RE = re.compile(r"^【제휴】\s*(.+?)\s+(https?://\S+)\s*$")             # 【제휴】 문구 URL
LINK_RE = re.compile(r"^【링크】\s*(.+?)\s+(https?://\S+)\s*$")           # 【링크】 문구 URL
ONELINER_RE = re.compile(r"^【한줄평】\s*(.+?)\s*$")
FAQ_HEAD_RE = re.compile(r"^(?:>|■)\s*(?:\d+\.\s*)?\**\s*자주\s*묻는\s*질문")
FAQ_Q_RE = re.compile(r"^\s*\d+\s*[.)]\s*.+\?\s*$")
HEADING_RE = re.compile(r"^(?:>\s*\d+\.|■)\s*(.+?)\s*$")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")

EMOJI_RE = re.compile("[" + chr(0x1F300) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF)
                      + chr(0x2B00) + "-" + chr(0x2BFF) + chr(0xFE0F) + chr(0x2049) + chr(0x203C) + "]")

POINT = {"파랑": "#0075c8", "청록": "#168F88", "주황": "#E58A35"}
POINT_TOKEN_RE = re.compile(r"\{(" + "|".join(POINT) + r"):\s*(.+?)\}")
ANY_COLOR_TOKEN_RE = re.compile(r"\{([가-힣A-Za-z#0-9]{1,10}):\s*.+?\}")
BAD_COLOR_TOKENS = ("검정", "블랙", "black", "빨강", "초록", "회색", "보라")

BANNED_WORDS = ("ㅎㅎ", "ㅋㅋ", "더라구요", "넘나", "뿜뿜", "찐", "?!", "완벽 가이드", "총정리",
                "꿀팁", "인생샷", "성지", "압도적", "낱낱이", "치트키")
EMPTY_PRAISE = ("좋았어요", "좋았습니다", "추천합니다", "추천해요", "만족스러워요", "훌륭합니다",
                "방문해 보시길", "꼭 가보세요", "최고였어요", "맛있었어요")

SOURCE_WORDS = ("네이버 플레이스", "네이버 지도", "구글 지도", "구글 리뷰", "방문자 리뷰")
DISCLOSURE_WORDS = ("내돈내산", "수수료")
VISIT_DATE_RE = re.compile(r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일|\d{4}-\d{2}-\d{2}")
AFFILIATE_PROVIDERS = ("naver.me", "brandconnect", "shopping.naver", "myrealt.rip", "3ha.in",
                       "skyscanner.pxf.io", "tamice.com", "link.naver", "naver.com/connect")


def item(code: str, name: str, state: str, detail: str = "", where: Optional[List] = None) -> dict:
    return {"코드": code, "항목": name, "판정": state, "내용": detail, "위치": where or []}


def is_course(body: str) -> bool:
    """>`1.` 번호 소제목이 하나라도 있으면 코스형 완성본으로 본다."""
    return any(SECTION_RE.match(l.strip()) for l in body.split("\n"))


def _lines(body: str) -> List[str]:
    return body.split("\n")


def _sections(body: str) -> List[dict]:
    """번호 소제목 단위 묶음: [{no, title, start, text, lines:[(줄번호, 글)]}]"""
    lines = _lines(body)
    out: List[dict] = []
    cur = None
    pre = []
    for i, l in enumerate(lines):
        m = SECTION_RE.match(l.strip())
        if m:
            if cur:
                out.append(cur)
            cur = {"no": int(m.group(1)), "title": m.group(2).strip(), "start": i, "lines": [], "pre": []}
        elif cur:
            cur["lines"].append((i, l))
        else:
            pre.append((i, l))
    if cur:
        out.append(cur)
    if out:
        out[0]["pre"] = pre
    return out


def _intro_lines(body: str) -> List[str]:
    """첫 번호 소제목 전 = 도입부(제목 재배열·저작권·대표사진·도입 3문단)."""
    lines = _lines(body)
    for i, l in enumerate(lines):
        if SECTION_RE.match(l.strip()):
            return lines[:i]
    return lines


def _pct(body: str, line_no: int) -> float:
    """본문(공백 제외) 누적 글자수 비율 — 슬롯 위치 계산."""
    lines = _lines(body)
    total = len(re.sub(r"\s", "", body)) or 1
    upto = len(re.sub(r"\s", "", "\n".join(lines[:line_no + 1])))
    return upto * 100 / total


def _paragraphs(lines: List[str]) -> List[str]:
    """빈 줄로 나눈 덩어리(사진·소제목 줄은 문단으로 세지 않음)."""
    out, buf = [], []
    for l in lines:
        s = l.strip()
        if not s:
            if buf:
                out.append("\n".join(buf)); buf = []
            continue
        if FIGURE_RE.match(s) or s.startswith(("【", "■", ">", "|", "▶", "—", "=")):
            if buf:
                out.append("\n".join(buf)); buf = []
            continue
        buf.append(s)
    if buf:
        out.append("\n".join(buf))
    return out


# ── B16 코스 구조 ────────────────────────────────────────
def b16_course_structure(body: str, title: str) -> dict:
    if not is_course(body):
        return item("B16", "코스 구조", "참고", "코스형(번호 소제목) 글이 아니면 해당 없음")
    problems = []
    secs = _sections(body)
    if not 5 <= len(secs) <= 7:
        problems.append(f"번호 소제목 {len(secs)}개(5~7개)")
    if not re.search(r"^> 1\.\s*\S*코스|^> 1\.\s*.*한눈", body, re.M) and not any(
            "한눈" in s["title"] for s in secs):
        problems.append("1번 소제목이 '코스 한눈에'가 아님")
    rows = [l for l in _lines(body) if TABLE_ROW_RE.match(l)]
    tables = 0
    prev_row = False
    for l in _lines(body):
        is_row = bool(TABLE_ROW_RE.match(l))
        if is_row and not prev_row:
            tables += 1
        prev_row = is_row
    if not 1 <= tables <= 2:
        problems.append(f"표 {tables}개(1~2개)")
    wide = [l[:30] for l in rows if l.count("|") - 1 > 3]
    if wide:
        problems.append(f"표 열이 4개 이상: {wide[0]}")
    plain = re.sub(r"\s", "", title)
    if not 22 <= len(plain) <= 30:
        problems.append(f"제목 {len(plain)}자(22~30자)")
    if not re.search(r"\d", title):
        problems.append("제목에 숫자 없음")
    if title.count("?") > 1 or title.count(",") > 1:
        problems.append("제목 물음표·쉼표가 2개 이상")
    intro = _paragraphs(_intro_lines(body))
    if not 3 <= len(intro) <= 4:
        problems.append(f"도입 문단 {len(intro)}개(3~4개)")
    return item("B16", "코스 구조", "걸림" if problems else "OK", " · ".join(problems))


# ── B17 슬롯 배치 ────────────────────────────────────────
def b17_slots(body: str) -> dict:
    lines = _lines(body)
    ads = [(i, m.group(1), m.group(2)) for i, l in enumerate(lines) if (m := AD_RE.match(l.strip()))]
    links = [(i, m.group(1), m.group(2)) for i, l in enumerate(lines) if (m := LINK_RE.match(l.strip()))]
    if not ads and not links:
        return item("B17", "슬롯 배치", "참고", "제휴 카드·내부 링크가 없는 글(해당 없음)")
    problems = []
    if len(ads) > 3:
        problems.append(f"제휴 카드 {len(ads)}개(최대 3)")
    urls = [u for _, _, u in ads]
    dup = sorted({u for u in urls if urls.count(u) > 1})
    if dup:
        problems.append("같은 링크 반복: " + ", ".join(dup[:2]))
    pcts = [round(_pct(body, i), 1) for i, _, _ in ads]
    if ads and min(pcts) < 10:
        problems.append(f"첫 10% 안에 제휴 카드({min(pcts)}%)")
    if ads and not any(25 <= p <= 45 for p in pcts):
        problems.append(f"본문 중간(25~45%)에 카드 없음 {pcts}")
    if ads and not any(80 <= p <= 95 for p in pcts):
        problems.append(f"마무리 직전(80~95%)에 카드 없음 {pcts}")
    for i, _, _ in ads:
        prev = next((l.strip() for l in reversed(lines[:i]) if l.strip()), "")
        if AD_RE.match(prev) or LINK_RE.match(prev):
            problems.append(f"{i + 1}번째 줄: 카드가 카드에 바로 붙음")
        elif len(prev) < 12:
            problems.append(f"{i + 1}번째 줄: 카드 앞 문맥 문장이 없음")
    if len(links) > 2:
        problems.append(f"내부 링크 {len(links)}개(최대 2)")
    detail = f"카드 {len(ads)}개 위치 {pcts}% · 내부 링크 {len(links)}개"
    return item("B17", "슬롯 배치", "걸림" if problems else "OK", detail + (" — " + " · ".join(problems) if problems else ""))


# ── B18 대가성 고지 ────────────────────────────────────
def b18_disclosure(body: str) -> dict:
    lines = _lines(body)
    intro = "\n".join(_intro_lines(body))
    ads = [l for l in lines if AD_RE.match(l.strip())]
    problems = []
    if "내돈내산" not in intro:
        problems.append("도입부에 '내돈내산' 없음")
    if not VISIT_DATE_RE.search(intro):
        problems.append("도입부에 방문일(2026년 11월 16일) 없음")
    if ads and not all(w in intro for w in DISCLOSURE_WORDS):
        problems.append("제휴 카드가 있는데 도입부에 제휴·수수료 고지 없음")
    # 발행 직전에도 고지가 살아 있는지(발행기가 지우지 않게) — 도입부 한 곳이면 충분하지만 문장이 통째로 빠지지 않았는지 본다
    if ads and "수수료" not in body:
        problems.append("본문 어디에도 수수료 고지 문장이 없음")
    if "[협찬]" in intro and not re.search(r"제공받", body):
        problems.append("[협찬] 표기 글인데 '제공받' 문장 없음")
    return item("B18", "대가성 고지", "걸림" if problems else "OK", " · ".join(problems))


# ── B19 문체 비율 ──────────────────────────────────────
def b19_style_ratio(body: str) -> dict:
    sents = []
    for l in _lines(body):
        s = l.strip()
        if not s or s.startswith(("【", "■", ">", "|", "▶", "#", "http", "—", "=")) or FAQ_Q_RE.match(s):
            continue
        s = ANY_COLOR_TOKEN_RE.sub("", s)
        sents += [x for x in re.split(r"(?<=[.!?])\s+", s) if len(x.strip()) >= 6]
    if len(sents) < 10:
        return item("B19", "문체 비율", "참고", f"문장 {len(sents)}개 — 재기엔 적음")
    formal = sum(1 for s in sents if re.search(r"(습니다|입니다|ㅂ니다)[.!?\s]*$", s.strip()))
    friendly = sum(1 for s in sents if re.search(r"(어요|에요|예요|더라고요|죠|세요)[.!?\s]*$", s.strip()))
    if formal + friendly == 0:
        return item("B19", "문체 비율", "참고", "문장 끝을 못 읽음")
    ratio = formal / (formal + friendly)
    state = "OK" if 0.25 <= ratio <= 0.55 else "주의"
    detail = f"격식 {formal} : 친근 {friendly} = {ratio:.2f}(목표 0.40 ± 0.15)"
    if ratio == 0:
        detail += " — 격식체가 하나도 없어요(정보 문단은 '~습니다'를 섞어요)"
    return item("B19", "문체 비율", state, detail)


# ── B20 금지어·기호 ────────────────────────────────────
def b20_banned(body: str) -> dict:
    lines = _lines(body)
    where, found = [], set()
    for i, l in enumerate(lines):
        if l.strip().startswith("http"):
            continue
        emo = EMOJI_RE.findall(l)
        if emo:
            where.append((i + 1, "이모지·그림문자 " + " ".join(sorted(set(emo)))[:20]))
        for w in BANNED_WORDS:
            if w in l:
                found.add(w)
        s = l.strip()
        if s and len(s) <= 24 and any(w in s for w in EMPTY_PRAISE) and not re.search(r"\d", s):
            where.append((i + 1, "근거 없는 한 줄 평: " + s[:24]))
    detail = []
    emoji_n = sum(1 for _, w in where if "이모지" in w)
    if where:
        detail.append(f"기호·빈말 {len(where)}곳" + (f" (이모지·그림문자 {emoji_n}곳)" if emoji_n else ""))
    if found:
        detail.append("금지어: " + ", ".join(sorted(found)))
    return item("B20", "금지어·기호(이모지 0개)", "걸림" if (where or found) else "OK",
                " · ".join(detail), where[:5])


# ── B21 한 줄 평 ───────────────────────────────────────
REASON_RE = re.compile(r"\d|무료|유료|웨이팅|주차|분|원|시간|평일|주말|냉면|점심|저녁")
WEAK_RE = re.compile("|".join(EMPTY_PRAISE))


def b21_one_liners(body: str) -> dict:
    lines = _lines(body)
    ones = [(i + 1, m.group(1)) for i, l in enumerate(lines) if (m := ONELINER_RE.match(l.strip()))]
    if not is_course(body):
        return item("B21", "한 줄 평", "참고", "코스형 글이 아니면 해당 없음")
    if not 4 <= len(ones) <= 5:
        return item("B21", "한 줄 평", "걸림", f"{len(ones)}줄(4~5줄)")
    weak = [(n, s) for n, s in ones if not REASON_RE.search(s) or (WEAK_RE.search(s) and len(s) <= 24)]
    return item("B21", "한 줄 평", "주의" if weak else "OK",
                f"{len(ones)}줄" + (f" · 근거 없는 줄 {len(weak)}개" if weak else ""), weak[:5])


# ── B22 내부 링크 ──────────────────────────────────────
def b22_internal_links(body: str) -> dict:
    lines = _lines(body)
    links = [(i, m.group(1), m.group(2)) for i, l in enumerate(lines) if (m := LINK_RE.match(l.strip()))]
    if not links:
        return item("B22", "내부 링크", "참고", "내부 링크 없음(생략 가능)")
    problems, where = [], []
    for i, label, url in links:
        if not re.search(r"blog\.naver\.com/\w+/\d{9,}", url):
            problems.append(f"{i + 1}번째 줄 내부 링크 주소가 아님: {url[:40]}")
            where.append((i + 1, url[:40]))
        prev = next((l.strip() for l in reversed(lines[:i]) if l.strip()), "")
        if not re.search(r"이날|이어서|다음에|전에 쓴|같이 본", prev):
            problems.append(f"{i + 1}번째 줄: 링크 앞에 동선 근거 문장이 없음")
    return item("B22", "내부 링크", "걸림" if problems else "OK", " · ".join(problems[:3]), where[:3])


# ── B23 지도 핀·소스 ───────────────────────────────────
def b23_map_blocks(body: str) -> dict:
    lines = _lines(body)
    places = [(i, m.group(1), (m.group(2) or "").strip()) for i, l in enumerate(lines)
              if (m := PLACE_RE.match(l.strip()))]
    maps = [(i, m.group(1)) for i, l in enumerate(lines) if (m := MAP_RE.match(l.strip()))]
    if not places and not maps:
        return item("B23", "지도 주소·소스 대조", "참고", "지도 줄 없음(해당 없음)")
    problems, where = [], []
    for i, name, addr in places:
        if not addr:
            problems.append(f"{i + 1}번째 줄: '【장소】 {name}'에 주소가 없어요(이름만으로는 핀 오매핑을 막을 수 없음)")
            where.append((i + 1, name))
        elif not re.search(r"로|길|동|읍|면|구", addr):
            problems.append(f"{i + 1}번째 줄: 주소가 도로명주소 형태가 아님({addr[:24]})")
            where.append((i + 1, addr[:24]))
    for i, url in maps:
        if not re.search(r"(google\.[a-z.]+/maps|maps\.app\.goo\.gl|goo\.gl/maps)", url):
            problems.append(f"{i + 1}번째 줄: 해외 지도는 구글 지도 링크여야 해요({url[:30]})")
            where.append((i + 1, url[:30]))
    return item("B23", "지도 주소·소스 대조", "걸림" if problems else "OK",
                " · ".join(problems[:3]) if problems else f"지도 {len(places)}곳 + 링크 {len(maps)}개", where[:3])


# ── B24 태그 품질 ──────────────────────────────────────
BRAND_TAG = "서준의여행한입"
LEGACY_TAG = "달리는이기사"


def b24_tags(tags: List[str], title: str, body: str) -> dict:
    if not tags:
        return item("B24", "태그 품질", "걸림", "태그 없음")
    problems = []
    if not 10 <= len(tags) <= 15:
        problems.append(f"{len(tags)}개(10~15개)")
    if len(set(tags)) != len(tags):
        problems.append("중복 태그")
    if BRAND_TAG not in tags:
        problems.append(f"#{BRAND_TAG} 없음")
    hay = re.sub(r"\s", "", title + body)
    overlap = [t for t in tags if len(t) >= 2 and t not in (BRAND_TAG,) and t in hay]
    if len(overlap) < 3:
        problems.append(f"본문·제목과 이어지는 태그가 {len(overlap)}개뿐(3개 이상)")
    state = "걸림" if any("개(10" in p or "없음" in p or "중복" in p for p in problems) else ("주의" if problems else "OK")
    detail = f"{len(tags)}개" + (" — " + " · ".join(problems) if problems else "")
    if LEGACY_TAG in tags:
        detail += " · 옛 태그 #달리는이기사(새 글엔 넣지 않아요)"
    return item("B24", "태그 품질", state, detail)


# ── B25 블록 간격 ──────────────────────────────────────
def b25_block_spacing(body: str) -> dict:
    lines = _lines(body)
    problems = []

    def blank_between(a: int, b: int) -> bool:
        return any(not l.strip() for l in lines[a + 1:b])

    for i, l in enumerate(lines):
        s = l.strip()
        if not s:
            continue
        if FIGURE_RE.match(s) or s.startswith(("【장소】", "【지도】", "【쇼츠】", "【한줄평】", "【제휴】", "【링크】")):
            j = i - 1
            if j >= 0 and lines[j].strip() and not FIGURE_RE.match(lines[j].strip()):
                problems.append(f"{i + 1}번째 줄: 앞 문단과 빈 줄 없이 붙음")
            k = i + 1
            if k < len(lines) and lines[k].strip() and not FIGURE_RE.match(lines[k].strip()):
                problems.append(f"{i + 1}번째 줄: 뒤 문단과 빈 줄 없이 붙음")
        if s.startswith("|") and not (i > 0 and lines[i - 1].strip().startswith("|")):
            j = i - 1
            if j >= 0 and lines[j].strip():
                problems.append(f"{i + 1}번째 줄: 표 위에 빈 줄 없음")
        elif s.startswith(">"):
            j = i - 1
            if j >= 0 and lines[j].strip() and not lines[j].strip().startswith(">"):
                problems.append(f"{i + 1}번째 줄: 소제목 위에 빈 줄 없음")
        elif s.startswith("■"):
            j = i - 1
            if j >= 0 and lines[j].strip():
                problems.append(f"{i + 1}번째 줄: 소제목 위에 빈 줄 없음")
    # 사진 3장 이상 연달아 붙고 그 사이 글 없음
    figs = [i for i, l in enumerate(lines) if FIGURE_RE.match(l.strip())]
    run = 1
    for a, b in zip(figs, figs[1:]):
        if not any(l.strip() and not FIGURE_RE.match(l.strip()) for l in lines[a + 1:b]):
            run += 1
            if run >= 3:
                problems.append(f"{a + 1}번째 줄: 사진이 글 없이 3장 이상 붙음")
                break
        else:
            run = 1
    uniq = list(dict.fromkeys(problems))
    return item("B25", "블록 간격(사진·빈 줄·문단)", "걸림" if uniq else "OK",
                " · ".join(uniq[:3]) + (f" 외 {len(uniq) - 3}곳" if len(uniq) > 3 else ""))


# ── B26 소제목 볼드 ────────────────────────────────────
def b26_heading_bold(body: str) -> dict:
    """소제목은 볼드로 나가야 한다.

    발행기(neo_source.render_block)는 `■`·`> N.` 소제목을 **언제나 굵은 h3**로 넣는다.
    그래서 이 게이트는 두 가지를 나눠 본다.
      - 걸림: 소제목을 **색으로 대신한** 경우(색만 있는 줄은 h3 로 렌더되지 않아 굵지도 소제목도 아니다)
      - 주의: 원본에 `**굵게**` 표시가 없는 경우(출력은 굵지만 원본도 맞춰 두는 게 좋다)
    이렇게 나누지 않으면 예전 완성본(■ 소제목)이 전부 발행 차단된다 — 출력은 이미 굵다.
    """
    heads, colored, weak = [], [], []
    for i, l in enumerate(_lines(body)):
        s = l.strip()
        m = HEADING_RE.match(s)
        if not m:
            continue
        text = m.group(1).strip()
        if FAQ_Q_RE.match(text):
            continue
        heads.append(text)
        has_bold = bool(re.search(r"\*\*.+?\*\*", text))
        has_color = bool(ANY_COLOR_TOKEN_RE.search(text))
        if has_color and not has_bold:
            colored.append((i + 1, text[:30]))
        elif not has_bold:
            weak.append((i + 1, text[:30]))
    if not heads:
        return item("B26", "소제목 볼드", "참고", "소제목 없음(해당 없음)")
    if colored:
        return item("B26", "소제목 볼드", "걸림",
                    f"소제목을 색으로 대신했어요({colored[0][1]}) — 굵게 쓰세요", colored[:5])
    detail = f"{len(heads)}개" + (f" · 원본에 **굵게** 표시 없음 {len(weak)}개('{weak[0][1]}')" if weak else "")
    return item("B26", "소제목 볼드", "주의" if weak else "OK", detail, weak[:5])


# ── B27 본문 색·강조 ──────────────────────────────────
def b27_body_color(body: str) -> dict:
    lines = _lines(body)
    problems, where = [], []
    per_section: Dict[int, int] = {}
    sec_of_line: Dict[int, int] = {}
    sec = 0
    for i, l in enumerate(lines):
        if SECTION_RE.match(l.strip()):
            sec += 1
        sec_of_line[i] = sec
        toks = ANY_COLOR_TOKEN_RE.findall(l)
        for name in toks:
            if name in BAD_COLOR_TOKENS or name.startswith("#"):
                problems.append(f"{i + 1}번째 줄: 본문 글자색 지정({name}) — 진그레이 기본값을 쓰세요")
                where.append((i + 1, name))
        if len(toks) > 1:
            problems.append(f"{i + 1}번째 줄: 포인트 컬러 {len(toks)}개(문단당 1개)")
        per_section[sec_of_line[i]] = per_section.get(sec_of_line[i], 0) + len(toks)
    heavy = {k: v for k, v in per_section.items() if v > 2}
    if heavy:
        problems.append("섹션당 색 포인트 3개 이상: " + ", ".join(f"{k}번 섹션 {v}개" for k, v in sorted(heavy.items())))
    counts: Dict[str, int] = {}
    for name in ANY_COLOR_TOKEN_RE.findall(body):
        if name in POINT:
            counts[name] = counts.get(name, 0) + 1
    many = {k: v for k, v in counts.items() if v > 5}
    if many:
        problems.append("같은 색 5회 초과: " + ", ".join(f"{k} {v}회" for k, v in many.items()))
    state = "걸림" if any("글자색" in p for p in problems) else ("주의" if problems else "OK")
    return item("B27", "본문 색·강조", state,
                f"포인트 {sum(counts.values())}개" + (" — " + " · ".join(problems) if problems else ""), where[:4])


# ── B28 SEO·AEO·GEO ───────────────────────────────────
def b28_seo(body: str, title: str) -> dict:
    try:
        import seo_aeo_geo
    except Exception as e:      # 모듈이 없어도 검문소가 죽지 않게
        return item("B28", "SEO·AEO·GEO", "참고", f"검사 모듈을 못 불러요({type(e).__name__})")
    return seo_aeo_geo.check(body, title)


def run(body: str, title: str, tags: List[str]) -> List[dict]:
    """검문소가 부르는 한 줄 입구 — B16~B28."""
    out = [b16_course_structure(body, title)]
    if is_course(body):
        out += [b17_slots(body), b18_disclosure(body), b19_style_ratio(body), b21_one_liners(body),
                b22_internal_links(body)]
    else:
        out += [b19_style_ratio(body)]
    out += [b20_banned(body), b23_map_blocks(body), b24_tags(tags, title, body),
            b25_block_spacing(body), b26_heading_bold(body), b27_body_color(body), b28_seo(body, title)]
    return out
