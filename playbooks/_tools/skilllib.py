"""스킬 공용 함수: frontmatter 읽기, 매뉴얼 목록. (PyYAML 없이 동작)"""
import json, re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]          # playbooks/
REPO = BASE.parent

def frontmatter(skill_md: Path) -> dict:
    s = skill_md.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", s, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if mm := re.match(r"(\w[\w-]*):\s*(.*)$", line):
            out[mm.group(1)] = mm.group(2).strip()
        elif mm := re.match(r"\s+triggers:\s*(\[.*\])\s*$", line):
            out["triggers"] = json.loads(mm.group(1))
    return out

def playbooks():
    """실제 매뉴얼 폴더(이름이 _ 로 시작하지 않고 SKILL.md 있음)."""
    return [d for d in sorted(BASE.iterdir()) if d.is_dir() and not d.name.startswith("_") and (d / "SKILL.md").is_file()]
