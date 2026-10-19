"""문체 점검 — 검문소 B12~B14 (사장님 10-14).
 B12 이음말·같은 낱말 반복: "했고 했어서 그래서 같은 단어가 자주 나오면 읽기 불편"
 B13 문단 띄어쓰기: "문단 문단 띄어쓰기 적절히"
 B14 글 색상: "글색상도 중요함" — {파랑: } 강조가 제자리에 있는지
읽기만 한다. 결과는 검문소 item 모양 (코드·항목·판정·내용·위치)."""
import re

START = ["그래서", "근데", "그런데", "그리고", "그러니까", "일단", "사실", "대신", "또"]
ANYWHERE = ["그래서", "그리고", "그러니까", "근데", "그런데"]
LINK = [("~고", re.compile(r"(?:있|없|되|하|돼)고$")),
        ("~서", re.compile(r"(?:해|어|아|여|워|와|봐|있어|없어)서$")),
        ("~는데", re.compile(r"[가-힣](?:는|인|한|던|갔는|했는)데$"))]
JOSA = re.compile(r"(으로|에서|이랑|에는|까지|부터|은|는|이|가|을|를|에|엔|도|로|랑|만|의|와|과)$")
SKIP_WORDS = set("그래서 그리고 그러니까 근데 그런데 일단 사실 대신 제가 저는 저희 그날 지금 여기서 이건 이거 하나 따로 바로 미리 직접 정도 경우 있어요 돼요 해요 했어요 같아요".split())
BLUE = re.compile(r"\{파랑:\s*(.+?)\}")
SKIP_LINE = ("【", "▶", "http", "←", "#")
EMO = re.compile("[" + chr(0x1F300) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF) + "]")   # 이모지 목록 줄(드라이브 전송 때 글자가 안 바뀌게 chr 로)
LINK_WIN, WORD_WIN, WORD_N, START_MAX = 4, 4, 3, 2
MOBILE = 30   # 한 줄 글자 수(공백 빼고) — 휴대폰에서 두 줄로 꺾이기 시작
PARA_MAX = 5  # 한 문단 줄 수


def item(code, name, state, detail="", where=None):
    return {"코드": code, "항목": name, "판정": state, "내용": detail, "위치": where or []}


def _prose(lines):
    """[(줄번호, 글)] — 소제목·그림·링크·목록·FAQ 번호 줄은 뺌."""
    out = []
    for n, l in lines:
        s = BLUE.sub(r"\1", l.strip())
        if not s or s.startswith(SKIP_LINE) or EMO.match(s[:1]) or s.startswith("■") or re.match(r"^\d+\.\s", s):
            continue
        out.append((n, s))
    return out


def _past(w, tail):
    """'갔고·봤고·샀어서'처럼 앞 글자 받침이 ㅆ(지난 일)인지."""
    if not w.endswith(tail) or len(w) <= len(tail):
        return False
    c = ord(w[-len(tail) - 1]) - 0xAC00
    return 0 <= c < 11172 and c % 28 == 20


def _tags(s):
    t = []
    first = s.split()[0].rstrip(",") if s.split() else ""
    if first in START:
        t.append(first)
    for w in ANYWHERE:                       # 뜻이 하나뿐인 이음말은 줄 가운데 있어도 셈
        if w != first and re.search(r"(^|\s)" + w + r"[\s,]", s + " "):
            t.append(w)
    for tok in s.split():
        w = tok.rstrip(",.!?~)")
        for name, rx in LINK:
            if rx.search(w) or (name == "~고" and _past(w, "고")) or (name == "~서" and _past(w, "어서")):
                t.append(name)
    return t


def repeats(lines):
    pr = _prose(lines)
    near, seen, count = [], {}, {}
    for i, (n, s) in enumerate(pr):
        for t in dict.fromkeys(_tags(s)):          # 한 줄 안의 같은 이음말은 한 번만
            count[t] = count.get(t, 0) + 1
            j = seen.get(t)
            if j is not None and i - j < LINK_WIN:
                near.append((n, f"[{t}] {pr[j][1][:16]}… → {s[:16]}…"))
            seen[t] = i
    many = [f"'{w}' {c}번" for w, c in count.items() if w in START and c > START_MAX]
    words, done = [], set()
    for i in range(len(pr)):
        chunk = [s for _, s in pr[i:i + WORD_WIN]]
        toks = [JOSA.sub("", w) for s in chunk for w in re.findall(r"[가-힣]{2,}", s)]
        for w in set(toks):
            if len(w) >= 2 and w not in SKIP_WORDS and w not in done and toks.count(w) >= WORD_N:
                done.add(w)
                words.append((pr[i][0], f"'{w}' {WORD_WIN}줄 안에 {toks.count(w)}번"))
    res = [item("B12", "이음말 반복(~고·~서·~는데·그래서…)", "주의" if (near or many) else "OK",
                f"가까이 {len(near)}곳" + (" · 글 전체: " + ", ".join(many) if many else "") +
                (" — 한쪽을 다른 말로 바꾸거나 문장을 끊기" if near or many else ""), near[:6]),
           item("B12", "같은 낱말 몰림", "참고" if words else "OK",
                f"{len(words)}곳 — 두 번째부터는 '이거·여기'나 다른 말로" if words else "", words[:6])]
    return res


