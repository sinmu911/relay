#!/usr/bin/env python3
"""merge_gate 훅 시험. 실패 시 exit 1."""
import json, subprocess, sys, tempfile
from pathlib import Path
HOOK = Path(__file__).resolve().parents[2] / ".claude/hooks/merge_gate.py"
def run(user, tool, inp):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as f:
        f.write(json.dumps({"type": "user", "message": {"content": user}}, ensure_ascii=False))
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"transcript_path": f.name, "tool_name": tool, "tool_input": inp}),
                          capture_output=True, text=True).returncode
M = "mcp__github__merge_pull_request"
cases = [
    ("'병합해' 한 마디", run("병합해", M, {"pullNumber": 2}), 2),
    ("다른 번호 승인", run("병합 승인 #3", M, {"pullNumber": 2}), 2),
    ("정확한 승인 문구", run("diff 봤음. 병합 승인 #2", M, {"pullNumber": 2}), 0),
    ("main 푸시 무승인", run("올려", "Bash", {"command": "git push origin main"}), 2),
    ("main 푸시 승인", run("main 푸시 승인", "Bash", {"command": "git push origin main"}), 0),
    ("작업 브랜치 푸시는 무관", run("올려", "Bash", {"command": "git push -u origin ccr-0eea4943-j44c9h"}), 0),
    ("일반 명령 무관", run("x", "Bash", {"command": "ls"}), 0),
]
fail = 0
for n, got, want in cases:
    ok = got == want; fail += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {n} — 기대 {want}, 실제 {got}")
print(f"\n{len(cases)-fail}/{len(cases)} 통과"); sys.exit(1 if fail else 0)
