"""로그인 점검 — 네이버 로그인이 언제·왜 풀리는지 기록하고, 풀리기 전에 미리 알린다.

사장님 요청(10-13): "로그인 유지 점검". 로그인은 지금처럼 사장님이 직접 한다(자동 로그인 없음).
하루 한 번(9시 뒤), 또는 올리다가 로그인이 풀렸을 때 바로:
  - 저장된 로그인 쿠키(NID_AUT·NID_SES)가 있는지, 만료일이 언제인지 본다(값은 안 봄·안 남김).
  - 글쓰기 화면이 열리는지(진짜 올릴 때와 같은 길) 확인한다.
  - 결과를 상태/로그인_기록.json 에 남긴다 → 블로그 보조가 드라이브에서 보고 원인을 찾는다.
  - 만료가 3일 안이면 "곧 풀려요" 알림(하루 한 번).
풀린 이유 짐작:
  - 쿠키 만료일이 지남 → "기간 끝"
  - 창 닫으면 지워지는 쿠키였음 → "로그인 상태 유지 꺼짐"
  - 쿠키가 아예 없거나, 있는데도 로그인 화면 → "네이버가 로그아웃시킴(비밀번호 변경·다른 기기·보안 확인 등)"
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Optional

log = logging.getLogger(__name__)

RECORD_REL = Path("상태") / "로그인_기록.json"
WARN_BEFORE = timedelta(days=3)
KEEP = 30


def cookie_summary(cookies: Dict[str, float], now: datetime) -> dict:
    """{쿠키이름: 만료(epoch, 0 이하면 창 닫으면 지워짐)} → 기록용 요약."""
    out = {}
    for name, exp in sorted(cookies.items()):
        if not exp or exp <= 0:
            out[name] = "창 닫으면 지워짐"
        else:
            out[name] = datetime.fromtimestamp(exp).strftime("%Y-%m-%d %H:%M")
    return out


def guess_cause(cookies: Dict[str, float], now: datetime, need=("NID_AUT", "NID_SES")) -> str:
    missing = [n for n in need if n not in cookies]
    if missing and len(missing) == len(need):
        return "로그인 쿠키가 없음 — 네이버가 로그아웃시켰거나(비밀번호 변경·다른 기기·보안 확인) 로그인을 안 함"
    if any((cookies.get(n) or 0) <= 0 for n in need if n in cookies):
        return "'로그인 상태 유지'가 꺼진 로그인 — login 때 꼭 체크"
    if any(0 < (cookies.get(n) or 0) <= now.timestamp() for n in need):
        return "쿠키 기간이 끝남"
    if missing:
        return f"쿠키 일부 없음({', '.join(missing)}) — 네이버가 로그아웃시킴"
    return "쿠키는 있는데 로그인 화면 — 네이버가 로그아웃시킴(비밀번호 변경·다른 기기·보안 확인 등)"


def soonest_expiry(cookies: Dict[str, float]) -> Optional[datetime]:
    exps = [e for e in cookies.values() if e and e > 0]
    return datetime.fromtimestamp(min(exps)) if exps else None


def check(cfg: dict, state: dict, publisher_factory, notify: Callable[[str, str], None],
          now: datetime, force: bool = False) -> Optional[dict]:
    """점검 하나. 오늘 이미 했고 force 가 아니면 None. state["meta"] 를 고친다(저장은 부르는 쪽)."""
    meta = state.setdefault("meta", {})
    today = now.strftime("%Y-%m-%d")
    hist = meta.setdefault("login_log", [])
    if force and hist and hist[-1].get("로그인") == "풀림":
        force = False   # 풀린 건 이미 기록함 — 5분마다 다시 열지 않게
    if not force and (now.hour < 9 or meta.get("login_check_date") == today):
        return None
    with publisher_factory() as pub:
        cookies = pub.auth_cookies()
        ok = pub.check_login()
    entry = {"at": now.strftime("%Y-%m-%d %H:%M:%S"), "로그인": "됨" if ok else "풀림",
             "쿠키": cookie_summary(cookies, now)}
    exp = soonest_expiry(cookies)
    if exp:
        entry["남은 날"] = max(0, (exp - now).days)
    if not ok:
        entry["이유 짐작"] = guess_cause(cookies, now)
        if meta.get("login_ok_since"):
            entry["유지된 기간"] = f"{meta['login_ok_since']} 부터"
        meta.pop("login_ok_since", None)
    else:
        meta.setdefault("login_ok_since", entry["at"])
        if exp and exp - now <= WARN_BEFORE and meta.get("login_warn_date") != today:
            meta["login_warn_date"] = today
            notify("로그인 곧 풀려요", f"{exp:%m-%d %H시}쯤 네이버 로그인이 끝나요. 시간 될 때 login 해 주세요.")
    meta["login_check_date"] = today
    hist.append(entry)
    del hist[:-KEEP]
    _write_record(cfg, meta)
    log.info("로그인 점검: %s", entry)
    return entry


def _write_record(cfg: dict, meta: dict) -> None:
    if not cfg.get("neo_root"):
        return
    path = Path(os.path.expanduser(str(cfg["neo_root"]))) / RECORD_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "_설명": "맥이 하루 한 번 남기는 네이버 로그인 점검 기록(쿠키 값은 안 남김, 이름·만료일만).",
            "로그인 유지 시작": meta.get("login_ok_since", ""),
            "기록": meta.get("login_log", [])}, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:
        log.warning("로그인 기록을 드라이브에 못 씀: %s", e)
