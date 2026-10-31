#!/usr/bin/env python3
"""UserPromptSubmit 훅 — 사용자 요청에 스킬 트리거 말이 있으면 그 스킬을 쓰라고 모델 문맥에 주입하고 사용 기록을 남긴다.
기록: ~/.claude/skill_usage.log (어느 노드가 어떤 스킬을 언제 받았는지 → 실제 사용 증거)."""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "playbooks" / "_tools"))
from skilllib import frontmatter, playbooks

data = json.load(sys.stdin)
prompt = data.get("prompt", "")
hits = []
for d in playbooks():
    f = frontmatter(d / "SKILL.md")
    words = [t for t in f.get("triggers", []) if t and t.lower() in prompt.lower()]
    if words:
        hits.append((f.get("name", d.name), words))
if hits:
    log = Path.home() / ".claude" / "skill_usage.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as fh:
        for name, w in hits:
            fh.write(json.dumps({"t": time.strftime("%F %T"), "session": data.get("session_id"), "skill": name, "matched": w}, ensure_ascii=False) + "\n")
    print("[skill_router] 이 요청에 해당하는 스킬: " + "; ".join(f"{n} (일치: {', '.join(w)})" for n, w in hits)
          + " — Skill 도구로 먼저 불러 그 순서와 완료의 정의대로 처리할 것.")
