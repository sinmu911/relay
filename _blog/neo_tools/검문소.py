#!/usr/bin/env python3
"""검문소 — Claude 가 눈으로 보던 발행 전 점검을 파이썬으로 (DESIGN-BLOG-PYPORT-001, 10-07, 사용자 "그것도 하자").

사용: python3 검문소.py <완성본.md> [--json]
읽기만 한다(원본 글·계획표를 바꾸지 않음). 결과: 항목별 OK/주의/걸림 + 위치. 걸림이 있으면 종료코드 1.
 B1 금지 표현·빈칸([확인 필요]·[사장님 한 줄])·리얼엔진 걸림
 B2 근거 없는 숫자: 본문의 단위 붙은 숫자가 재료·시리즈계획·같은 주제 초안·점검 메모에 있는지 (근거 묶음이 완전하지 않아 '주의')
 B3 형식: 내돈내산 줄 · AI 고지 · 자주 묻는 질문 ≤ 3 · 파랑 강조 ≤ 5 · 표 3열 이하 · 태그 10개 + 달리는이기사
 B4 그림: 번호 순서 · 파일 존재 · 연달아 붙음 · 안 쓴 그림
 B5 시리즈: 제목 [여행지 ①~④] · 목차(지금 글) · 이전/다음 편 · 계획표 링크와 일치 · 남은 '(발행 후 링크)'
 B8 예약 추천 시각(주마다 요일·분 다르게, 지난 추천과 겹치지 않게) — 상태/예약기록.json
 B12 이음말 반복(~고·~서·그래서…)·같은 낱말 몰림 · B13 문단 띄어쓰기(1~5줄·휴대폰 줄 길이·소제목 앞 빈 줄) · B14 글 색상(파랑 자리) — 도구/문체점검.py
 B15 말투 뽑기 했나(상태/말투배정.json) · 리얼고침 본이면 주의
 B10 같은 틀 반복(최근 완성본과 문단 틀이 거의 같음) · B11 검색어 반복(목표 검색어가 1000자당 너무 자주) — '참고'
 판정: 걸림(발행 전 고침) · 주의(사람이 한 번 볼 것) · 참고(네이버 근거 없는 우리 기준 — 연구6, 10-14 사장님 "나쁠 거 없으니까")
 운영 점검(블로그 전체): python3 검문소.py --운영 [--json]
  B6 발행 감지(계획표 갱신 제안·채울 링크) · B7 다음 2편 후보 · B9 메인 목록 제안(메인/메인글_목록_제안.md) — 모두 제안만, 원본 불변
"""
import datetime, glob, importlib.util, json, os, re, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
B = os.path.dirname(HERE)
STATE = os.path.join(B, "상태")
CIRC = "①②③④⑤⑥"
EMO = re.compile("[" + chr(0x1F300) + "-" + chr(0x1FAFF) + "☀-➿]")   # 이모지 범위(드라이브에 올릴 때 글자가 안 바뀌게 chr 로)
HEAD = re.compile(r"^={5,}\n([^\n=][^\n]*)\n={5,}$", re.M)
FIG = re.compile(r"^【그림\s*([0-9]+[a-z]?)】\s*(\S+)")
NUMU = re.compile(r"(USD|AED|\$)?\s?(\d[\d,]*(?:\.\d+)?)\s?(디르함|달러|원|km|시간|분|박|세|%|엔|바트|동)?")


def nfc(s):
    return unicodedata.normalize("NFC", s)


def _mod(name):
    sp = importlib.util.spec_from_file_location(name, os.path.join(HERE, name + ".py"))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    return m


def sections(text):
    hs = list(HEAD.finditer(text))
    out = {"머리": text[: hs[0].start()] if hs else text}
    for i, m in enumerate(hs):
        out[m.group(1).strip().split()[0]] = text[m.end(): hs[i + 1].start() if i + 1 < len(hs) else len(text)].strip("\n")
    return out


def item(code, name, state, detail="", where=None):
    return {"코드": code, "항목": name, "판정": state, "내용": detail, "위치": where or []}


def numbers(text):
    """단위가 붙었거나 3자리 이상인 숫자만(①, 3일 같은 작은 수는 제외)."""
    out = []
    for m in NUMU.finditer(text):
        pre, n, unit = m.groups()
        v = n.replace(",", "")
        if unit in (None, "박", "세", "분", "시간") and not pre and len(v.replace(".", "")) < 3:
            continue
        out.append((v.rstrip("0").rstrip(".") if "." in v else v, m.group(0).strip()))
    return out


