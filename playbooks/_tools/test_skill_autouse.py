#!/usr/bin/env python3
"""새 스킬 추가 → 자동 등록 → 세션 시작 알림 → 요청 라우팅까지 끝단 시험. 저장소 사본·임시 HOME에서 돌려 원본을 건드리지 않음."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[2]
tmp = Path(tempfile.mkdtemp())
repo, home = tmp / "repo", tmp / "home"
shutil.copytree(SRC, repo, ignore=shutil.ignore_patterns(".git"), symlinks=True)
env = dict(os.environ, HOME=str(home))
H = repo / ".claude" / "hooks"
def hook(name, payload):
    return subprocess.run([sys.executable, str(H / name)], input=json.dumps(payload), capture_output=True, text=True, env=env)

res = []
def check(name, ok, ev): res.append((name, ok, ev))

out1 = hook("skill_announce.py", {"source": "startup"}).stdout          # 첫 세션: 기존 스킬 기록
new = repo / "playbooks" / "demo-new-skill"
shutil.copytree(repo / "playbooks" / "_template", new)
skill = new / "SKILL.md"
skill.write_text(skill.read_text().replace("name: [job-name]", "name: demo-new-skill")
                 .replace('["[실제로 칠 말]"]', '["데모 보고서"]'))
out2 = hook("skill_announce.py", {"source": "startup"}).stdout          # 다음 세션: 새 스킬 감지
link = repo / ".claude" / "skills" / "demo-new-skill"
check("새 스킬 자동 등록(링크)", link.is_symlink() and link.resolve() == new.resolve(), str(link))
check("세션 시작 알림에 '새로 추가'", "demo-new-skill(새로 추가)" in out2, out2.splitlines()[-1][:90] if out2 else "출력 없음")
check("두 번째 알림엔 재알림 없음", "demo-new-skill(" not in hook("skill_announce.py", {"source": "startup"}).stdout, "seen 기록")
r = hook("skill_router.py", {"prompt": "이번 주 데모 보고서 써줘", "session_id": "t"}).stdout
check("요청 라우팅", "demo-new-skill" in r, r.strip()[:90])
check("무관한 요청은 주입 없음", hook("skill_router.py", {"prompt": "날씨 어때", "session_id": "t"}).stdout == "", "빈 출력")
log = home / ".claude" / "skill_usage.log"
check("사용 기록 남음", log.is_file() and "demo-new-skill" in log.read_text(), str(log))
shutil.rmtree(new)
subprocess.run([sys.executable, str(repo / "playbooks/_tools/sync_skills.py")], capture_output=True, env=env)
check("삭제된 스킬 링크 정리", not link.is_symlink(), "끊긴 링크 제거")
shutil.rmtree(tmp)

fail = 0
for n, ok, ev in res:
    print(f"{'PASS' if ok else 'FAIL'}  {n} — {ev}"); fail += not ok
print(f"\n{len(res) - fail}/{len(res)} 통과")
sys.exit(1 if fail else 0)
