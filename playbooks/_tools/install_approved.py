#!/usr/bin/env python3
"""승인된 스냅샷 설치기 — 자동 git pull 대신 쓰는 것 (공급망 위험 차단).

원칙: 훅·스킬이 실행되는 곳은 git 작업폴더가 아니라 '사람이 diff를 보고 승인한 커밋의 스냅샷'.
작업폴더를 pull 해도 실행되는 코드는 바뀌지 않는다. 바꾸려면 이 스크립트로 diff 확인 → --approve.

  python3 install_approved.py                 # origin/main 최신과 설치본의 diff만 보여줌 (아무것도 안 바꿈)
  python3 install_approved.py --approve <커밋> # 그 커밋을 ~/.claude/relay-approved/<커밋>에 풀고 current 링크 교체
설치 후 ~/.claude/settings.json 훅 경로: ~/.claude/relay-approved/current/.claude/hooks/<훅>.py
조건: 커밋은 origin/main 안에 있어야 함(=PR로 병합된 것만). 설치 기록: ~/.claude/relay-approved/INSTALLED.log
"""
import argparse, subprocess, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEST = Path.home() / ".claude" / "relay-approved"
SCOPE = [".claude", "playbooks"]

def git(*a, check=True):
    return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True, check=check).stdout.strip()

ap = argparse.ArgumentParser()
ap.add_argument("--approve", metavar="COMMIT")
ap.add_argument("--no-fetch", action="store_true", help="시험용: origin/main 갱신 생략")
a = ap.parse_args()
if not a.no_fetch:
    git("fetch", "-q", "origin", "main")
cur = DEST / "current"
installed = cur.resolve().name if cur.is_symlink() else None
target = a.approve or git("rev-parse", "origin/main")
target = git("rev-parse", target)
if subprocess.run(["git", "-C", str(REPO), "merge-base", "--is-ancestor", target, "origin/main"]).returncode:
    sys.exit(f"거부: {target[:10]} 는 origin/main 에 없음 — PR 병합된 커밋만 설치 가능")
print(f"설치본: {installed[:10] if installed else '없음'} → 대상: {target[:10]}")
diff = git("diff", "--stat", installed or "4b825dc642cb6eb9a060e54bf8d69288fbee4904", target, "--", *SCOPE)
print(diff or "(실행 범위 변경 없음)")
if not a.approve:
    print(f"\n전체 diff 확인: git -C {REPO} diff {installed or '<처음>'} {target[:10]} -- {' '.join(SCOPE)}")
    print(f"검토 후 승인: python3 {Path(__file__).name} --approve {target[:10]}")
    sys.exit(0)
out = DEST / target
if not out.exists():
    out.mkdir(parents=True)
    arc = subprocess.run(["git", "-C", str(REPO), "archive", target, *SCOPE], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(out)], input=arc, check=True)
tmp = DEST / ".current.tmp"
tmp.unlink(missing_ok=True); tmp.symlink_to(out.name); tmp.replace(cur)
with open(DEST / "INSTALLED.log", "a", encoding="utf-8") as f:
    f.write(f"{time.strftime('%F %T')} {installed or '-'} -> {target}\n")
subprocess.run([sys.executable, str(cur / "playbooks/_tools/sync_skills.py"), "--target", str(Path.home() / ".claude/skills")])
print(f"설치 완료: {cur} -> {target[:10]}")
