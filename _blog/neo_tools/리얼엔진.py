#!/usr/bin/env python3
"""리얼엔진 — 글이 사람 말투로 읽히는지 숫자로 재는 측정기 (달리는 이기사).

사용: python3 리얼엔진.py <완성본.md> [더 많은 글…] [--json] [--고침] [--bench] [--nocache]
      python3 리얼엔진.py --가르침 '삽니다=살아요'   (헷갈린 말을 학습 사전에 영구 저장)
- (v1.1 나노연산 탑재) 말투측정을 따로 띄우지 않고 같은 프로그램 안에서 계산, 정규식 미리 준비,
  같은 글(내용·엔진 버전 같음)은 저장된 결과를 즉시 반환(.cache), 여러 편을 한 번에.
- --고침: 나노연산.py 로 합니다체→해요체·이에요/예요 문법만 자동 교정한 사본 <이름>_리얼고침.md 를 만들고 다시 잰다
  (원본은 절대 안 바꿈. 숫자·영문 이름·서식이 바뀌는 줄은 고치지 않음. 사실·내용은 그대로).
- 완성본의 '본문' 섹션만 잰다(발행키트_생성.py 와 같은 ===== 머리줄 형식).
- 결과: 지표별 값 · 기준 · 판정(OK/주의/걸림) · 걸린 문장 위치. 걸림이 하나라도 있으면 종료코드 1.
- 기준값(THRESH)은 연구/연구3_사람말투.md 결과로 조정한다. 지금 값은 임시(v0).
"""
import hashlib, importlib.util, json, os, re, statistics, sys, time

VERSION = "1.2 나노연산+학습기억 (말투사전 v2 · 연구3 기준)"
HERE = os.path.dirname(os.path.abspath(__file__))
THRESH = {
    "문장길이_변동계수_최소": 0.45,   # 사람 글은 짧은 문장·긴 문장이 섞임(표준편차/평균)
    "같은어미_연속_최대": 3,          # 같은 어미로 끝나는 문장이 연달아 몇 개까지
    "최다어미_비율_최대": 0.45,       # 한 가지 어미가 전체 문장에서 차지하는 비율
    "문단길이_변동계수_최소": 0.30,   # 문단 문장 수가 모두 똑같으면 기계적
    "연결어_밀도_최대": 0.18,         # '또한·뿐만 아니라·더불어·특히·게다가' 문장 비율
    "셋나열_최대": 2,                 # 'A, B, 그리고 C' 식 3개 나열 문장 수
    "문단요약문_최대": 1,             # '이처럼·결론적으로·요약하면·즉,' 로 시작하는 문장
    "합니다체_비율_최대": 0.10,       # 말투사전 v2: 10% 이하(사람 글 중앙값 3.5%)
    "금지표현_최대": 0,
    "문장끝이모지_1000자당_최대": 1.5,  # 귀여운 모드: 풍경·음식·동행 줄 끝만
}
BANNED = ["완벽 가이드", "총정리", "완벽 정복", "완벽한", "치트키", "낱낱이", "압도적", "인생샷", "성지", "꿀팁",
          "필수 코스", "필수템", "화룡점정", "클라이맥스", "정점", "황금 루트", "특별한 경험", "마법 같은", "그 자체",
          "놓치지 마세요", "만끽", "선사", "끝판왕", "200%", "대공개", "이것만 알면", "알아보겠습니다", "계획 중이신 분들이라면"]
