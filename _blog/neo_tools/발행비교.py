"""발행본 비교 학습 — 내 완성본 vs 사장님이 실제로 발행한 글 (사용자 10-01 "언제 키우냐").

사장님이 발행 전에 고친 곳 = 가장 좋은 정답. 그걸 모아 리얼엔진 자동 고침에 반영한다.
 1) 짝짓기: B/초안/*_완성본*.md 의 제목 ↔ 블로그 RSS 제목(비슷함 ≥ 0.55, 발행일 ≥ 초안 날짜).
           수정안은 초안 속 '원래 글 주소 …/mose_love/<번호>' 로 바로 짝.
 2) 비교: 문장 단위 맞추기(difflib) → 바뀐 문장 쌍은 어절 단위로 '전→후' 조각(4어절 이하)을 뽑고, 지운·더한 문장 수를 센다.
          발행본이 초안과 거의 다르면(비슷함 < 0.3) '아직 교체 전'으로 보고 건너뜀.
 3) 승격: 같은 '전→후' 가 서로 다른 글 2편 이상에서 나오면 학습_말투선호.json 에 올림 → 나노연산.auto_fix 가 '사장님 말투' 로 적용.
같은 글·같은 발행 내용은 한 번만 센다. 블로그 읽기는 공개 글 읽기만(로그인·쓰기 없음).
"""
import difflib, hashlib, html, json, os, re, unicodedata, urllib.request
from email.utils import parsedate_to_datetime

HERE = os.path.dirname(os.path.abspath(__file__))
B = os.path.dirname(HERE)
STATE = os.path.join(HERE, "학습_발행차이.json")
PREF = os.path.join(HERE, "학습_말투선호.json")
PROMOTE_POSTS = 2

_MARK = re.compile(r"\*\*|\{(?:파랑|강조):\s*|\}")
_SENT = re.compile(r"(?<=[.?!요다])\s+")


def nfc(s):
    return unicodedata.normalize("NFC", s)


def _load(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d


# ---------- 초안 ----------
def _section(text, name):
    m = re.search(r"^={5,}\n" + name + r"[^\n]*\n={5,}\n(.*?)(?=^={5,}\n|\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def drafts():
    d = os.path.join(B, "초안")
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        f = nfc(f)
        if not f.endswith(".md") or "완성본" not in f or "_리얼고침" in f:
            continue
        p = os.path.join(d, f)
        try:
            t = nfc(open(p, encoding="utf-8").read())
        except Exception:
            continue
        title = _section(t, "제목").split("\n")[0].strip()
        body = _section(t, "본문") or t
        m = re.search(r"원래 글 주소[^\n]*?mose_love/(\d{9,})", t)
        date = (re.match(r"(\d{4}-\d{2}-\d{2})", f) or [None, ""])[1]
        yield {"file": f, "title": title, "body": body, "orig": m.group(1) if m else None, "date": date}


def clean_sents(text):
    out = []
    for l in text.split("\n"):
        s = l.strip()
        if not s or s.startswith(("【그림", "http", "#", "=====", "[")):
            continue
        s = _MARK.sub("", s).lstrip("■▶👉> ").strip()
        out += [x.strip() for x in _SENT.split(s) if len(x.strip()) >= 4]
    return out


# ---------- 블로그 ----------
def rss_items(rss_text):
    for it in re.findall(r"<item>(.*?)</item>", rss_text, re.S):
        g = lambda tag: re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(rf"<{tag}>(.*?)</{tag}>", it, re.S) or [None, ""])[1]).strip()
        m = re.search(r"mose_love/(\d+)", g("link"))
        if m:
            try:
                dt = parsedate_to_datetime(g("pubDate")).strftime("%Y-%m-%d")
            except Exception:
                dt = ""
            yield {"log": m.group(1), "title": nfc(html.unescape(g("title"))), "date": dt}


