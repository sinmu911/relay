#!/usr/bin/env python3
"""claim_gate 훅 회귀 시험: 가짜 대화 기록으로 막아야 할 것/통과할 것을 확인. 실패 시 exit 1."""
import json, subprocess, sys, tempfile, uuid
from pathlib import Path

HOOK = Path(__file__).resolve().parents[3] / ".claude" / "hooks" / "claim_gate.py"

def run(assistant_blocks, active=False):
    rows = [{"type": "user", "message": {"content": "확인해봐"}}]
    rows += [{"type": "assistant", "message": {"content": [b]}} for b in assistant_blocks]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))
    inp = json.dumps({"transcript_path": f.name, "session_id": uuid.uuid4().hex, "stop_hook_active": active})
    return subprocess.run([sys.executable, str(HOOK)], input=inp, capture_output=True, text=True).returncode

T = lambda s: {"type": "text", "text": s}
TOOL = {"type": "tool_use", "name": "Bash", "input": {"command": "x"}}
cases = [
    ("도구 없이 '정상입니다'", [T("버튼 정상입니다.")], 2),
    ("도구 있지만 근거/미확인 없음", [TOOL, T("확인했습니다. 정상.")], 2),
    ("근거 있지만 미확인 없음", [TOOL, T("정상.\n근거: check.py exit 0")], 2),
    ("근거+미확인 갖춤", [TOOL, T("서버 정상.\n근거: check.py 6/6, exit 0\n미확인: 폰 화면")], 0),
    ("주장 없음(질문)", [T("어느 카드 코드인가요?")], 0),
    ("영어 주장 근거 없음", [TOOL, T("All checks passed, the button works.")], 2),
    ("영어 주장 근거+미확인", [TOOL, T("Server confirmed.\nEvidence: check.py exit 0\nUnverified: phone screen")], 0),
]
# 무한반복 상한: 같은 세션에서 연속 차단 3회 후 4번째는 통과
import uuid as _u
sid = _u.uuid4().hex
def run_sid(blocks, active):
    rows = [{"type": "user", "message": {"content": "q"}}] + [{"type": "assistant", "message": {"content": [b]}} for b in blocks]
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write("\n".join(json.dumps(r) for r in rows))
    inp = json.dumps({"transcript_path": f.name, "session_id": sid, "stop_hook_active": active})
    return subprocess.run([sys.executable, str(HOOK)], input=inp, capture_output=True, text=True).returncode
seq = [run_sid([T("정상입니다")], i > 0) for i in range(4)]
Path(f"/tmp/claim_gate_{sid}.cnt").unlink(missing_ok=True)
fail = 0
for name, blocks, want in cases:
    got = run(blocks)
    ok = got == want
    fail += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name} — 기대 {want}, 실제 {got}")
okc = seq == [2, 2, 2, 0]
fail += not okc
print(f"{'PASS' if okc else 'FAIL'}  무한반복 상한 — 기대 [2,2,2,0], 실제 {seq}")
print(f"\n{len(cases) + 1 - fail}/{len(cases) + 1} 통과")
sys.exit(1 if fail else 0)
