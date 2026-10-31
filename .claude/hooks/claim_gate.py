#!/usr/bin/env python3
"""Stop 훅 — 증거 없는 '정상/완료/확인' 보고를 막는다 (2026-10-31 제재 정책).

이번 턴(마지막 사용자 메시지 이후) 응답에 완료·정상 주장이 있으면 세 가지를 요구한다:
  1) 이번 턴에 실제 도구 실행이 1회 이상 있었다
  2) '근거:' 또는 '검증:' 줄이 있다 (출력·파일·종료코드 등)
  3) '미확인' / '확인 못 함' 진술이 있다 (없으면 '미확인: 없음'이라고 쓴다)
어기면 exit 2 + 이유(stderr) → 모델이 보고를 고쳐 다시 써야 끝난다.
무한 반복 방지: 같은 세션에서 연속 3회 막으면 통과시키고 로그에 남긴다.
"""
import json, os, re, sys, time
from pathlib import Path

CLAIM = re.compile(r"정상|완료|확인(했|함|됨|완료)|통과|성공|문제\s*없|해결(됐|했|함)"
                   r"|\b(verified|confirmed|works|working|done|fixed|resolved|succeeded|successful(ly)?|complete[ds]?|pass(es|ed)?)\b|all good|no (issues|problems)", re.I)
EVID = re.compile(r"(근거|검증|evidence)\s*[:：]|^\s*[-*]?\s*\**(근거|검증)\**", re.I | re.M)
UNVER = re.compile(r"미확인|확인\s*못|확인\s*불가|확인하지\s*않|unverified|unconfirmed|not (verified|confirmed|checked)|(could|can)(n't|not) (verify|confirm|check)", re.I)
LOG = Path.home() / ".claude" / "claim_gate.log"
MAX_BLOCKS = 3

def turn(transcript):
    rows = [json.loads(l) for l in open(transcript, encoding="utf-8") if l.strip()]
    start = 0
    for i, r in enumerate(rows):
        if r.get("type") == "user":
            c = r.get("message", {}).get("content")
            if isinstance(c, str) or (isinstance(c, list) and any(b.get("type") == "text" for b in c)):
                start = i
    text, tools = [], 0
    for r in rows[start + 1:]:
        if r.get("type") != "assistant":
            continue
        for b in r.get("message", {}).get("content", []) or []:
            if b.get("type") == "text":
                text.append(b["text"])
            elif b.get("type") == "tool_use":
                tools += 1
    return "\n".join(text), tools

def main():
    data = json.load(sys.stdin)
    tp = data.get("transcript_path")
    if not tp or not os.path.isfile(tp):
        return 0
    text, tools = turn(tp)
    if not CLAIM.search(text):
        return 0
    why = []
    if tools == 0:
        why.append("이번 턴에 도구 실행이 0회인데 정상/완료를 주장함 — 실행 후 보고할 것")
    if not EVID.search(text):
        why.append("'근거:' 또는 '검증:' 줄 없음 — 명령 출력·파일·종료코드를 적을 것")
    if not UNVER.search(text):
        why.append("미확인 범위 진술 없음 — 확인 못 한 것을 적거나 '미확인: 없음'이라고 쓸 것")
    if not why:
        return 0
    sid = data.get("session_id", "x")
    cnt_f = Path("/tmp") / f"claim_gate_{sid}.cnt"
    n = int(cnt_f.read_text()) + 1 if cnt_f.exists() and data.get("stop_hook_active") else 1
    cnt_f.write_text(str(n))
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": time.strftime("%F %T"), "session": sid, "n": n, "why": why}, ensure_ascii=False) + "\n")
    if n > MAX_BLOCKS:
        return 0
    print("[claim_gate] 증거 없는 완료 보고 차단:\n- " + "\n- ".join(why), file=sys.stderr)
    return 2

if __name__ == "__main__":
    sys.exit(main())