def fetch_post(log, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)
    url = f"https://m.blog.naver.com/PostView.naver?blogId=mose_love&logNo={log}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    t = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    paras = re.findall(r'<p class="se-text-paragraph[^"]*"[^>]*>(.*?)</p>', t, re.S)
    txt = [nfc(html.unescape(re.sub(r"<[^>]+>", "", p))).replace("​", "").strip() for p in paras]
    return "\n".join(x for x in txt if x)


def _norm_title(t):
    return re.sub(r"[\[\]【】()①②③④⑤\s:,!'\"·\-]", "", t)


def match(drs, items):
    for d in drs:
        if d["orig"]:
            yield d, d["orig"]; continue
        best, score = None, 0.0
        for it in items:
            if d["date"] and it["date"] and it["date"] < d["date"]:
                continue
            r = difflib.SequenceMatcher(None, _norm_title(d["title"]), _norm_title(it["title"])).ratio()
            if r > score:
                best, score = it, r
        if best and score >= 0.55:
            yield d, best["log"]


# ---------- 비교 ----------
def compare(draft_body, published):
    a, b = clean_sents(draft_body), clean_sents(published)
    sim = difflib.SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    res = {"비슷함": round(sim, 3), "쌍": [], "지운": [], "더한": 0}
    if sim < 0.3:
        return res
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "delete":
            res["지운"] += a[i1:i2]
        elif op == "insert":
            res["더한"] += j2 - j1
        elif op == "replace":
            used = set()
            for s in a[i1:i2]:
                cands = [(difflib.SequenceMatcher(None, s, t).ratio(), k, t) for k, t in enumerate(b[j1:j2]) if k not in used]
                if not cands:
                    res["지운"].append(s); continue
                r, k, t = max(cands)
                if r < 0.5:
                    res["지운"].append(s); continue
                used.add(k)
                wa, wb = s.split(), t.split()
                for op2, x1, x2, y1, y2 in difflib.SequenceMatcher(None, wa, wb).get_opcodes():
                    if op2 == "replace" and x2 - x1 <= 4 and y2 - y1 <= 4:
                        pa, pb = " ".join(wa[x1:x2]), " ".join(wb[y1:y2])
                        if re.sub(r"\D", "", pa) == re.sub(r"\D", "", pb):  # 숫자 바뀐 건 사실 수정 → 말투 아님
                            res["쌍"].append([pa.rstrip(".,!?"), pb.rstrip(".,!?")])
            res["더한"] += max(0, (j2 - j1) - len(used))
    return res


def learn(pairs_by_post, state=None):
    """pairs_by_post: {글id: compare 결과}. 상태에 더하고 승격 목록을 돌려줌."""
    st = state if state is not None else _load(STATE, {"쌍": {}, "처리": {}, "지운문장": 0, "더한문장": 0})
    for pid, r in pairs_by_post.items():
        if pid in st["처리"]:
            continue
        st["처리"][pid] = {"비슷함": r["비슷함"], "쌍": len(r["쌍"]), "지운": len(r["지운"]), "더한": r["더한"]}
        st["지운문장"] += len(r["지운"]); st["더한문장"] += r["더한"]
        for pa, pb in {tuple(x) for x in r["쌍"]}:
            e = st["쌍"].setdefault(f"{pa}→{pb}", {"전": pa, "후": pb, "글": []})
            if pid not in e["글"]:
                e["글"].append(pid)
    pref = {e["전"]: e["후"] for e in st["쌍"].values() if len(e["글"]) >= PROMOTE_POSTS}
    return st, pref


def run(rss_text, cache_dir, save=True):
    """무한 학습 고리에서 부름. 돌려줌: 요약 dict."""
    items = list(rss_items(rss_text))
    found = {}
    st = _load(STATE, {"쌍": {}, "처리": {}, "지운문장": 0, "더한문장": 0})
    for d, log in match(list(drafts()), items):
        try:
            pub = fetch_post(log, cache_dir)
        except Exception as e:
            continue
        pid = f"{log}:{hashlib.sha256(pub.encode()).hexdigest()[:12]}"
        if pid in st["처리"]:
            continue
        r = compare(d["body"], pub)
        if r["비슷함"] < 0.3:
            continue  # 아직 내 글로 교체 전
        found[pid] = r
    st, pref = learn(found, st)
    if save:
        json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        json.dump(pref, open(PREF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {"짝지은 글": len(found), "누적 처리": len(st["처리"]), "말투 선호": len(pref), "새 선호": pref}
