"""올리기 전 마지막 관문 — 규칙서(블로그_NEO/규칙서.md)의 NEO·네이버·AEO/GEO·SEO 정책 중
프로그램이 확실히 잴 수 있는 것만 다시 본다. 하나라도 걸리면 그 글은 임시저장하지 않고 '글 형식 오류' 알림.

  NEO   금지 표현(1장) · 빈칸 자리표시([확인 필요]·[사장님 한 줄])가 남아 있으면 안 됨(1장 1번)
  네이버 검문소(블로그 섹션의 발행 전 점검)를 거쳤고 '걸림 0' 이어야 함
  AEO   자주 묻는 질문 3개 이하(3장)
  SEO   태그에 #달리는이기사(5장) · 파랑 강조 5곳 이하(7장)

말투·사실 확인처럼 사람 판단이 필요한 건 검문소·리얼엔진(블로그 섹션) 몫이다. 여기선 겹쳐 재지 않는다.
규칙서가 바뀌면 아래 목록만 고친다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

RULE_VERSION = "1.2"   # 이 파일이 따르는 규칙서 버전
BANNED = ("완벽 가이드", "총정리", "완벽 정복", "치트키", "낱낱이", "압도적", "인생샷 성지",
          "에 대해 알아보겠습니다", "를 계획 중이신 분들이라면")
PLACEHOLDERS = ("[확인 필요]", "[사장님 한 줄]")
REQUIRED_TAG = "달리는이기사"
MAX_FAQ = 3
MAX_BLUE = 5
FAQ_HEAD_RE = re.compile(r"^■\s*자주\s*묻는\s*질문")
FAQ_Q_RE = re.compile(r"^\s*\d+\s*[.)]\s*.+\?\s*$")


def count_faq(body: str) -> int:
    n, inside = 0, False
    for line in body.split("\n"):
        if line.startswith("■"):
            inside = bool(FAQ_HEAD_RE.match(line))
        elif inside and FAQ_Q_RE.match(line):
            n += 1
    return n


def checkpoint_problem(md: Path, status_dir: Path) -> Optional[str]:
    """블로그 섹션 검문소 결과(상태/검문소_<완성본 이름>.json)를 본다."""
    path = status_dir / f"검문소_{md.stem}.json"
    if not path.is_file():
        return f"검문소를 안 거친 글이에요({path.name} 없음)"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        stuck = int(data.get("걸림", 0))
    except (OSError, ValueError, TypeError) as e:
        return f"검문소 결과를 못 읽어요: {e}"
    return f"검문소 걸림 {stuck}개 — 블로그 섹션이 고친 뒤 다시 점검해야 해요" if stuck else None


def check(title: str, body: str, tags: List[str], md: Optional[Path] = None,
          status_dir: Optional[Path] = None) -> List[str]:
    """걸린 것 목록(비었으면 통과)."""
    problems = []
    text = title + "\n" + body
    found = [w for w in BANNED if w in text]
    if found:
        problems.append("금지 표현(규칙서 1장): " + ", ".join(found))
    left = [p for p in PLACEHOLDERS if p in text]
    if left:
        problems.append("빈칸이 남아 있어요: " + ", ".join(left))
    faq = count_faq(body)
    if faq > MAX_FAQ:
        problems.append(f"자주 묻는 질문은 {MAX_FAQ}개까지예요(규칙서 3장, 지금 {faq}개)")
    if REQUIRED_TAG not in tags:
        problems.append(f"태그에 #{REQUIRED_TAG} 가 없어요(규칙서 5장)")
    blue = body.count("{파랑:")
    if blue > MAX_BLUE:
        problems.append(f"파랑 강조는 {MAX_BLUE}곳까지예요(규칙서 7장, 지금 {blue}곳)")
    if md is not None and status_dir is not None:
        cp = checkpoint_problem(md, status_dir)
        if cp:
            problems.append(cp)
    return problems
