#!/usr/bin/env python3
"""PreToolUse 훅 — main 병합/푸시는 사용자의 명시 승인 문구가 있을 때만.

'병합해' 한 마디로는 안 된다. 사용자의 가장 최근 메시지에 정확히 `병합 승인 #<PR번호>` 가 있어야
mcp__github__merge_pull_request(그 번호)가 통과. main 으로의 git push 는 `main 푸시 승인` 문구 필요.
"""
import json, re, sys

data = json.load(sys.stdin)
tool, inp = data.get("tool_name", ""), data.get("tool_input", {}) or {}

def last_user_text():
    try:
        rows = [json.loads(l) for l in open(data["transcript_path"], encoding="utf-8") if l.strip()]
    except Exception:
        return ""
    for r in reversed(rows):
        if r.get("type") != "user":
            continue
        c = r.get("message", {}).get("content")
        if isinstance(c, str):
            return c
        if isinstance(c, list) and any(b.get("type") == "text" for b in c):
            return "\n".join(b.get("text", "") for b in c if b.get("type") == "text")
    return ""

need = None
if tool.endswith("merge_pull_request"):
    need = f"병합 승인 #{inp.get('pullNumber')}"
elif tool == "Bash" and re.search(r"git\s+push\b[^\n;&|]*\b(main|master)\b|git\s+push\b[^\n;&|]*:main\b", inp.get("command", "")):
    need = "main 푸시 승인"
if need and need not in last_user_text():
    print(f"[merge_gate] 차단: 사용자 최근 메시지에 '{need}' 문구가 없음. diff·CI 결과를 보여주고 그 문구로 승인받을 것.", file=sys.stderr)
    sys.exit(2)
