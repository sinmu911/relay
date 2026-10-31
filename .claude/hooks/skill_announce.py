#!/usr/bin/env python3
"""SessionStart 훅 — 세션(노드) 시작 때 스킬 등록을 맞추고, 스킬 목록과 '새로 생긴 스킬'을 모델에게 알린다.
본 기록: ~/.claude/skill_seen.json (노드별 마지막으로 본 스킬과 수정시각)."""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "playbooks" / "_tools"))
from skilllib import frontmatter, playbooks

subprocess.run([sys.executable, str(ROOT / "playbooks/_tools/sync_skills.py")], capture_output=True)
seen_f = Path.home() / ".claude" / "skill_seen.json"
try:
    seen = json.loads(seen_f.read_text())
except Exception:
    seen = {}
now, lines, fresh = {}, [], []
for d in playbooks():
    f = frontmatter(d / "SKILL.md")
    m = int((d / "SKILL.md").stat().st_mtime)
    now[d.name] = m
    tag = "새로 추가" if d.name not in seen else ("수정됨" if seen[d.name] != m else "")
    if tag:
        fresh.append(f"{d.name}({tag})")
    lines.append(f"- {d.name}: {f.get('description', '')}")
seen_f.parent.mkdir(parents=True, exist_ok=True)
seen_f.write_text(json.dumps(now, ensure_ascii=False))
msg = "[skill_announce] 이 저장소의 업무 스킬 — 해당 요청이면 묻지 말고 먼저 그 SKILL.md 순서·완료의 정의를 따를 것:\n" + "\n".join(lines)
if fresh:
    msg += "\n이번 세션에서 처음 보는/바뀐 스킬: " + ", ".join(fresh) + " — 첫 응답에서 한 줄로 알릴 것."
print(msg[:9500])
