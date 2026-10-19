#!/usr/bin/env python3
"""말투 뽑기 v2 — 글마다 말투·글 모양을 따로따로 뽑아 섞는다.
사장님 10-14 "말투도 여러 개 두고 섞어서 랜덤으로" · "일정한 패턴을 주지 말고" · "진중해졌다가 장난기 있게 했다가".

사용: python3 말투뽑기.py <완성본 이름> [--다시]
  → 상태/말투배정.json 에 이 글의 뽑기 결과를 적고, 쓰는 사람(블로그 담당)에게 보여 준다.
v1(결 4개 중 하나)도 결국 틀 4개라서, v2 는 글을 여러 칸으로 나눠 칸마다 따로 뽑는다:
  말투 결 · 첫머리 · 소제목 모양 · 문단 호흡 · 내 이야기 자리 · 마무리 · 숫자 두는 곳 · 문장 길이 목표.
  최근 5편과 같은 조합은 다시 뽑고, 칸마다 바로 앞 글과 같은 값은 피한다.
  문장 길이·조각 문장 목표도 글마다 범위 안에서 흔든다(모든 글이 같은 수치에 맞춰지지 않게).
고정은 규칙서 필수만: 내돈내산 둘째 줄 · AI 고지 · 태그 · 이전/다음 편. 사실은 재료로만(말투사전 ⑤).
"""
import datetime, json, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(os.path.dirname(HERE), "상태")
OUT = os.path.join(STATE, "말투배정.json")

SLOTS = {
    "말투 결": ["수다(친구한테 말하듯, 근데·일단·괄호 보충)", "담백(운행 노트처럼 짧게, 꾸밈말 적게)",
              "일기(그날 순서대로, 과거형)", "문답(독자가 물을 말로 풀기)", "섞음(소제목마다 결을 바꿔도 됨)"],
    "첫머리": ["답부터 한 줄(가격·시간·결론)", "그날 한 장면부터(재료에 있는 것)", "실수·헷갈린 것부터",
             "독자 질문 한 줄로 시작", "앞 편 이어서 한 줄"],
    "소제목 모양": ["말로 묻기('언제 풀리냐면요')", "짧은 명사('주차')", "시간·장소('오후, 남쪽 주차장')",
                "섞기(세 가지를 섞어서)", "숫자 하나 넣기('딱 10디르함')"],
    "문단 호흡": ["짧은 문단 많이(1~2줄 위주, 가끔 4줄)", "보통(2~3줄, 한 번은 5줄)", "들쭉날쭉(1줄 문단과 4~5줄 문단 섞기)"],
    "내 이야기 자리": ["소제목마다 한 줄", "글 가운데 한 덩어리로", "처음과 끝에만", "실수 대목에 몰아서"],
    "마무리": ["다음 편 예고로 끝", "아쉬운 점 하나로 끝", "독자에게 한 가지 권하고 끝", "짧은 한 줄 소감으로 끝(재료에 있을 때)"],
    "숫자 두는 곳": ["본문엔 하나만, 나머지 ▶ 줄", "정보 카드 그림으로 몰기", "표 하나로 몰기", "FAQ 답에 나누기"],
}
MOODS = {"진중": "차분하게, 농담 없이, 정확히", "장난": "가볍게 한마디·자기 농담·ㅎㅎ 하나 정도", "보통": "평소 이기사 말투"}
SERIOUS_ONLY = "운전·벌금·보증금·안전·예약 절차·출처 줄은 늘 진중(장난 칸이어도 그 줄은 진중으로)"


def mood_flow(rng, n=None):
    """소제목마다 분위기 흐름: 진중↔장난이 적어도 한 번씩 오가게, 같은 분위기 3번 연속은 없게."""
    n = n or rng.randint(4, 6)
    for _ in range(100):
        f = [rng.choice(list(MOODS)) for _ in range(n)]
        ok3 = all(not (f[i] == f[i + 1] == f[i + 2]) for i in range(n - 2))
        if "진중" in f and "장난" in f and ok3 and any(
                {f[i], f[i + 1]} == {"진중", "장난"} or (f[i] != f[i + 1]) for i in range(n - 1)):
            return f
    return ["진중", "장난", "보통", "진중", "장난"][:n]


RANGE = {"짧은 문장 %": (14, 28), "긴 문장 %": (8, 24), "조각 문장 %": (12, 30), "귀여운 장치 %": (0, 25)}
INFO_WORDS = ("법규", "벌금", "예약", "보증금", "주차", "톨", "비용", "쓴돈", "가이드", "총정리")


def load():
    try:
        return json.load(open(OUT, encoding="utf-8"))
    except (OSError, ValueError):
        return {"_설명": "글마다 말투·글 모양 뽑기(말투뽑기.py). 사람이 고쳐도 됨.", "글": {}}


def pick(name, db, rng=random):
    prev = [v for k, v in db["글"].items() if k != name]
    last = prev[-1] if prev else {}
    recent = [tuple(v.get(s) for s in SLOTS) for v in prev[-5:]]
    info = any(k in name for k in INFO_WORDS)
    for _ in range(50):
        a = {}
        for s, opts in SLOTS.items():
            cand = [o for o in opts if o != last.get(s)] or opts
            if info and s == "말투 결":                       # 정보 글은 수다·일기를 덜 뽑음(막지는 않음)
                cand = cand + [o for o in cand if o.startswith(("담백", "문답"))]
            a[s] = rng.choice(cand)
        if tuple(a[s] for s in SLOTS) not in recent:
            break
    a["분위기 흐름(소제목 순서)"] = " → ".join(mood_flow(rng))
    a["분위기 규칙"] = SERIOUS_ONLY
    for k, (lo, hi) in RANGE.items():
        a[k] = rng.randint(lo, hi)
    if info:
        a["귀여운 장치 %"] = min(a["귀여운 장치 %"], 10)
    a["at"] = datetime.datetime.now().strftime("%F %T")
    return a


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    name = os.path.basename(argv[1])
    db = load()
    if name not in db["글"] or "--다시" in argv:
        db["글"].pop(name, None)
        db["글"][name] = pick(name, db)
        os.makedirs(STATE, exist_ok=True)
        json.dump(db, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    a = db["글"][name]
    print(name)
    for k, v in a.items():
        if k != "at":
            print(f"  {k}: {v}")
    print("  (뽑은 대로 쓰되, 재료에 없는 장면·감정은 만들지 않기. 어색하면 그 칸만 --다시 대신 손으로 바꿔도 됨)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
