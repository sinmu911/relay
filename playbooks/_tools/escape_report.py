#!/usr/bin/env python3
"""claim_gate 반복 탈출 집계 — 노드별·날짜별 강제 통과 횟수와 사유. 비서실장 검토·LEDGER.md 기록용."""
import json, sys
from collections import Counter
from pathlib import Path
f = Path.home() / ".claude" / "claim_gate_escapes.jsonl"
rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.is_file() else []
if not rows:
    print("탈출 기록 0건"); sys.exit(0)
by = Counter((r["t"][:10], r.get("node", "default")) for r in rows)
print("| 날짜 | 노드 | 강제 통과 |\n|---|---|---|")
for (d, n), c in sorted(by.items(), reverse=True):
    print(f"| {d} | {n} | {c} |")
print("\n최근 5건 사유:")
for r in rows[-5:]:
    print(f"- {r['t']} {r.get('node')} 세션 {str(r.get('session'))[:8]}: {'; '.join(r['why'])}")
