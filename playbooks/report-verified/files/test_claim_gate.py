#!/usr/bin/env python3
"""claim_gate 훅 회귀 시험: 가짜 대화 기록으로 막을 것/통과할 것 확인. 임시 HOME 사용. 실패 시 exit 1."""
import json, os, subprocess, sys, tempfile, uuid
from pathlib import Path

HOOK = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "claim_gate.py"
HOME = tempfile.mkdtemp()

def run(blocks, sid=None, active=False, env_extra=None):
    rows = [{"type": "user", "message": {"content": "확인해봐"}}]
    for b in blocks:
        role = "user" if b.get("type") == "tool_result" else "assistant"
        rows.append({"type": role, "message": {"content": [b]}})
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
    inp = json.dumps({"transcript_path": f.name, "session_id": sid or uuid.uuid4().hex, "stop_hook_active": active, "cwd": "/nowhere"})
    env = dict(os.environ, HOME=HOME, **(env_extra or {}))
    env.pop("CLAUDE_NODE", None) if not env_extra or "CLAUDE_NODE" not in env_extra else None
    return subprocess.run([sys.executable, str(HOOK)], input=inp, capture_output=True, text=True, env=env)

T = lambda s: {"type": "text", "text": s}
TOOL = {"type": "tool_use", "name": "Bash", "input": {"command": "python3 check.py"}}
OUT = {"type": "tool_result", "content": "PASS ...\n6/6 통과\nexit=0"}
cases = [
    ("도구 없이 '정상입니다'", [T("버튼 정상입니다.")], 2),
    ("도구 있지만 근거/미확인 없음", [TOOL, OUT, T("확인했습니다. 정상.")], 2),
    ("'근거: 됐음' (추적 토큰 0)", [TOOL, OUT, T("정상.\n근거: 됐음\n미확인: 없음")], 2),
    ("가짜 개수 '9/9' (출력엔 6/6)", [TOOL, OUT, T("정상.\n근거: `check.py` 9/9 통과\n미확인: 없음")], 2),
    ("가짜 종료코드 exit 1", [TOOL, OUT, T("정상.\n근거: check.py exit 1\n미확인: 없음")], 2),
    ("실제 출력과 일치 6/6·exit 0", [TOOL, OUT, T("서버 정상.\n근거: `check.py` 6/6, exit 0\n미확인: 폰 화면")], 0),
    ("주장 없음(질문)", [T("어느 카드 코드인가요?")], 0),
    ("영어 주장 근거 없음", [TOOL, OUT, T("All checks passed, the button works.")], 2),
    ("영어 주장 실제 근거", [TOOL, OUT, T("Server confirmed.\nEvidence: check.py 6/6\nUnverified: phone screen")], 0),
]
fail = 0
for name, blocks, want in cases:
    got = run(blocks).returncode
    ok = got == want; fail += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name} — 기대 {want}, 실제 {got}")

# 상한 도달: 조용히 통과 금지 — systemMessage 경고 + 우회 기록 + 라우터가 다음 요청에 경고 주입
sid = uuid.uuid4().hex
seq = [run([T("정상입니다")], sid=sid, active=i > 0) for i in range(4)]
codes = [r.returncode for r in seq]
warn = "systemMessage" in seq[-1].stdout and "강제 종료" in seq[-1].stdout
router = HOOK.parent / "skill_router.py"
r = subprocess.run([sys.executable, str(router)], input=json.dumps({"prompt": "다음", "session_id": sid}),
                   capture_output=True, text=True, env=dict(os.environ, HOME=HOME))
ok = codes == [2, 2, 2, 0] and warn and "우회 경고" in r.stdout
fail += not ok
print(f"{'PASS' if ok else 'FAIL'}  상한 도달 시 공개 경고 — 코드 {codes}, 화면경고 {warn}, 다음요청 주입 {'우회 경고' in r.stdout}")

# 노드별 정책: CLAUDE_NODE=chatbot 은 max_blocks 1, min_traced 2
sid2 = uuid.uuid4().hex
c1 = [run([T("정상입니다")], sid=sid2, active=i > 0, env_extra={"CLAUDE_NODE": "chatbot"}).returncode for i in range(2)]
c2 = run([TOOL, OUT, T("정상.\n근거: check.py 실행\n미확인: 없음")], env_extra={"CLAUDE_NODE": "chatbot"}).returncode
c3 = run([TOOL, OUT, T("정상.\n근거: check.py 실행\n미확인: 없음")]).returncode
ok = c1 == [2, 0] and c2 == 2 and c3 == 0
fail += not ok
print(f"{'PASS' if ok else 'FAIL'}  노드 차등(chatbot 더 엄격) — 상한 {c1}, 토큰1개 chatbot {c2} / default {c3}")

total = len(cases) + 2
print(f"\n{total - fail}/{total} 통과")
sys.exit(1 if fail else 0)