CONNECT = ["또한", "뿐만 아니라", "더불어", "게다가", "아울러", "나아가", "특히나"]
SUMMARY = ["이처럼", "결론적으로", "요약하면", "즉,", "정리하자면", "이렇듯"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
_SKIPNUM = re.compile(r"^\d\.\s")
_MARK = re.compile(r"\*\*|\{파랑:\s*|\}")
_URL = re.compile(r"https?://\S+")
_SPLIT = re.compile(r"(?<=[.?!요다])\s+(?=\S)")
_TAILP = re.compile(r"[.!?~\s]+$")
_THREE = re.compile(r"[^,]+, [^,]+,? (그리고|및) ")
_MT_LINE = re.compile(r"\[(OK|고침)\] (.+?): ([\d.]+)\s+\(목표 (.+)\)")


def body_of(text):
    text = text.replace("\r\n", "\n")
    heads = list(re.finditer(r"^={5,}\n([^\n=][^\n]*)\n={5,}$", text, re.M))
    for i, m in enumerate(heads):
        if m.group(1).strip().startswith("본문"):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            return text[m.end():end]
    return text


def clean_lines(body):
    out = []
    for l in body.splitlines():
        s = l.strip()
        if not s or s.startswith(("【그림", "■", "▶", "👉", "←", "다음 편", "http")) or _SKIPNUM.match(s):
            out.append("")  # 문단 경계로 취급
            continue
        s = _MARK.sub("", s)
        s = _URL.sub("", s)
        out.append(s)
    return out


def sentences(lines):
    paras, cur = [], []
    for l in lines:
        if not l:
            if cur: paras.append(cur); cur = []
            continue
        for s in _SPLIT.split(l):
            s = s.strip()
            if len(s) >= 4: cur.append(s)
    if cur: paras.append(cur)
    return paras


def ending(s):
    s = _TAILP.sub("", s)
    s = EMOJI.sub("", s).strip()
    for e in ["더라고요", "더라구요", "었어요", "았어요", "했어요", "였어요", "이에요", "예요", "해요", "돼요", "세요",
              "어요", "아요", "습니다", "합니다", "니다", "죠", "네요", "군요", "까요", "거든요", "잖아요", "요", "다"]:
        if s.endswith(e): return e
    return s[-2:]


def cv(xs):
    return (statistics.pstdev(xs) / statistics.mean(xs)) if len(xs) > 1 and statistics.mean(xs) else 0.0


def judge(name, val, lo=None, hi=None):
    if lo is not None:
        st = "OK" if val >= lo else ("주의" if val >= lo * 0.8 else "걸림")
        return {"지표": name, "값": round(val, 3), "기준": f">= {lo}", "판정": st}
    st = "OK" if val <= hi else ("주의" if val <= hi * 1.3 and hi > 0 else "걸림")
    return {"지표": name, "값": round(val, 3), "기준": f"<= {hi}", "판정": st}


_MT = None


def _malt():
    """말투측정.py 를 한 번만 불러 같은 프로그램 안에서 씀(예전: 글마다 파이썬을 새로 띄움)."""
    global _MT
    if _MT is None:
        f = os.path.join(HERE, "말투측정.py")
        if not os.path.exists(f):
            _MT = False
        else:
            spec = importlib.util.spec_from_file_location("malt", f)
            _MT = importlib.util.module_from_spec(spec); spec.loader.exec_module(_MT)
    return _MT


def _malt_lines(path):
    m = _malt()
    if not m:
        return []
    try:
        meta, body = m.load_plain(path) if path.endswith((".plain", ".txt")) else m.load_sample(path)
        r = m.analyze(meta, body)
    except Exception:
        return []  # 예전과 같음: 말투측정이 못 읽는 형식이면 2층 생략
    out = []
    for k, (lo, hi, desc) in m.TARGET.items():
        v = r[k]; ok = "OK" if lo <= v <= hi else "고침"
        out.append(f"[{ok:2}] {desc}: {v}  (목표 {lo}~{hi})")
    return out


CACHE = os.path.join(HERE, ".cache", "리얼엔진.json")


def _sig(path):
    h = hashlib.sha256(open(path, "rb").read())
    for f in (__file__, os.path.join(HERE, "말투측정.py")):
        if os.path.exists(f): h.update(open(f, "rb").read())
    return h.hexdigest()


def run_cached(path, use_cache=True):
    db = {}
    if use_cache:
        try: db = json.load(open(CACHE, encoding="utf-8"))
        except Exception: db = {}
    k = _sig(path)
    if k in db:
        r = db[k]; r["파일"] = path; r["저장된 결과"] = True
        return r
    r = run(path)
    if use_cache and "오류" not in r:
        try:
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            db[k] = r
            if len(db) > 300: db = dict(list(db.items())[-300:])
            json.dump(db, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass
    return r


def run(path):
    raw = open(path, encoding="utf-8").read()
    body = body_of(raw)
    paras = sentences(clean_lines(body))
    sents = [s for p in paras for s in p]
    if not sents:
        return {"오류": "본문 문장을 찾지 못함"}
    lens = [len(s) for s in sents]
    ends = [ending(s) for s in sents]
    # 같은 어미 연속
    run_max, run_cur, where = 1, 1, ""
    for i in range(1, len(ends)):
        run_cur = run_cur + 1 if ends[i] == ends[i - 1] else 1
        if run_cur > run_max: run_max, where = run_cur, sents[i][:30]
    top_end = max(dict.fromkeys(ends), key=ends.count)  # (v1.1) 동점이면 먼저 나온 어미 — 실행마다 바뀌던 무작위 순서 고정
    res = [
        judge("문장 길이 변동계수", cv(lens), lo=THRESH["문장길이_변동계수_최소"]),
        judge(f"같은 어미 연속(최대, '{where}…')", run_max, hi=THRESH["같은어미_연속_최대"]),
        judge(f"가장 많은 어미 비율('{top_end}')", ends.count(top_end) / len(ends), hi=THRESH["최다어미_비율_최대"]),
        judge("문단 길이 변동계수", cv([len(p) for p in paras]), lo=THRESH["문단길이_변동계수_최소"]),
        judge("연결어 밀도", sum(any(c in s for c in CONNECT) for s in sents) / len(sents), hi=THRESH["연결어_밀도_최대"]),
        judge("셋 나열 문장 수", sum(bool(_THREE.search(s)) for s in sents), hi=THRESH["셋나열_최대"]),
        judge("요약 시작 문장 수", sum(s.startswith(tuple(SUMMARY)) for s in sents), hi=THRESH["문단요약문_최대"]),
    ]
    formal = sum(e in ("습니다", "합니다", "니다") for e in ends) / len(ends)
    res.append(judge("합니다체 비율", formal, hi=THRESH["합니다체_비율_최대"]))
    banned = [b for b in BANNED if b in body]
    res.append({"지표": "금지 표현", "값": len(banned), "기준": "0", "판정": "OK" if not banned else "걸림", "목록": banned})
    emo_end = [s[:30] for s in sents if EMOJI.search(s[-3:]) and not s.startswith("👉")]
    per_k = len(emo_end) / max(1, sum(lens)) * 1000
    res.append({"지표": "문장 끝 이모지 /1000자(귀여운 모드)", "값": round(per_k, 2), "기준": "<= 1.5", "판정": "OK" if per_k <= 1.5 else "걸림", "목록": emo_end[:5]})
    # 2층: 말투측정.py(말투사전 v2 수치) — [고침] 중 재료·규칙 때문에 못 맞추는 항목(숫자·감정)은 '주의', 나머지는 '걸림'
    if True:
        for line in _malt_lines(path):
            m = _MT_LINE.match(line.strip())
            if not m: continue
            ok, name, val, goal = m.groups()
            soft = ("숫자" in name) or ("감정" in name)
            res.append({"지표": "v2 " + name, "값": float(val), "기준": goal, "판정": "OK" if ok == "OK" else ("주의" if soft else "걸림")})
    summary = {
        "파일": path, "엔진": VERSION, "문장 수": len(sents), "문단 수": len(paras),
        "평균 문장 길이": round(statistics.mean(lens), 1), "어미 분포": {e: ends.count(e) for e in sorted(dict.fromkeys(ends), key=ends.count, reverse=True)[:6]},
        "지표": res, "걸림": sum(r["판정"] == "걸림" for r in res), "주의": sum(r["판정"] == "주의" for r in res),
    }
    return summary


def show(r):
    if "오류" in r:
        print(f"{r.get('파일', '')}: {r['오류']}"); return
    print(f"리얼엔진 {r['엔진']} · 문장 {r['문장 수']} · 문단 {r['문단 수']} · 평균 {r['평균 문장 길이']}자" + (" · (저장된 결과)" if r.get("저장된 결과") else ""))
    print("어미 분포:", r["어미 분포"])
    for x in r["지표"]:
        extra = f"  {x['목록']}" if x.get("목록") else ""
        print(f"  [{x['판정']}] {x['지표']}: {x['값']} (기준 {x['기준']}){extra}")
    print(f"결과: 걸림 {r['걸림']} · 주의 {r['주의']}")


def fix(path):
    import importlib.util as iu
    spec = iu.spec_from_file_location("nano", os.path.join(HERE, "나노연산.py"))
    nano = iu.module_from_spec(spec); spec.loader.exec_module(nano)
    text = open(path, encoding="utf-8").read()
    out = re.sub(r"\.md$", "", path) + "_리얼고침.md"
    # 반복 고침: 고친 뒤 다시 재고, 권유가 아직 기준을 넘으면 한 단계 더(최대 6회)
    lim = 1.2
    for _ in range(6):
        new, log = nano.auto_fix(text, urge_max_per_k=lim)
        open(out, "w", encoding="utf-8").write(new)
        r = run(out)
        over = [x for x in r.get("지표", []) if "권유" in x["지표"] and x["판정"] != "OK"]
        if not over:
            break
        lim -= 0.2
    ch = [x for v in log.values() for x in v]
    if not ch and os.path.exists(out):
        os.remove(out)  # 고칠 것 없으면 사본 안 남김(방금 만든 임시 사본)
    print(f"[고침] {len(ch)}곳 교정" + (f" → {out}" if ch else " (고칠 것 없음)") + " · " + ", ".join(f"{k} {len(v)}" for k, v in log.items() if v))
    for k, v in log.items():
        for n, a, b in v[:4]:
            print(f"  ({k}) {n}행: {a.strip()[:56]}\n     → {b.strip()[:56]}")
    left = [b for b in BANNED if b in new]
    if left:
        print(f"[그대로 둠] 기존 글 제목·인용(「」·따옴표·이모지 목록 줄) 안 금지 표현 {len(left)}종 — 발행된 제목이라 안 바꿈: {left[:6]}")
    if nano.LEX_FIXES:
        print(f"[학습 어휘로 바로잡음] {nano.LEX_FIXES}")
    todo = nano.flush_unknown()
    if todo:
        print(f"[배울 거리] 헷갈려서 안 바꾼 말 {len(todo)}개: {list(todo)[:10]}  → 가르치기: python3 리얼엔진.py --가르침 '삽니다=살아요'")
    return out if ch else None


if __name__ == "__main__":
    if "--가르침" in sys.argv:  # 2층 학습 사전에 영구 저장
        import importlib.util as iu
        sp = iu.spec_from_file_location("nano", os.path.join(HERE, "나노연산.py")); nano = iu.module_from_spec(sp); sp.loader.exec_module(nano)
        for kv in sys.argv[sys.argv.index("--가르침") + 1:]:
            w, a = kv.split("=", 1); nano.teach(w.strip(), a.strip()); print(f"[학습] {w.strip()} → {a.strip()} (학습사전.json)")
        sys.exit(0)
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_cache = "--nocache" not in sys.argv and "--bench" not in sys.argv
    if "--bench" in sys.argv:
        for p in paths:
            run(p); n = 200; t = time.perf_counter()
            for _ in range(n): run(p)
            per = (time.perf_counter() - t) / n
            print(f"{os.path.basename(p)}: 1편 {per * 1000:.2f}ms (= {per * 1e6:.0f}µs, {n}회 평균, 저장 결과 미사용)")
        sys.exit(0)
    bad = 0
    for p in paths:
        if "--고침" in sys.argv:
            q = fix(p)
            if q: p = q
        r = run_cached(p, use_cache)
        if "--json" in sys.argv:
            print(json.dumps(r, ensure_ascii=False, indent=1))
        else:
            if len(paths) > 1: print("==", p)
            show(r)
        bad += bool(r.get("걸림")) or "오류" in r
    if len(paths) == 1 and "오류" in r and "--json" not in sys.argv:
        sys.exit(r["오류"])
    sys.exit(1 if bad else 0)
