#!/usr/bin/env python3
"""relay-shell-release 증명 검사. 저장소 루트를 자동으로 찾는다. 실패가 하나라도 있으면 종료코드 1."""
import json, re, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HTML = ["index.html", "app.html"]
SECRET = re.compile(r"PRIVATE KEY|VAPID_PRIV|\bsk-[A-Za-z0-9]{20,}|\bghp_[A-Za-z0-9]{20,}|\bAIza[0-9A-Za-z_-]{30,}")
results = []
SELF = {Path(__file__).resolve(), (ROOT / "playbooks/_tools/validate_playbooks.py").resolve()}

def rec(name, ok, evidence):
    results.append((name, ok, evidence))

def read(p):
    return (ROOT / p).read_text(encoding="utf-8")

# 1. manifest
try:
    man = json.loads(read("manifest.json"))
    icons = [i["src"] for i in man.get("icons", [])]
    missing = [s for s in icons if not (ROOT / s).is_file()]
    rec("manifest 파싱+아이콘 존재", not missing, f"아이콘 {len(icons)}개, 없음 {missing or 0}")
except Exception as e:
    man, icons = {}, []
    rec("manifest 파싱+아이콘 존재", False, repr(e))

# 2. 로컬 참조
refs = {}
for f in HTML:
    refs[f] = sorted(set(re.findall(r'(?:href|src)=["\']([^"\'#?]+)', read(f))))
bad = [f"{f}:{r}" for f, rs in refs.items() for r in rs
       if not re.match(r"[a-z]+:|//", r) and not (ROOT / r).is_file()]
rec("html 로컬 참조 존재", not bad, f"없는 참조 {bad or 0}")

# 3. 아이콘 버전 일치 (manifest 기준)
ver = sorted({m.group(1) for s in icons if (m := re.search(r"(-v\d+)\.png$", s))})
if ver:
    old = []
    for f in HTML + ["sw.js"]:
        for name in re.findall(r"icon-[\w-]+?\.png", read(f)):
            if not name.endswith(f"{ver[-1]}.png"):
                old.append(f"{f}:{name}")
    rec("아이콘 참조 버전 일치", not old, f"기준 {ver[-1]}, 구이름 {sorted(set(old)) or 0}")
else:
    rec("아이콘 참조 버전 일치", True, "manifest 아이콘에 버전 접미사 없음 — 검사 생략")

# 4. viewport
nov = [f for f in HTML if not re.search(r'name="viewport"[^>]*maximum-scale=1', read(f))]
rec("viewport maximum-scale=1", not nov, f"누락 {nov or 0}")

# 5. JS 문법
errs = []
with tempfile.TemporaryDirectory() as d:
    jobs = [("sw.js", read("sw.js"))]
    for f in HTML:
        for i, s in enumerate(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", read(f), re.S)):
            jobs.append((f"{f}#script{i}", s))
    for name, code in jobs:
        p = Path(d) / (re.sub(r"\W", "_", name) + ".js")
        p.write_text(code, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
        if r.returncode:
            errs.append(f"{name}: {r.stderr.strip().splitlines()[-1] if r.stderr.strip() else 'error'}")
    rec("JS 문법(node --check)", not errs, f"검사 {len(jobs)}개, 오류 {errs or 0}")

# 6. 비밀값
hits = []
for p in ROOT.rglob("*"):
    if ".git" in p.parts or not p.is_file() or p.suffix in {".png", ".jpg", ".ico"}:
        continue
    if p.resolve() in SELF:  # 패턴 정의 파일 자신은 제외
        continue
    for n, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if SECRET.search(line):
            hits.append(f"{p.relative_to(ROOT)}:{n}")
rec("비밀값 패턴 0개", not hits, f"검출 {hits or 0}")

fail = 0
for name, ok, ev in results:
    print(f"{'PASS' if ok else 'FAIL'}  {name} — {ev}")
    fail += not ok
print(f"\n{len(results) - fail}/{len(results)} 통과. 미확인(수동): 폰 화면 스크린샷, 알림 켜기/끄기")
if fail > 2:
    print("실패 2개 초과 → 결과물 땜질 말고 어느 순서 단계가 원인인지 먼저 진단 (프롬프트 4)")
sys.exit(1 if fail else 0)