def paragraphs(lines):
    """빈 줄로 나뉜 문단 모양. lines = [(줄번호, 원문)] 본문 그대로(빈 줄 포함)."""
    paras, cur, gaps, run = [], [], [], 0
    no_gap_head = []
    prev_blank = True
    for n, l in lines:
        s = l.strip()
        if not s:
            run += 1
            if cur:
                paras.append(cur); cur = []
            prev_blank = True
            continue
        if run >= 3:
            gaps.append((n, f"빈 줄 {run}개 연속"))
        run = 0
        if s.startswith("■") and not prev_blank:
            no_gap_head.append((n, s[:20]))
        if s.startswith(("【", "■", "http", "←")) or EMO.match(s[:1]) or re.match(r"^\d+\.\s", s):
            if cur:
                paras.append(cur); cur = []
            prev_blank = False
            continue
        cur.append((n, s))
        prev_blank = False
    if cur:
        paras.append(cur)
    long_p = [(p[0][0], f"{len(p)}줄 문단: {p[0][1][:18]}…") for p in paras if len(p) > PARA_MAX]
    def plain_len(s):
        return len(re.sub(r"\s", "", BLUE.sub(r"\1", s)))
    wide = [(n, f"{plain_len(s)}자: {s[:18]}…") for p in paras for n, s in p if plain_len(s) > MOBILE and not s.startswith("▶")]
    sizes = [len(p) for p in paras]
    same = max((sizes.count(k) for k in set(sizes)), default=0) / max(1, len(sizes))
    res = [item("B13", "문단 길이(1~5줄)", "주의" if long_p else "OK", f"{len(long_p)}곳 — 중간에 빈 줄 하나" if long_p else "", long_p[:5]),
           item("B13", "문단 모양이 다 같음", "참고" if len(sizes) >= 6 and same >= 0.7 else "OK",
                f"문단 {len(sizes)}개 중 {round(same * 100)}%가 같은 줄 수 — 1줄짜리·4줄짜리를 섞기" if len(sizes) >= 6 and same >= 0.7 else
                f"문단 {len(sizes)}개, 줄 수 {sorted(set(sizes))}"),
           item("B13", f"한 줄 {MOBILE}자 넘음(휴대폰에서 꺾임)", "참고" if len(wide) > 3 else "OK", f"{len(wide)}줄", wide[:5]),
           item("B13", "소제목 앞 빈 줄 · 빈 줄 몰림", "주의" if (no_gap_head or gaps) else "OK", "", (no_gap_head + gaps)[:5])]
    return res


def colors(lines):
    blues = [(n, m.group(1)) for n, l in lines for m in BLUE.finditer(l)]
    heads = [(n, l.strip()[:20]) for n, l in lines if l.strip().startswith("■") and BLUE.search(l)]
    longb = [(n, b[:20]) for n, b in blues if len(b) > 20]
    adj = [(n, b[:16]) for (n, b), (m, _) in zip(blues[1:], blues) if n - m <= 1]
    # 소제목 구역마다 몇 개
    sec, per = 0, {}
    for n, l in lines:
        if l.strip().startswith("■"):
            sec += 1
        per[sec] = per.get(sec, 0) + len(BLUE.findall(l))
    crowd = [k for k, v in per.items() if v > 1]
    bad = heads or longb or adj or crowd
    state = "주의" if bad else ("참고" if not blues else "OK")
    detail = (f"파랑 {len(blues)}곳" + (" · 소제목에 색" if heads else "") + (" · 20자 넘는 색" if longb else "") +
              (" · 붙은 줄 둘 다 색" if adj else "") + (f" · 한 구역에 2곳 이상 {len(crowd)}구역" if crowd else "") +
              (" — 글 맨 앞 핵심 한 곳(답·가격)에 파랑 하나면 충분" if not blues else ""))
    return [item("B14", "글 색상(파랑 강조 자리)", state, detail, (heads + longb + adj)[:5])]


def check(body_text, line_offset=0):
    lines = [(i + 1 + line_offset, l) for i, l in enumerate(body_text.split("\n"))]
    return repeats(lines) + paragraphs(lines) + colors(lines)


if __name__ == "__main__":
    import sys
    for r in check(open(sys.argv[1], encoding="utf-8").read()):
        print(f"[{r['판정']}] {r['코드']} {r['항목']}: {r['내용']}")
        for w in r["위치"]:
            print("     ", w)
