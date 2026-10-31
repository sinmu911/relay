#!/usr/bin/env python3
"""매뉴얼 → 스킬 등록(심볼릭 링크) + 색인 생성. 여러 번 돌려도 안전(멱등).

  python3 playbooks/_tools/sync_skills.py                       # 이 저장소 .claude/skills 에 등록
  python3 playbooks/_tools/sync_skills.py --target ~/.claude/skills   # 이 컴퓨터의 모든 세션(노드)에 등록
  python3 playbooks/_tools/sync_skills.py --check               # 바꾸지 않고 누락만 보고(누락 시 exit 1)

원본은 playbooks/<이름>/ 하나뿐. 링크라서 원본을 고치면 모든 노드에 바로 반영(Claude Code가 skills 폴더를 감시).
"""
import argparse, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from skilllib import BASE, REPO, frontmatter, playbooks

ap = argparse.ArgumentParser()
ap.add_argument("--target", default=str(REPO / ".claude" / "skills"))
ap.add_argument("--check", action="store_true")
a = ap.parse_args()
target = Path(os.path.expanduser(a.target))
problems, made = [], []
if not a.check:
    target.mkdir(parents=True, exist_ok=True)

for d in playbooks():
    link = target / d.name
    rel = os.path.relpath(d, target) if str(target).startswith(str(REPO)) else str(d)
    if link.is_symlink() and link.resolve() == d.resolve():
        continue
    if link.exists() and not link.is_symlink():
        problems.append(f"{link} 가 링크가 아닌 실제 폴더 — 원본이 둘이 됨. 수동 정리 필요")
        continue
    if a.check:
        problems.append(f"미등록: {d.name} → {link}")
        continue
    if link.is_symlink():
        link.unlink()
    link.symlink_to(rel, target_is_directory=True)
    made.append(d.name)

# 끊긴 링크(삭제된 매뉴얼) 정리
if target.is_dir():
    for link in target.iterdir():
        if link.is_symlink() and not link.exists() and str(os.readlink(link)).find("playbooks") >= 0:
            (problems.append(f"끊긴 링크: {link}") if a.check else (link.unlink(), made.append(f"-{link.name}")))

# 색인 (README 대신 기계가 갱신)
rows = ["# SKILLS — 자동 생성 (sync_skills.py). 직접 고치지 말 것", "", "| 스킬 | 언제 쓰는지 | 트리거 |", "|---|---|---|"]
for d in playbooks():
    f = frontmatter(d / "SKILL.md")
    rows.append(f"| {f.get('name', d.name)} | {f.get('description', '(description 없음)')} | {', '.join(f.get('triggers', []))} |")
idx = BASE / "SKILLS.md"
new = "\n".join(rows) + "\n"
if a.check:
    if not idx.is_file() or idx.read_text(encoding="utf-8") != new:
        problems.append("playbooks/SKILLS.md 가 최신 아님 — sync_skills.py 실행")
else:
    idx.write_text(new, encoding="utf-8")

print(f"대상 {target} · 매뉴얼 {len(playbooks())}개 · 변경 {made or '없음'}")
for p in problems:
    print("  -", p)
sys.exit(1 if problems else 0)
