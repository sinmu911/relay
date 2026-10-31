#!/usr/bin/env python3
"""Stop 훅 — 근거 없는/근거와 안 맞는 '정상·완료' 보고를 막는다 (2026-10-31 제재 정책).

이번 턴 응답에 완료·정상 주장이 있으면:
  1) 이번 턴에 실제 도구 실행이 있어야 한다
  2) '근거:' 줄이 있어야 하고, 그 줄에서 뽑은 증거 토큰(`백틱`, 파일 경로, 6/6 같은 개수, exit 0, 커밋 해시)이
     **이번 턴의 실제 도구 입력·출력에 그대로 있어야 한다**. 없는 숫자·명령을 근거로 쓰면 차단.
  3) '미확인' 진술이 있어야 한다
한계(정직하게): 토큰이 실제 출력에 있는지까지만 본다. 그 출력이 주장과 '관련 있는지'는 판단 못 한다.

노드별 정책: playbooks/_sanctions/node_policy.json (환경변수 CLAUDE_NODE 또는 cwd 접두어로 노드 판별).
상한 도달 시: 조용히 통과하지 않는다 — 사용자에게 경고(systemMessage) + 우회 기록 + 다음 요청에 경고 주입.
"""
import json, os, re, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLAIM = re.compile(r"정상|완료|확인(했|함|됨|완료)|통과|성공|문제\s*없|해결(됐|했|함)"
                   r"|\b(verified|confirmed|works|working|done|fixed|resolved|succeeded|successful(ly)?|complete[ds]?|pass(es|ed)?)\b|all good|no (issues|problems)", re.I)
EVID_LINE = re.compile(r"^\s*[-*]?\s*\**(근거|검증|evidence)\**\s*[:：]", re.I)
UNVER = re.compile(r"미확인|확인\s*못|확인\s*불가|확인하지\s*않|unverified|unconfirmed|not (verified|confirmed|checked)|(could|can)(n't|not) (verify|confirm|check)", re.I)
TOKEN = re.compile(r"`([^`]{2,120})`|(\b\d+/\d+\b)|\b(exit\s*(?:code\s*)?[=:]?\s*\d+)\b|(\b[0-9a-f]{7,40}\b)|([\w./-]+\.(?:py|md|json|js|html|png|sh|log|jsonl))", re.I)
HOME = Path.home() / ".claude"
LOG, BYPASS = HOME / "claim_gate.log", HOME / "claim_gate_bypass.json"

def policy(cwd):
    try:
        cfg = json.loads((ROOT / "playbooks/_sanctions/node_policy.json").read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    node = os.environ.get("CLAUDE_NODE")
    if not node:
        for name, p in cfg.get("nodes", {}).items():
            pre = os.path.expanduser(p.get("cwd_prefix", "")) if p.get("cwd_prefix") else None
            if pre and cwd and cwd.startswith(pre):
                node = name
                break
    pol = {"max_blocks": 3, "require_trace": True, "min_traced": 1}
    pol.update(cfg.get("default", {}))
    pol.update(cfg.get("nodes", {}).get(node or "", {}))
    return node or "default", pol

def turn(transcript):
    rows = [json.loads(l) for l in open(transcript, encoding="utf-8") if l.strip()]
    start = 0
    for i, r in enumerate(rows):
        if r.get("type") == "user":
            c = r.get("message", {}).get("content")
            if isinstance(c, str) or (isinstance(c, list) and any(b.get("type") == "text" for b in c)):
                start = i
    text, io, tools = [], [], 0
    for r in rows[start + 1:]:
        for b in r.get("message", {}).get("content", []) or [] if isinstance(r.get("message", {}).get("content"), list) else []:
            t = b.get("type")
            if r.get("type") == "assistant" and t == "text":
                text.append(b["text"])
            elif t == "tool_use":
                tools += 1
                io.append(json.dumps(b.get("input", {}), ensure_ascii=False))
            elif t == "tool_result":
                c = b.get("content")
                io.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
    return "\n".join(text), "\n".join(io), tools

def evidence_lines(text):
    out, on = [], False
    for line in text.splitlines():
        if EVID_LINE.match(line):
            out.append(line); on = True
        elif on and re.match(r"^\s*([-*]|\d+\.)\s+", line):
            out.append(line)
        else:
            on = False
    return out

def found(tok, io):
    if tok in io:
        return True
    m = re.match(r"exit\s*(?:code\s*)?[=:]?\s*(\d+)", tok, re.I)
    if m:
        return re.search(rf"exit(\s*code)?\s*[=:]?\s*{m.group(1)}\b", io, re.I) is not None
    return False

def check(text, io, tools, pol):
    why = []
    if tools == 0:
        why.append("이번 턴 도구 실행 0회인데 정상/완료 주장 — 실행 후 보고할 것")
    ev = evidence_lines(text)
    if not ev:
        why.append("'근거:' 줄 없음")
    elif pol.get("require_trace", True):
        toks = [next(g for g in m.groups() if g) for l in ev for m in TOKEN.finditer(l)]
        hit = [t for t in toks if found(t, io)]
        miss = [t for t in toks if not found(t, io) and (re.fullmatch(r"\d+/\d+", t) or re.match(r"exit", t, re.I))]
        if len(hit) < pol.get("min_traced", 1):
            why.append(f"근거가 실제 도구 출력과 연결 안 됨 — 명령·파일·개수·exit 코드를 출력에 있는 그대로 인용할 것 (추적된 토큰 {len(hit)}개)")
        if miss:
            why.append(f"근거의 숫자/종료코드가 이번 턴 실제 출력에 없음: {miss[:5]}")
    if not UNVER.search(text):
        why.append("미확인 범위 진술 없음 — 없으면 '미확인: 없음'")
    return why

def main():
    data = json.load(sys.stdin)
    tp = data.get("transcript_path")
    if not tp or not os.path.isfile(tp):
        return 0
    text, io, tools = turn(tp)
    if not CLAIM.search(text):
        return 0
    node, pol = policy(data.get("cwd") or os.getcwd())
    why = check(text, io, tools, pol)
    if not why:
        return 0
    sid = data.get("session_id", "x")
    cnt_f = Path("/tmp") / f"claim_gate_{sid}.cnt"
    n = int(cnt_f.read_text()) + 1 if cnt_f.exists() and data.get("stop_hook_active") else 1
    cnt_f.write_text(str(n))
    HOME.mkdir(parents=True, exist_ok=True)
    rec = {"t": time.strftime("%F %T"), "session": sid, "node": node, "n": n, "why": why}
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if n > pol["max_blocks"]:
        # 무한반복은 막되 조용히 통과시키지 않는다: 사용자 화면 경고 + 다음 요청에 경고 주입용 기록
        try:
            by = json.loads(BYPASS.read_text())
        except Exception:
            by = {}
        by[sid] = rec
        BYPASS.write_text(json.dumps(by, ensure_ascii=False))
        print(json.dumps({"systemMessage": f"⚠ claim_gate[{node}]: 이 응답은 근거 검증 {pol['max_blocks']}회 실패 후 강제 종료됨 — 미검증 보고로 취급할 것. 사유: {'; '.join(why)}"}, ensure_ascii=False))
        return 0
    print(f"[claim_gate:{node}] 증거 검증 실패로 보고 차단 ({n}/{pol['max_blocks']}):\n- " + "\n- ".join(why), file=sys.stderr)
    return 2

if __name__ == "__main__":
    sys.exit(main())
