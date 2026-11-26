"""글 성적표 — 글마다 발행 뒤 7일·30일 조회수를 검문소 점수와 나란히 적는다(사장님 10-14 "나쁠 거 없으니까").

목적: 우리 점검(검문소·리얼엔진) 중 어떤 게 진짜 조회수와 같이 움직이는지 숫자로 보려고(연구6).
읽기만 한다. 하루 한 번 통계 받은 뒤:
  - 통계/월간조회수순위.txt(이번 달 글별 조회수, 어제까지)를 전날 것과 비교해 하루치 조회수를 글마다 쌓는다
    (달이 바뀌면 새 달 숫자가 그대로 하루치). 순위에 없는 글은 0.
  - 블로그 글 목록(RSS)의 최근 60일 글마다: 발행일 · 7일/30일/지금까지 조회 · 검문소 걸림/주의.
  - 상태/글성적표.json 과 사람이 읽는 상태/글성적표.md 를 쓴다.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sources import find_similar

log = logging.getLogger(__name__)

ROW_RE = re.compile(r"^\d+\s+(.+?)\s+(\d+)\s+(?:글|동영상|클립)\s+\d{4}\.\d{2}\.\d{2}\.")
LINK_RE = re.compile(r"^(.*?)\s*\|\s*https://blog\.stat\.naver\.com/blog/article/(\d+)/cv")
PERIOD_RE = re.compile(r"(\d{4})\.(\d{2})\.(\d{2})\.")
TITLE_RE = re.compile(r"^=+\n제목\n=+\n(.+)$", re.M)
KEEP_DAYS = 60


def parse_month_rank(text: str) -> Tuple[str, Dict[str, int]]:
    """(기준일 YYYY-MM-DD, {글번호: 이번 달 조회수}). 기준일을 못 찾으면 ""."""
    m = PERIOD_RE.search(text)
    period = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""
    links = [(t.strip(), n) for t, n in (LINK_RE.match(l).groups() for l in text.splitlines() if LINK_RE.match(l))]
    counts: Dict[str, int] = {}
    for line in text.splitlines():
        r = ROW_RE.match(line.strip())
        if not r:
            continue
        title, n = r.group(1).strip(), int(r.group(2))
        log_no = next((no for t, no in links if t and (title.startswith(t) or t.startswith(title))), None)
        if log_no:
            counts[log_no] = n
    return period, counts


def add_snapshot(meta: dict, period: str, counts: Dict[str, int]) -> bool:
    """하루치 조회수를 meta["daily_views"][글번호][기준일] 에 쌓는다. 같은 기준일은 한 번만. 쌓았으면 True."""
    if not period:
        return False
    snap = meta.get("rank_snap") or {}
    if snap.get("period") == period:
        return False
    old = snap.get("counts", {}) if snap.get("period", "")[:7] == period[:7] else {}
    daily = meta.setdefault("daily_views", {})
    for log_no, n in counts.items():
        inc = n - old.get(log_no, 0)
        if inc > 0:
            daily.setdefault(log_no, {})[period] = inc
    meta["rank_snap"] = {"period": period, "counts": counts}
    cut = (date.fromisoformat(period) - timedelta(days=400)).isoformat()   # 오래된 하루치는 버림
    for log_no in list(daily):
        daily[log_no] = {d: v for d, v in daily[log_no].items() if d >= cut}
        if not daily[log_no]:
            del daily[log_no]
    return True


def _views(days: Dict[str, int], start: str, n: Optional[int]) -> int:
    end = (date.fromisoformat(start) + timedelta(days=n - 1)).isoformat() if n else "9999"
    return sum(v for d, v in days.items() if start <= d <= end)


def checkpoint_titles(neo_root: Path) -> Dict[str, dict]:
    """{완성본 제목: 검문소 결과}. 검문소_<파일>.json 의 파일 이름으로 초안/<파일>.md 제목을 찾는다."""
    out = {}
    for f in sorted((neo_root / "상태").glob("검문소_*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
            text = (neo_root / "초안" / r["파일"]).read_text(encoding="utf-8")
        except (OSError, ValueError, KeyError):
            continue
        m = TITLE_RE.search(text.replace("\r\n", "\n"))
        if m:
            out[m.group(1).strip()] = {"걸림": r.get("걸림"), "주의": r.get("주의"), "참고": r.get("참고", 0),
                                       "파일": r["파일"]}
    return out


def build(meta: dict, posts: List[dict], checks: Dict[str, dict], today: date) -> List[dict]:
    daily = meta.get("daily_views", {})
    since = meta.get("score_first", "")
    rows = []
    for p in posts:
        if not p.get("date") or (today - date.fromisoformat(p["date"])).days > KEEP_DAYS:
            continue
        days = daily.get(p["log"], {})
        age = (today - date.fromisoformat(p["date"])).days
        match = find_similar(p["title"], list(checks)) if checks else None
        c = checks.get(match, {}) if match else {}
        rows.append({
            "글": p["title"][:60], "주소": f"https://blog.naver.com/{meta.get('blog_id', 'mose_love')}/{p['log']}",
            "발행일": p["date"], "지난 날": age,
            "7일 조회": _views(days, p["date"], 7) if age >= 7 else None,
            "30일 조회": _views(days, p["date"], 30) if age >= 30 else None,
            "지금까지": _views(days, p["date"], None),
            "검문소": (f"걸림 {c.get('걸림')} · 주의 {c.get('주의')}" + (f" · 참고 {c['참고']}" if c.get("참고") else "")) if c else "",
            "집계 시작": since,
        })
    return sorted(rows, key=lambda r: r["발행일"], reverse=True)


def to_markdown(rows: List[dict], at: str) -> str:
    def f(v):
        return "-" if v is None else str(v)
    lines = [f"# 글 성적표 ({at})", "",
             "7일·30일 칸의 '-' 는 아직 그만큼 안 지났다는 뜻. 조회수는 하루 한 번 받은 통계에서 쌓음.", "",
             "| 발행일 | 글 | 7일 | 30일 | 지금까지 | 검문소 |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['발행일']} | {r['글'][:34]} | {f(r['7일 조회'])} | {f(r['30일 조회'])} | {r['지금까지']} | {r['검문소'] or '-'} |")
    return "\n".join(lines) + "\n"


def update(meta: dict, neo_root: Path, stats_dir: Path, posts: List[dict], now: datetime, blog_id: str) -> int:
    """하루 한 번(통계 받은 뒤). 성적표 줄 수를 돌려준다. meta 를 고친다(저장은 부르는 쪽)."""
    meta["blog_id"] = blog_id
    try:
        text = (stats_dir / "월간조회수순위.txt").read_text(encoding="utf-8")
    except OSError:
        text = ""
    period, counts = parse_month_rank(text)
    if add_snapshot(meta, period, counts):
        meta.setdefault("score_first", period)
    rows = build(meta, posts, checkpoint_titles(neo_root), now.date())
    at = now.strftime("%Y-%m-%d %H:%M")
    out = neo_root / "상태"
    out.mkdir(parents=True, exist_ok=True)
    (out / "글성적표.json").write_text(json.dumps(
        {"_설명": "글별 발행 뒤 조회수와 검문소 점수(연구6). 10편쯤 쌓이면 어떤 점검이 조회수와 같이 움직이는지 본다.",
         "at": at, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "글성적표.md").write_text(to_markdown(rows, at), encoding="utf-8")
    return len(rows)