def evidence(path, sec):
    """근거 묶음: 시리즈계획 · 재료 폴더 글 · 같은 날짜·주제의 다른 초안 · 완성본 머리/점검 메모."""
    parts = [sec.get("머리", ""), sec.get("점검", "")]
    for f in [os.path.join(B, "시리즈계획.md")] + glob.glob(os.path.join(B, "재료", "**", "*.*"), recursive=True):
        if f.lower().endswith((".md", ".txt")):
            try: parts.append(open(f, encoding="utf-8").read())
            except Exception: pass
    base = nfc(os.path.basename(path))
    key = "_".join(base.split("_")[:2])
    for f in glob.glob(os.path.join(os.path.dirname(path), "*.md")):
        nf = nfc(os.path.basename(f))
        if nf != base and nf.startswith(key) and "_리얼고침" not in nf:
            try: parts.append(open(f, encoding="utf-8").read())
            except Exception: pass
    sm = re.match(r"^\[(\S+)\s*[" + CIRC + r"]\]", sec.get("제목", "").strip())
    if sm:   # 같은 시리즈의 다른 편(예: ③ 의 140km 를 ④ 에서 다시 씀)도 근거로
        for f in glob.glob(os.path.join(os.path.dirname(path), "*.md")):
            nf = nfc(os.path.basename(f))
            if nf != base and "_리얼고침" not in nf:
                try:
                    t = nfc(open(f, encoding="utf-8").read())
                except Exception:
                    continue
                if sections(t).get("제목", "").strip().startswith(f"[{sm.group(1)} "):
                    parts.append(t)
    ev = nfc("\n".join(parts))
    return {v for v, _ in numbers(ev)} | set(re.findall(r"\d[\d,]*(?:\.\d+)?", ev.replace(",", "")))


