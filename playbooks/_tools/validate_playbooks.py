#!/usr/bin/env python3
"""playbooks/ 아래 모든 매뉴얼 폴더 구조 검사. 실패 시 종료코드 1."""
import re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from skilllib import frontmatter

BASE = Path(__file__).resolve().parents[1]
SECTIONS = ["목적", "언제 쓰는지", "입력", "순서", "결정", "완료의 정의", "예외 사례"]
SECRET = re.compile(r"PRIVATE KEY|\bsk-[A-Za-z0-9]{20,}|\bghp_[A-Za-z0-9]{20,}|\bAIza[0-9A-Za-z_-]{30,}|password\s*[:=]\s*\S", re.I)
DATED = re.compile(r"\d{4}-\d{2}-\d{2}|[-_]v\d+\b|[-_](final|old|new|copy)\b", re.I)
fails = []

dirs = [d for d in sorted(BASE.iterdir()) if d.is_dir() and not d.name.startswith("_")] + [BASE / "_template"]
for d in dirs:
    name = d.name
    skill = d / "SKILL.md"
    if not skill.is_file():
        fails.append(f"{name}: SKILL.md 없음"); continue
    fm = frontmatter(skill)
    if name != "_template":
        if fm.get("name") != name:
            fails.append(f"{name}: frontmatter name '{fm.get('name')}' ≠ 폴더명 (자동 호출 안 됨)")
        if not fm.get("description") or len(fm["description"]) > 1536:
            fails.append(f"{name}: frontmatter description 없음/1536자 초과 (자동 호출 근거)")
        if not fm.get("triggers"):
            fails.append(f"{name}: metadata.triggers 없음 (skill_router가 못 잡음)")
    heads = re.findall(r"^##\s+(.+?)\s*$", skill.read_text(encoding="utf-8"), re.M)
    miss = [s for s in SECTIONS if s not in heads]
    if miss:
        fails.append(f"{name}: SKILL.md 섹션 누락 {miss}")
    for req in ["notes.md", "files/INDEX.md", "examples"]:
        if not (d / req).exists():
            fails.append(f"{name}: {req} 없음")
    idx = d / "files" / "INDEX.md"
    listed = set(re.findall(r"^\|\s*([^|\s][^|]*?)\s*\|", idx.read_text(encoding="utf-8"), re.M)) if idx.is_file() else set()
    for f in sorted((d / "files").glob("*")) if (d / "files").is_dir() else []:
        if f.name == "INDEX.md" or f.name.startswith("."):
            continue
        if f.name not in listed:
            fails.append(f"{name}: files/{f.name} 가 INDEX.md에 없음")
        if DATED.search(f.stem):
            fails.append(f"{name}: files/{f.name} 이름에 날짜/버전 (examples/ 로 옮기거나 이름 변경)")
    for f in d.rglob("*"):
        if f.is_file() and f.suffix in {".md", ".py", ".txt", ".json", ".js", ".sh"}:
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                if SECRET.search(line) and not re.match(r"\s*SECRET\s*=", line):  # 패턴 정의 줄 제외
                    fails.append(f"{name}: 비밀값 의심 {f.relative_to(BASE)}:{n}")
    print(f"{'FAIL' if any(x.startswith(name + ':') for x in fails) else 'PASS'}  {name}")

# 제재 장부: 저장소 안 장치 경로는 실제로 있어야 하고, 외부(~/) 장치는 '외부-미확인'으로 표시돼야 한다
ledger = BASE / "_sanctions" / "LEDGER.md"
REPO = BASE.parent
if ledger.is_file():
    rows = [r for r in ledger.read_text(encoding="utf-8").splitlines() if re.match(r"\|\s*\d{4}-\d{2}-\d{2}", r)]
    for r in rows:
        cols = [c.strip() for c in r.strip("|").split("|")]
        if len(cols) != 7:
            fails.append(f"_sanctions: 칸 수 {len(cols)}≠7 → {r[:40]}"); continue
        dev, state = cols[4], cols[6]
        if dev.startswith("~/"):
            if state != "외부-미확인":
                fails.append(f"_sanctions: 외부 장치 {dev} 상태가 '{state}' (검증 불가 → '외부-미확인')")
        elif not (REPO / dev).is_file():
            fails.append(f"_sanctions: 장치 파일 없음 {dev}")
    print(f"{'FAIL' if any(x.startswith('_sanctions') for x in fails) else 'PASS'}  _sanctions (장부 {len(rows)}줄)")
else:
    fails.append("_sanctions: LEDGER.md 없음")

r = subprocess.run([sys.executable, str(BASE / "_tools/sync_skills.py"), "--check"], capture_output=True, text=True)
print(f"{'PASS' if r.returncode == 0 else 'FAIL'}  스킬 등록(.claude/skills 링크·SKILLS.md 최신)")
if r.returncode:
    fails += ["등록: " + l.strip(" -") for l in r.stdout.splitlines()[1:]]

for f in fails:
    print("  -", f)
print(f"\n매뉴얼 {len(dirs)}개 검사, 문제 {len(fails)}개")
sys.exit(1 if fails else 0)
