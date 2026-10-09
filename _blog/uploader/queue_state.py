"""어떤 글을 올릴지 정하고, 올린 기록을 남긴다.

두 번 올리기 방지가 제일 중요하다:
- [발행] 확인 버튼을 누르기 '직전'에 기록을 publishing 으로 저장(디스크에 확실히 씀)한다.
- 다음 실행에서 publishing 이 남아 있으면 '눌렀는데 결과를 못 봤다'는 뜻이라 자동으로 다시 올리지 않고
  needs_check(확인 필요)로 바꾼다. 사장님이 글쓰기 화면에서 [다시 올리기]를 눌러야만 다시 올린다.
"""
from __future__ import annotations

import fcntl
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from blogpost import STATUS_READY, Post, normalize_title

PUBLISHING = "publishing"
PUBLISHED = "published"
FAILED = "failed"
NEEDS_CHECK = "needs_check"
INVALID = "invalid"
DUPLICATE = "duplicate"
# 같은 제목 검사에 쓰는 상태: 네이버에 올라갔거나 올라갔을 수 있는 글
MAYBE_ON_NAVER = (PUBLISHED, PUBLISHING, NEEDS_CHECK)

ACTION_UPLOAD = "upload"
ACTION_SKIP = "skip"
ACTION_WAIT = "wait"
ACTION_INVALID = "invalid"
ACTION_DUPLICATE = "duplicate"


class StateError(Exception):
    """기록 파일이 깨졌다 — 이 상태로 돌리면 이미 올린 글을 또 올릴 수 있어 멈춘다."""


@dataclass
class Decision:
    action: str
    reason: str = ""


def empty_state() -> dict:
    return {"version": 1, "posts": {}, "meta": {}}


def now_str(now: datetime) -> str:
    return now.strftime("%Y-%m-%d %H:%M:%S")


def is_explicit_retry(post: Post, rec: Optional[dict]) -> bool:
    """글쓰기 화면의 [다시 올리기](또는 목록의 retry 값)로 사장님이 직접 다시 올리라고 한 경우."""
    return bool(post.retry) and post.retry != (rec or {}).get("retry", "")


def decide(post: Post, rec: Optional[dict], now: datetime, taken_titles: Dict[str, str],
           max_attempts: int) -> Decision:
    rec = rec or {}
    st = rec.get("status")
    if st == PUBLISHED:
        return Decision(ACTION_SKIP, "이미 올림")
    if st == PUBLISHING:
        return Decision(ACTION_SKIP, "올리는 중 기록 있음")
    explicit_retry = is_explicit_retry(post, rec)
    if st in (NEEDS_CHECK, DUPLICATE) and not explicit_retry:
        return Decision(ACTION_SKIP, "확인 필요 — [다시 올리기]를 눌러야 다시 올림")
    if post.status == "draft":
        return Decision(ACTION_SKIP, "임시저장")  # 쓰다 만 글은 제목·본문이 비어도 오류로 안 친다
    if post.errors or post.status != STATUS_READY:
        return Decision(ACTION_INVALID, "; ".join(post.errors) or "status 확인 필요")
    if post.publish_at and post.publish_at > now:
        return Decision(ACTION_WAIT, "예약 " + post.publish_at.strftime("%m/%d %H:%M"))
    if (st == FAILED and not explicit_retry and rec.get("hash") == post.content_hash
            and rec.get("attempts", 0) >= max_attempts):
        return Decision(ACTION_SKIP, f"{max_attempts}번 실패 — 글을 고치거나 [다시 올리기]를 누르면 다시 시도")
    other = taken_titles.get(normalize_title(post.title))
    if other and other != post.path and not explicit_retry:
        return Decision(ACTION_DUPLICATE, f"같은 제목 글이 이미 있어요: {other}")
    return Decision(ACTION_UPLOAD)


def taken_titles(state: dict) -> Dict[str, str]:
    """제목 → 글 파일 경로 (네이버에 올라갔거나 올라갔을 수 있는 글만)."""
    out: Dict[str, str] = {}
    for path, rec in state["posts"].items():
        if rec.get("status") in MAYBE_ON_NAVER and rec.get("title"):
            out[normalize_title(rec["title"])] = path
    return out


def recover_interrupted(state: dict, now: datetime) -> list:
    """지난번 실행이 [발행] 확인을 누른 뒤 끝을 못 봤으면 확인 필요로 돌린다(자동 재시도 금지)."""
    recovered = []
    for path, rec in state["posts"].items():
        if rec.get("status") == PUBLISHING:
            rec["status"] = NEEDS_CHECK
            rec["error"] = "올리던 중 멈췄어요. 네이버 블로그에 올라갔는지 확인해 주세요."
            rec["at"] = now_str(now)
            recovered.append(path)
    return recovered


def merge_remote(local: dict, remote: dict) -> dict:
    """맥을 새로 설치해 기록이 날아가도, 저장소에 남은 기록으로 이미 올린 글을 알아본다.
    둘 다 있으면 맥의 기록이 기준(저장소 쪽은 맥이 쓴 사본이라서)."""
    merged = {"version": 1, "posts": dict(local.get("posts", {})), "meta": dict(local.get("meta", {}))}
    for path, rec in (remote or {}).get("posts", {}).items():
        if path not in merged["posts"] and isinstance(rec, dict):
            merged["posts"][path] = dict(rec)
    return merged


class StateFile:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return empty_state()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise StateError(f"기록 파일을 못 읽어요({self.path}): {e}") from e
        if not isinstance(data, dict) or not isinstance(data.get("posts"), dict):
            raise StateError(f"기록 파일 모양이 이상해요: {self.path}")
        data.setdefault("meta", {})
        data["version"] = 1
        return data

    def save(self, data: dict) -> None:
        """임시 파일에 쓰고 fsync 뒤 바꿔치기 — 쓰는 도중 꺼져도 기록이 반쪽이 되지 않게."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".state-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


class RunLock:
    """5분마다 도는 자동 실행과 손으로 돌린 실행이 겹치면 같은 글을 두 번 올릴 수 있어 잠근다."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._fd = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self._fd)
            self._fd = None
            return False
        return True

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None