def check(path):
    text = nfc(open(path, encoding="utf-8").read())
    sec = sections(text)
    body = sec.get("본문", "")
    lines = body.split("\n")
    OFF = text[: text.find(body)].count("\n") if body and body in text else 0  # 위치는 파일 줄 번호로
    res = []
    real = _mod("리얼엔진")
    is_main = "메인" in nfc(os.path.basename(os.path.dirname(os.path.abspath(path))))  # 메인(링크 모음) 글은 일반 글 형식 규칙 일부 제외

    # ---- B1 ----
    prose = "\n".join(l for l in lines if not EMO.match(l.strip()[:2] or " ") and not l.strip().startswith(("http", "#")))
    quoted = re.sub(r"「[^」]*」|\"[^\"]*\"|“[^”]*”", "", prose)
    banned = [b for b in real.BANNED if b in quoted]
    res.append(item("B1", "금지 표현", "걸림" if banned else "OK", ", ".join(banned)))
    holes = [(i + 1 + OFF, l.strip()[:40]) for i, l in enumerate(lines) if re.search(r"\[확인 필요|\[사장님 한 줄", l)]
    res.append(item("B1", "빈칸([확인 필요]·[사장님 한 줄])", "걸림" if holes else "OK", f"{len(holes)}곳", holes[:5]))
    try:
        r = real.run(path)
        # 말투 수치(숫자 개수·감정 개수 등)는 우리 표본에서 나온 기준이라 '참고'로만(연구6). 걸림은 그대로.
        res.append(item("B1", "리얼엔진", "걸림" if r.get("걸림") else ("참고" if r.get("주의") else "OK"),
                        f"걸림 {r.get('걸림')} · 참고 {r.get('주의')}",
                        [x["지표"] for x in r.get("지표", []) if x["판정"] in ("걸림", "주의")][:5]))
    except Exception as e:
        res.append(item("B1", "리얼엔진", "주의", f"측정 실패 {type(e).__name__}"))

    # ---- B2 ----
    ev = evidence(path, sec)
    miss = []
    for i, l in enumerate(lines):
        s = l.strip()
        if not s or s.startswith(("【그림", "http", "#")) or "http" in s:
            continue
        plain = re.sub(r"\*\*|\{파랑:\s*|\}", "", s)
        man = set(re.findall(r"(\d+(?:\.\d+)?)\s*만", plain))   # '약 220만 원' = 근거 2,202,184 를 만 원 단위로 줄인 것
        for v, shown in numbers(plain):
            if v not in ev and v.replace(".", "") not in ev:
                if v in man and any(n.isdigit() and abs(int(n) / 10000 - float(v)) < 1 for n in ev):
                    continue
                miss.append((i + 1 + OFF, shown))
    res.append(item("B2", "근거 없는 숫자", "주의" if miss else "OK", f"{len(miss)}개 (재료·계획표·초안에서 못 찾음)", miss[:8]))

    # ---- B3 ----
    nonempty = [l.strip() for l in lines if l.strip() and not FIG.match(l.strip())]
    if not is_main:
        res.append(item("B3", "둘째 줄 내돈내산", "OK" if nonempty and nonempty[0].startswith("내돈내산") else "걸림", (nonempty[0][:30] if nonempty else "")))
    tail = "\n".join(nonempty[-6:])
    res.append(item("B3", "끝맺음 위 AI 고지", "OK" if re.search(r"AI", tail) else ("주의" if is_main else "걸림")))
    faq_i = next((i for i, l in enumerate(lines) if "자주 묻는 질문" in l), None)
    nfaq = 0
    if faq_i is not None:
        for l in lines[faq_i + 1:]:
            if l.startswith(("■", "←", "다음 편")): break
            nfaq += bool(re.match(r"^\d+\.\s", l.strip()))
    res.append(item("B3", "자주 묻는 질문 ≤ 3", "OK" if nfaq <= 3 else "걸림", f"{nfaq}개"))
    blue = body.count("{파랑:")
    res.append(item("B3", "파랑 강조 ≤ 5", "OK" if blue <= 5 else "걸림", f"{blue}곳"))
    wide = [(i + 1 + OFF, l[:30]) for i, l in enumerate(lines) if l.strip().startswith("|") and l.strip().count("|") - 1 > 3]
    res.append(item("B3", "표 3열 이하", "OK" if not wide else "걸림", "", wide[:3]))
    tags = re.findall(r"#\S+", sec.get("태그", ""))
    ok = len(tags) == 10 and any("달리는이기사" in t for t in tags) and len(set(tags)) == len(tags)
    res.append(item("B3", "태그 10개 + 달리는이기사", "OK" if ok else "걸림", f"{len(tags)}개" + ("" if any("달리는이기사" in t for t in tags) else " · 달리는이기사 없음")))

    # ---- B4 ----
    figs = [(i, FIG.match(l.strip())) for i, l in enumerate(lines) if FIG.match(l.strip())]
    key = "_".join(nfc(os.path.basename(path)).split("_")[:2])
    dirs = [d for d in glob.glob(os.path.join(os.path.dirname(path), "*")) if os.path.isdir(d) and nfc(os.path.basename(d)).startswith(key) and "이미지" in nfc(os.path.basename(d))]
    if is_main:
        dirs = [os.path.dirname(os.path.abspath(path))]
    have = {nfc(f) for d in dirs for f in os.listdir(d)}
    missing = [(i + 1 + OFF, m.group(2)) for i, m in figs if m.group(2) not in have]
    res.append(item("B4", "그림 파일 존재", "걸림" if missing or not dirs else "OK", "그림 폴더 없음" if not dirs else f"{len(figs)}장", missing[:5]))
    order = [m.group(1) for _, m in figs]
    seq = [(int(re.match(r"\d+", o).group()), o) for o in order]
    bad_order = [o for (a, _), (b, o) in zip(seq, seq[1:]) if b < a or (b == a and o == _)] if seq else []
    dup = [o for o in set(order) if order.count(o) > 1]
    gaps = sorted(set(range(seq[0][0], seq[-1][0] + 1)) - {n for n, _ in seq}) if seq else []
    res.append(item("B4", "그림 번호 순서", "걸림" if bad_order or dup or gaps else "OK", f"중복 {dup} · 빠진 번호 {gaps}" if (dup or gaps or bad_order) else ""))
    adj = []
    for (i1, _), (i2, _) in zip(figs, figs[1:]):
        if not any(l.strip() for l in lines[i1 + 1:i2]):
            adj.append(i2 + 1 + OFF)
    res.append(item("B4", "그림 연달아 붙음", "걸림" if adj else "OK", "", adj[:5]))
    used = {m.group(2) for _, m in figs}
    unused = sorted(f for f in have if f.lower().endswith(".png") and f not in used)
    res.append(item("B4", "안 쓴 그림", "주의" if unused else "OK", ", ".join(unused[:6])))

    # ---- B5 ----
    title = sec.get("제목", "").strip().split("\n")[0]
    tm = re.match(r"^\[(\S+)\s*([" + CIRC + r"])\]", title)
    if not tm:
        res.append(item("B5", "시리즈 제목 [여행지 ①~④]", "참고", "시리즈 글이 아니면(가지·기존 글 수정) 해당 없음: " + title[:30]))
    else:
        place, no = tm.groups(); idx = CIRC.index(no)
        res.append(item("B5", "시리즈 제목 [여행지 ①~④]", "OK", f"{place} {no}"))
        toc = [l for l in lines if l.strip() and l.strip()[0] in CIRC]  # 빈 줄 제외(빈 문자열 in 문자열 = 참 함정)
        here = any("지금 글" in l for l in toc)
        res.append(item("B5", "목차 박스(지금 글 표시)", "OK" if len(toc) >= 3 and here else "걸림", f"목차 {len(toc)}줄"))
        prev = [l for l in lines if l.strip().startswith("← 이전 편")]
        nxt = [l for l in lines if l.strip().startswith("다음 편 →")]
        res.append(item("B5", "이전 편 연결", "OK" if (idx == 0 or prev) else "걸림"))
        res.append(item("B5", "다음 편 연결·예고", "OK" if (idx >= 3 or nxt) else "걸림"))
        plan = {}
        try:
            for l in nfc(open(os.path.join(B, "시리즈계획.md"), encoding="utf-8").read()).split("\n"):
                c = [x.strip() for x in l.split("|")]
                if len(c) >= 9 and c[2] in list(CIRC):
                    u = re.search(r"https?://\S+", c[8]); plan[c[2]] = u.group(0) if u else ""
        except Exception:
            pass
        diff = []
        for l in toc + prev + nxt:
            n = next((ch for ch in l if ch in CIRC), None); u = re.search(r"https?://\S+", l)
            if n and u and plan.get(n) and not plan[n].startswith(u.group(0)[:44]):
                diff.append(f"{n}: 글 {u.group(0)[-14:]} ≠ 계획표 {plan[n][-14:]}")
            if n and u and len(re.search(r"/(\d+)$", u.group(0).rstrip("/")).group(1) if re.search(r"/(\d+)$", u.group(0).rstrip("/")) else "000000000000") < 12:
                diff.append(f"{n}: 주소가 잘린 것 같음 {u.group(0)[-16:]}")
        res.append(item("B5", "링크가 계획표와 일치", "걸림" if diff else "OK", "", sorted(set(diff))[:5]))
        pend = [(i + 1 + OFF, l.strip()[:36]) for i, l in enumerate(lines) if "(발행 후 링크)" in l or "다음 글 예정" in l]
        res.append(item("B5", "아직 못 채운 링크", "주의" if pend else "OK", f"{len(pend)}곳(발행 뒤 채움)", pend[:4]))

    # ---- B10 같은 틀 반복 · B11 검색어 반복 (네이버 어뷰징 신호로 자주 꼽힘 — 참고) ----
    mine = shape(lines)
    twins = []
    for f in glob.glob(os.path.join(os.path.dirname(path), "*.md")):
        nf = nfc(os.path.basename(f))
        if nf == nfc(os.path.basename(path)) or "완성본" not in nf or "_리얼고침" in nf:
            continue
        try:
            other = shape(sections(nfc(open(f, encoding="utf-8").read())).get("본문", "").split("\n"))
        except Exception:
            continue
        if len(mine) >= 8 and difflib.SequenceMatcher(None, mine, other).ratio() >= 0.9:
            twins.append(nf[:40])
    res.append(item("B10", "같은 틀 반복", "참고" if twins else "OK",
                    "최근 글과 문단 순서가 거의 같아요 — 소제목·순서를 조금 다르게: " + ", ".join(twins[:3]) if twins else ""))
    km = re.search(r"목표 검색어:\s*(.+)", sec.get("머리", ""))
    if km:
        kw = km.group(1).strip()
        chars = max(1, len(re.sub(r"\s", "", body)))
        per = body.count(kw) * 1000 / chars
        res.append(item("B11", "검색어 반복", "참고" if per > 3 else "OK", f"'{kw}' {body.count(kw)}번 · 1000자당 {per:.1f}번(3 넘으면 참고)"))

    # ---- B12 이음말·같은 낱말 반복 · B13 문단 띄어쓰기 · B14 글 색상 (도구/문체점검.py, 사장님 10-14) ----
    try:
        res.extend(_mod("문체점검").check(body, OFF))
    except Exception as e:
        res.append(item("B12", "문체 점검", "참고", f"실행 못 함 {type(e).__name__}"))
    # ---- B15 말투 뽑기 했나 · 리얼고침 본인가 (사장님 10-14 "말투 섞어서 랜덤으로", 연구7) ----
    me = nfc(os.path.basename(path))
    try:
        picked = json.load(open(os.path.join(STATE, "말투배정.json"), encoding="utf-8")).get("글", {})
    except (OSError, ValueError):
        picked = {}
    res.append(item("B15", "말투 뽑기(도구/말투뽑기.py)", "OK" if me in picked else "참고",
                    "" if me in picked else "새 글이면 쓰기 전에 python3 도구/말투뽑기.py " + me[:40]))
    if "_리얼고침" in me:
        res.append(item("B15", "리얼고침 본", "주의", "자동 고침 본은 원본보다 걸림이 많았어요(연구7) — 발행은 원본 완성본으로"))

    # ---- B8 ----
    res.append(item("B8", "예약 추천 시각", "OK", suggest_time()))
    # B6·B7·B9 는 글 하나가 아니라 블로그 전체를 보는 점검 → `검문소.py --운영` (아래 운영 점검)
    summ = {"파일": nfc(os.path.basename(path)), "검문소": "0.4", "걸림": sum(r["판정"] == "걸림" for r in res),
            "주의": sum(r["판정"] == "주의" for r in res), "참고": sum(r["판정"] == "참고" for r in res), "항목": res}
    return summ


def shape(lines):
    """문단 틀: 줄 종류만 순서대로(그림·소제목·요약·목차·질문·링크·글) — 글 내용은 안 봄."""
    out = []
    for l in lines:
        s = l.strip()
        if not s:
            continue
        k = ("그림" if s.startswith("【그림") else "소제목" if s.startswith("■") else "요약" if s.startswith("▶")
             else "목차" if s[0] in CIRC else "질문" if re.match(r"^\d+\.\s", s) else "링크" if "http" in s else "글")
        if not out or out[-1] != k:
            out.append(k)
    return out


def suggest_time(today=None, save=True):
    """매주 요일·분을 바꿔 2편(하루 1편 이하). 네이버 예약은 5일 뒤까지 → 일요일 기준 다음 월~금."""
    today = today or datetime.date.today()
    wk = today.isocalendar()[1]
    pairs = [(0, 3), (1, 4), (0, 4), (1, 3)]  # 월·목 / 화·금 / 월·금 / 화·목
    mins = [7, 22, 41, 13, 36, 52, 18, 47]
    hours = [19, 20, 19, 21]
    hist = {}
    f = os.path.join(STATE, "예약기록.json")
    try: hist = json.load(open(f, encoding="utf-8"))
    except Exception: pass
    key = f"{today.isocalendar()[0]}-W{wk:02d}"
    if key not in hist:
        k = wk
        last = list(hist.values())[-1] if hist else None
        for _ in range(8):
            d1, d2 = pairs[k % 4]
            cand = [f"{'월화수목금'[d1]} {hours[k % 4]}:{mins[k % 8]:02d}", f"{'월화수목금'[d2]} {hours[(k + 1) % 4]}:{mins[(k + 3) % 8]:02d}"]
            if cand != last: break
            k += 1
        hist[key] = cand
        if save:
            try:
                os.makedirs(STATE, exist_ok=True); json.dump(hist, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            except Exception:
                pass
    return " / ".join(hist[key])


# ================= 운영 점검 (블로그 전체) — B6 발행 감지 · B7 다음 2편 후보 · B9 메인 목록 =================
import difflib, html, urllib.request

ALIAS = {"베트남": "다낭", "그랩": "다낭", "바나힐": "다낭", "큐슈": "규슈", "삿포로": "홋카이도", "오타루": "홋카이도", "비에이": "홋카이도",
        "타이완": "대만", "타이페이": "대만", "UAE": "두바이", "야스": "아부다비", "마디푸시": "몰디브"}
# 주제 밖(먹거리 리뷰 등). '처음이라면'의 '라면'을 음식으로 잡던 오탐 수정(10-07 시험에서 발견) — 낱말 앞이 한글이면 제외
OFFTOPIC = re.compile(r"(?<![가-힣])라면|컵라면|봉지라면|곰탕면|파래김|조미김|(?<![가-힣])김 리뷰|과자|^\[리뷰\]")


def _norm(t):
    return re.sub(r"[\[\]【】()①②③④⑤\s:,!'\"·\-~?]", "", t)


def _sim(a, b):
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def rss_items(rss_text=None):
    """블로그 글 목록(읽기만). 받아 오기 실패하면 저장된 사본. 돌려줌: [{log,title,date,url}]"""
    texts = []
    if rss_text is None:
        try:
            req = urllib.request.Request("https://rss.blog.naver.com/mose_love.xml", headers={"User-Agent": "Mozilla/5.0"})
            texts.append(urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore"))
        except Exception:
            cands = [os.path.expanduser("~/MicLab/blog_learn/cache/rss.xml")] + sorted(glob.glob(os.path.join(B, "완료", "기존글목록_*.xml")), reverse=True)
            for c in cands:
                try: texts.append(open(c, encoding="utf-8").read()); break
                except Exception: pass
    else:
        texts.append(rss_text)
    out = []
    pub = _mod("발행비교")
    for t in texts:
        for it in pub.rss_items(t):
            it["url"] = f"https://blog.naver.com/mose_love/{it['log']}"; out.append(it)
    return out


def plan_rows():
    rows = []
    try:
        for i, l in enumerate(nfc(open(os.path.join(B, "시리즈계획.md"), encoding="utf-8").read()).split("\n"), 1):
            c = [x.strip() for x in l.split("|")]
            if len(c) >= 9 and c[1] in ("줄기", "가지", "목록"):
                u = re.search(r"https?://\S+", c[8])
                rows.append({"줄": i, "종류": c[1], "번호": c[2], "제목": c[3], "작업": c[6], "상태": c[7], "링크": u.group(0) if u else ""})
    except Exception:
        pass
    return rows


def finals():
    out = []
    for f in glob.glob(os.path.join(B, "초안", "*.md")):
        nf = nfc(os.path.basename(f))
        if "완성본" in nf and "_리얼고침" not in nf:
            try:
                t = nfc(open(f, encoding="utf-8").read()); sec = sections(t)
                out.append({"file": nf, "path": f, "title": sec.get("제목", "").strip().split("\n")[0], "text": t})
            except Exception:
                pass
    return out


def detect(items=None):
    """B6: 새 발행 감지 → 계획표 상태·링크 제안, 완성본의 '(발행 후 링크)' 채울 주소. 파일은 제안본만."""
    items = items if items is not None else rss_items()
    rows, fin = plan_rows(), finals()
    known = {re.search(r"/(\d+)", r["링크"]).group(1) for r in rows if re.search(r"/(\d+)", r["링크"])}
    props, newlink = [], {}
    for r in rows:
        if r["링크"] or "발행됨" in r["상태"]:
            continue
        best = max(items, key=lambda it: _sim(r["제목"], it["title"]), default=None)
        if best and _sim(r["제목"], best["title"]) >= 0.55 and best["log"] not in known:
            props.append({"계획표 줄": r["줄"], "번호": r["번호"], "제목": r["제목"][:40], "제안": f"상태 → 발행됨({best['date']}) · 링크 → {best['url']}",
                          "발행 제목": best["title"][:50]})
            newlink[r["번호"]] = best["url"]; known.add(best["log"])
    links = {r["번호"]: r["링크"] for r in rows if r["링크"]}; links.update(newlink)
    fills = []
    for f in fin:
        for i, l in enumerate(f["text"].split("\n"), 1):
            if "(발행 후 링크)" in l or "다음 글 예정" in l:
                n = next((ch for ch in l if ch in CIRC), None)
                if n and links.get(n):
                    fills.append({"파일": f["file"], "줄": i, "지금": l.strip()[:50], "채울 주소": links[n]})
    main_urls = set()
    try: main_urls = set(re.findall(r"mose_love/(\d+)", open(os.path.join(B, "메인", "메인글_완성본.md"), encoding="utf-8").read()))
    except Exception: pass
    stray = [{"제목": it["title"][:50], "주소": it["url"], "날짜": it["date"], "비고": "주제 밖" if OFFTOPIC.search(it["title"]) else "새 글?"}
             for it in items if it["log"] not in known and it["log"] not in main_urls]
    return {"글 목록 수": len(items), "계획표 갱신 제안": props, "채울 링크": fills, "계획표·메인에 없는 글": stray}


def next2(items=None):
    """B7: 다음 주 2편 후보 — 시리즈 순서(새 글 1 + 기존 글 수정 1) > 재료 폴더 > 기존 글 우선순위."""
    rows, fin = plan_rows(), finals()
    done = lambda r: "발행됨" in r["상태"] or "키트 완료" in r["상태"] or "초안 완료" in r["상태"] or any(_sim(r["제목"], f["title"]) >= 0.6 for f in fin)
    stems = [r for r in rows if r["종류"] == "줄기"]
    new = [r for r in stems if r["작업"].startswith("새 글") and not done(r)]
    cur = [r["번호"] for r in stems if done(r)]            # 이미 쓴 줄기 — 그 가지부터 수정
    fix = [r for r in rows if "기존 글" in r["작업"] and "수정" in r["작업"] and not done(r)]
    fix.sort(key=lambda r: (0 if any(r["번호"].startswith(c) for c in cur[-1:]) else 1 if any(r["번호"].startswith(c) for c in cur) else 2, r["줄"]))
    mats = []
    md = os.path.join(B, "재료")
    if os.path.isdir(md):
        mats = sorted([d for d in os.listdir(md) if os.path.isdir(os.path.join(md, d))], key=lambda d: os.path.getmtime(os.path.join(md, d)))
    pick = {"새 글": new[0] if new else None, "기존 글 수정": fix[0] if fix else None}
    alt = {"새 글 다음 후보": [r["번호"] + " " + r["제목"][:30] for r in new[1:3]], "수정 다음 후보": [r["번호"] + " " + r["제목"][:30] for r in fix[1:4]], "재료 폴더(오래된 순)": [nfc(m) for m in mats[:3]]}
    fallback = []
    if not new and not fix and not mats:   # 계획·재료가 다 비면 기존 글 우선순위(렌트카·운전 > 일정 > 관광지 > 맛집)
        items = items if items is not None else rss_items()
        def score(t):
            if OFFTOPIC.search(t): return 99
            return 0 if re.search(r"렌트|운전|주차|교통", t) else 1 if re.search(r"일정|박\s*\d+일", t) else 3 if re.search(r"맛집|카페|식당", t) else 2
        fallback = [{"제목": it["title"][:50], "주소": it["url"], "비고": "주제 밖 — 비공개 권장만" if score(it["title"]) == 99 else ""} for it in sorted(items, key=lambda it: score(it["title"]))[:4]]
    return {"이번 주 2편": {k: (f"{v['번호']} {v['제목']}" + (f" → {v['링크']}" if v and v["링크"] else "")) if v else "없음" for k, v in pick.items()}, **alt, "대체 후보": fallback}


def mainlist(items=None, write=True):
    """B9: 메인 글 목록 점검 — 메인에 없는 글을 나라 구역·분류 이모지와 함께 제안본으로. 원본 메인 글은 안 바꿈."""
    items = items if items is not None else rss_items()
    p = os.path.join(B, "메인", "메인글_완성본.md")
    t = nfc(open(p, encoding="utf-8").read())
    have = set(re.findall(r"mose_love/(\d+)", t))
    heads = [l[1:].strip() for l in t.split("\n") if l.startswith("■ ") and re.search(r"[·]|[가-힣]{2,}", l) and "읽으면" not in l]
    def keys(h):
        ks = [k for k in re.split(r"[·\s]+", re.sub(r"[^가-힣A-Za-z·\s]", "", h)) if len(k) >= 2]
        return ks + [a for a, to in ALIAS.items() if to in ks]
    add, lost, off = [], [], []
    for it in items:
        if it["log"] in have:
            continue
        ti = it["title"]
        if OFFTOPIC.search(ti):   # 주제 밖(라면·김 등) — 메인에 넣지 않음. 규칙: 비공개 권장으로만 표시
            off.append({"제목": ti[:50], "주소": it["url"]}); continue
        sec = next((h for h in heads if any(k in ti for k in keys(h))), None)
        cat = "📅 일정" if re.search(r"일정|\d+박\s*\d+일", ti) else "🚗 운전·팁" if re.search(r"렌트|렌터카|운전|주차|교통|그랩|톨", ti) else "📍"
        add.append({"구역": sec or "분류 못 함(나라 구역을 못 찾음)", "줄": f"{cat} {ti}", "주소": it["url"]})
    rss_logs = {it["log"] for it in items}
    if len(items) >= 10:
        lost = sorted(have - rss_logs)
    m = re.search(r"여행 이야기 (\d+)편", t)
    count_note = ""
    total = len(have) + len([a for a in add if not a["구역"].startswith("분류 못 함")])
    if m and int(m.group(1)) != total:
        count_note = f"'여행 이야기 {m.group(1)}편' → {total}편 (추가분 반영 시)"
    out = os.path.join(B, "메인", "메인글_목록_제안.md")
    if write and (add or lost or count_note):
        L = [f"# 메인 글 목록 제안 ({datetime.date.today()}) — 검문소 B9. 원본 메인글_완성본.md 은 바꾸지 않았음", ""]
        for sec in dict.fromkeys(a["구역"] for a in add):
            L += [f"## {sec} 에 추가", ""] + [x for a in add if a["구역"] == sec for x in (a["줄"], a["주소"])] + [""]
        if count_note: L += ["## 숫자 줄", count_note, ""]
        if lost: L += ["## 글 목록(RSS 최근 50편)에 안 보이는 메인 링크 — 삭제·비공개됐는지 확인", *[f"https://blog.naver.com/mose_love/{x}" for x in lost], ""]
        open(out, "w", encoding="utf-8").write("\n".join(L))
    return {"메인 링크 수": len(have), "추가 제안": add, "글 목록에 안 보이는 메인 링크": lost, "숫자 줄": count_note, "주제 밖 글(메인 제외·비공개 권장)": off,
            "제안 파일": nfc(os.path.basename(out)) if (write and (add or lost or count_note)) else ""}


def ops(items=None, write=True):
    items = items if items is not None else rss_items()
    r = {"at": datetime.datetime.now().strftime("%F %T"), "B6 발행 감지": detect(items), "B7 다음 2편": next2(items), "B9 메인 목록": mainlist(items, write)}
    if not write:
        return r
    try:
        os.makedirs(STATE, exist_ok=True)
        json.dump(r, open(os.path.join(STATE, "운영점검.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass
    return r


if __name__ == "__main__":
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    bad = 0
    if "--운영" in sys.argv:
        r = ops()
        if "--json" in sys.argv:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        else:
            d, n, m = r["B6 발행 감지"], r["B7 다음 2편"], r["B9 메인 목록"]
            print(f"운영 점검 {r['at']} · 글 목록 {d['글 목록 수']}편")
            print(f"  B6 발행 감지: 계획표 갱신 제안 {len(d['계획표 갱신 제안'])} · 채울 링크 {len(d['채울 링크'])} · 계획표·메인에 없는 글 {len(d['계획표·메인에 없는 글'])}")
            for x in d["계획표 갱신 제안"]: print(f"     {x['번호']} {x['제목']} ⇒ {x['제안']}")
            for x in d["채울 링크"][:6]: print(f"     {x['파일']}:{x['줄']} ⇒ {x['채울 주소']}")
            for x in d["계획표·메인에 없는 글"][:6]: print(f"     ({x['비고']}) {x['날짜']} {x['제목']}")
            print(f"  B7 이번 주 2편: {n['이번 주 2편']}")
            print(f"     다음 후보: {n['새 글 다음 후보']} / {n['수정 다음 후보']} / 재료 {n['재료 폴더(오래된 순)']}")
            print(f"  B9 메인 목록: 메인 링크 {m['메인 링크 수']} · 추가 제안 {len(m['추가 제안'])} · 안 보이는 링크 {len(m['글 목록에 안 보이는 메인 링크'])} {m['숫자 줄']} {m['제안 파일']}")
            for x in m["추가 제안"][:8]: print(f"     [{x['구역'][:18]}] {x['줄'][:60]}")
            if m["주제 밖 글(메인 제외·비공개 권장)"]: print(f"     주제 밖 {len(m['주제 밖 글(메인 제외·비공개 권장)'])}편은 메인에 넣지 않음(비공개 권장)")
    for p in paths:
        r = check(p)
        try:
            os.makedirs(STATE, exist_ok=True)
            json.dump(r, open(os.path.join(STATE, "검문소_" + re.sub(r"\.md$", "", r["파일"]) + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception:
            pass
        if "--json" in sys.argv:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        else:
            print(f"검문소 {r['검문소']} · {r['파일']} · 걸림 {r['걸림']} · 주의 {r['주의']} · 참고 {r['참고']}")
            for x in r["항목"]:
                if x["판정"] in ("걸림", "주의", "참고"):
                    print(f"  [{x['판정']}] {x['코드']} {x['항목']}: {x['내용']} {x['위치'] if x['위치'] else ''}")
        bad += bool(r["걸림"])
    sys.exit(1 if bad else 0)
