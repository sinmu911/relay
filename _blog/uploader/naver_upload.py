#!/usr/bin/env python3
"""네이버 블로그 자동 올리기 — 맥에서 5분마다 돈다.

  python naver_upload.py login               처음 한 번(또는 로그인 풀렸을 때): 네이버 로그인 창
  python naver_upload.py run                 올릴 글이 있으면 올림 (자동 실행이 이걸 부름)
  python naver_upload.py run --dry-run       시험: 발행 직전까지만 채우고 화면을 logs 폴더에 저장
  python naver_upload.py run --post 경로      그 글 하나만
  python naver_upload.py status              글마다 지금 상태 보기
"""
from __future__ import annotations

import argparse
import contextlib
import json
import logging
import logging.handlers
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from blogpost import Post, parse_post  # noqa: E402
from github_store import GitHubStore, StoreError  # noqa: E402
from queue_state import (ACTION_DUPLICATE, ACTION_INVALID, ACTION_UPLOAD, DUPLICATE, FAILED,  # noqa: E402
                         INVALID, NEEDS_CHECK, PUBLISHED, PUBLISHING, RunLock, StateError, StateFile,
                         decide, merge_remote, now_str, recover_interrupted, taken_titles)

log = logging.getLogger("naver_upload")

APP_HOME = Path(os.environ.get("NAVER_BLOG_UPLOADER_HOME", "~/.naver-blog-uploader")).expanduser()
LOGIN_ALERT_EVERY = timedelta(hours=6)  # 로그인 풀림 알림을 5분마다 띄우면 시끄러워서
DEFAULTS = {
    "repo": "sinmu911/relay",
    "branch": "main",
    "blog_root": "_blog",
    "headless": False,
    "max_attempts": 3,
    "max_posts_per_run": 1,   # 한꺼번에 여러 편 올리면 네이버가 이상 행동으로 볼 수 있어 5분에 한 편
    "notify": True,
}


class ConfigError(Exception):
    pass


def load_config(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"설정 파일이 없어요: {path} (setup_mac.sh install 을 먼저 실행)")
    try:
        user = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ConfigError(f"설정 파일을 못 읽어요: {e}") from e
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in user.items() if not k.startswith("_")})
    cfg["github_token"] = os.environ.get("BLOG_GITHUB_TOKEN") or cfg.get("github_token", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,30}", str(cfg.get("blog_id", ""))):
        raise ConfigError("설정의 blog_id 에 네이버 블로그 아이디(영문/숫자)를 넣어 주세요")
    if not re.fullmatch(r"(github_pat_|ghp_)[A-Za-z0-9_]{20,}", str(cfg["github_token"])):
        raise ConfigError("설정의 github_token 에 GitHub 토큰을 넣어 주세요")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", str(cfg.get("repo", ""))):
        raise ConfigError("설정의 repo 는 '주인/저장소' 형식이어야 해요")
    for key in ("max_attempts", "max_posts_per_run"):
        if not isinstance(cfg[key], int) or cfg[key] < 1:
            raise ConfigError(f"설정의 {key} 는 1 이상 숫자여야 해요")
    return cfg


def mac_notify(title: str, message: str) -> None:
    """맥 화면 오른쪽 위 알림. 맥이 아니거나 실패해도 올리기에는 영향 없음."""
    if sys.platform != "darwin":
        return

    def q(s: str) -> str:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    script = f"display notification {q(message[:200])} with title {q('네이버 블로그')} subtitle {q(title)}"
    try:
        subprocess.run(["osascript", "-e", script], timeout=10, check=False, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass


def _record(post: Post, blob_sha: str, status: str, now: datetime, prev: Optional[dict] = None,
            **extra) -> dict:
    prev = prev or {}
    rec = {"status": status, "title": post.title, "hash": post.content_hash, "blob_sha": blob_sha,
           "at": now_str(now), "retry": prev.get("retry", ""), "attempts": prev.get("attempts", 0),
           "error": "", "url": prev.get("url", "")}
    rec.update(extra)
    return rec


class Runner:
    def __init__(self, cfg: dict, store, state_file: StateFile, lock: RunLock,
                 publisher_factory: Callable, notify: Callable[[str, str], None],
                 now_fn: Callable[[], datetime] = datetime.now):
        self.cfg = cfg
        self.store = store
        self.state_file = state_file
        self.lock = lock
        self.publisher_factory = publisher_factory
        self.notify = notify
        self.now_fn = now_fn

    def run(self, dry_run: bool = False, only_path: Optional[str] = None) -> List[str]:
        """한 바퀴. 돌려주는 값은 시험·로그용 사건 목록."""
        if not self.lock.acquire():
            log.info("다른 실행이 아직 돌고 있어 이번엔 건너뜀")
            return ["locked"]
        try:
            return self._run(dry_run, only_path)
        finally:
            self.lock.release()

    def _run(self, dry_run: bool, only_path: Optional[str]) -> List[str]:
        events: List[str] = []
        state = self.state_file.load()   # 깨졌으면 StateError — 두 번 올리기 위험이라 여기서 멈춤
        try:
            remote, remote_sha = self.store.get_state()
            files = self.store.list_post_files()
        except StoreError as e:
            log.warning("글 목록을 못 가져와서 다음에 다시: %s", e)
            return ["store_error"]
        state = merge_remote(state, remote)
        now = self.now_fn()
        for path in recover_interrupted(state, now):
            events.append(f"recovered:{path}")
            self.notify("확인 필요", f"{state['posts'][path].get('title', path)} — 올리던 중 멈췄어요. 블로그를 확인해 주세요.")
        self.state_file.save(state)

        uploads = 0
        with contextlib.ExitStack() as stack:
            publisher = None
            for f in files:
                if only_path and f["path"] != only_path:
                    continue
                try:
                    post = parse_post(f["path"], self.store.read_post_text(f["path"], f["sha"]))
                except (StoreError, UnicodeDecodeError) as e:
                    log.warning("글 파일을 못 읽음 %s: %s", f["path"], e)
                    continue
                rec = state["posts"].get(post.path)
                d = decide(post, rec, now, taken_titles(state), self.cfg["max_attempts"])
                log.info("%s → %s %s", post.path, d.action, d.reason)
                if d.action == ACTION_INVALID:
                    if not rec or rec.get("status") != INVALID or rec.get("hash") != post.content_hash:
                        state["posts"][post.path] = _record(post, f["sha"], INVALID, now, rec, error=d.reason)
                        self.notify("글 형식 오류", f"{post.title or post.path}: {d.reason}")
                        events.append(f"invalid:{post.path}")
                elif d.action == ACTION_DUPLICATE:
                    if not rec or rec.get("status") != DUPLICATE or rec.get("hash") != post.content_hash:
                        state["posts"][post.path] = _record(post, f["sha"], DUPLICATE, now, rec, error=d.reason)
                        self.notify("같은 제목", f"{post.title}: {d.reason}")
                        events.append(f"duplicate:{post.path}")
                elif d.action == ACTION_UPLOAD:
                    if uploads >= self.cfg["max_posts_per_run"]:
                        events.append(f"later:{post.path}")
                        continue
                    uploads += 1
                    if publisher is None:
                        try:
                            publisher = stack.enter_context(self.publisher_factory())
                        except Exception as e:  # noqa: BLE001 — 브라우저 못 띄움(설치 안 됨·창 열려 있음 등): 글은 손대지 않고 다음에
                            log.error("브라우저를 못 띄워서 다음에 다시: %s", e)
                            events.append("browser_error")
                            break
                    events.append(self._upload_one(publisher, state, post, f["sha"], dry_run))
                    if events[-1].startswith("login:"):
                        break
                self.state_file.save(state)
        self.state_file.save(state)

        if state != remote:
            try:
                self.store.put_state(state, remote_sha)
            except StoreError as e:
                log.warning("저장소에 상태 사본을 못 씀(올리기 기록은 맥에 안전히 있음): %s", e)
        return events

    def _upload_one(self, publisher, state: dict, post: Post, blob_sha: str, dry_run: bool) -> str:
        from naver_editor import NotLoggedInError  # 브라우저 라이브러리는 실제로 올릴 때만 불러온다

        prev = state["posts"].get(post.path) or {}
        same_try = (prev.get("status") == FAILED and prev.get("hash") == post.content_hash
                    and prev.get("retry", "") == post.retry)
        attempts = (prev.get("attempts", 0) if same_try else 0) + 1

        def mark_publishing() -> None:
            state["posts"][post.path] = _record(post, blob_sha, PUBLISHING, self.now_fn(), prev,
                                                retry=post.retry, attempts=attempts)
            try:
                self.state_file.save(state)
            except BaseException:
                # 기록을 못 남겼으면 발행도 안 누른다. 메모리 기록도 되돌려 '안 누름(실패)'으로 처리되게.
                if prev:
                    state["posts"][post.path] = prev
                else:
                    state["posts"].pop(post.path, None)
                raise

        with tempfile.TemporaryDirectory(prefix="naver-blog-") as tmp:
            try:
                images = {p: self.store.download_image(p, Path(tmp)) for p in post.image_paths}
                url = publisher.publish(post, images, mark_publishing, dry_run=dry_run)
            except NotLoggedInError:
                self._login_alert(state)
                return f"login:{post.path}"
            except Exception as e:  # noqa: BLE001 — 어떤 오류든 '발행을 눌렀는지'는 기록으로 판단해야 해서 다 받는다
                cur = state["posts"].get(post.path) or {}
                if cur.get("status") == PUBLISHING:
                    state["posts"][post.path] = dict(cur, status=NEEDS_CHECK, at=now_str(self.now_fn()),
                                                     error=f"발행 뒤 확인 실패: {e}")
                    self.notify("확인 필요", f"{post.title} — 올라갔는지 블로그를 확인해 주세요.")
                    log.error("발행 뒤 확인 실패 %s: %s", post.path, e)
                    return f"needs_check:{post.path}"
                state["posts"][post.path] = _record(post, blob_sha, FAILED, self.now_fn(), prev,
                                                    retry=post.retry, attempts=attempts, error=str(e)[:300])
                left = self.cfg["max_attempts"] - attempts
                self.notify("올리기 실패", f"{post.title} — {str(e)[:80]}" + (f" (다시 시도 {left}번 남음)" if left > 0 else ""))
                log.error("올리기 실패 %s (%d번째): %s", post.path, attempts, e)
                return f"failed:{post.path}"
        if dry_run:
            self.notify("시험 실행 끝", f"{post.title} — 발행 직전에서 멈췄어요(logs 폴더 화면 확인).")
            return f"dryrun:{post.path}"
        state["posts"][post.path] = _record(post, blob_sha, PUBLISHED, self.now_fn(), prev,
                                            retry=post.retry, attempts=attempts, url=url)
        self.notify("올렸어요", post.title)
        log.info("올림 %s → %s", post.path, url)
        return f"published:{post.path}"

    def _login_alert(self, state: dict) -> None:
        meta = state.setdefault("meta", {})
        last = meta.get("login_alert_at", "")
        now = self.now_fn()
        try:
            recent = bool(last) and now - datetime.strptime(last, "%Y-%m-%d %H:%M:%S") < LOGIN_ALERT_EVERY
        except ValueError:
            recent = False
        if not recent:
            meta["login_alert_at"] = now_str(now)
            self.notify("로그인 필요", "네이버 로그인이 풀렸어요. 터미널에서 login 을 다시 해 주세요.")
        log.error("네이버 로그인이 풀려서 올리기를 멈춤")


def print_status(cfg: dict, store, state_file: StateFile) -> None:
    state = merge_remote(state_file.load(), store.get_state()[0])
    now = datetime.now()
    for f in store.list_post_files():
        post = parse_post(f["path"], store.read_post_text(f["path"], f["sha"]))
        rec = state["posts"].get(post.path) or {}
        d = decide(post, rec, now, taken_titles(state), cfg["max_attempts"])
        extra = rec.get("url") or rec.get("error") or ""
        print(f"{post.path}\n  제목: {post.title}\n  기록: {rec.get('status', '-')} {rec.get('at', '')}"
              f"\n  다음 실행: {d.action} {d.reason}\n  {extra}".rstrip())


def setup_logging(verbose: bool) -> None:
    (APP_HOME / "logs").mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.handlers.RotatingFileHandler(APP_HOME / "logs" / "uploader.log", maxBytes=1_000_000,
                                              backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(fh)
    root.addHandler(sh)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="네이버 블로그 자동 올리기")
    ap.add_argument("--config", type=Path, default=APP_HOME / "config.json")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="네이버 로그인 창 열기")
    r = sub.add_parser("run", help="올릴 글이 있으면 올리기")
    r.add_argument("--dry-run", action="store_true", help="발행 직전까지만(시험)")
    r.add_argument("--post", help="이 글 하나만 (예: _blog/posts/2026-10-09-120000.md)")
    sub.add_parser("status", help="글별 상태")
    args = ap.parse_args(argv)
    setup_logging(args.verbose)

    if args.cmd == "login":
        from naver_editor import interactive_login
        return 0 if interactive_login(APP_HOME / "profile") else 1

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        log.error("%s", e)
        return 2
    store = GitHubStore(cfg["repo"], cfg["branch"], cfg["github_token"], cfg["blog_root"],
                        cache_dir=APP_HOME / "cache")
    state_file = StateFile(APP_HOME / "state.json")

    def notify(title: str, message: str) -> None:
        log.info("[알림] %s: %s", title, message)
        if cfg["notify"]:
            mac_notify(title, message)

    try:
        if args.cmd == "status":
            print_status(cfg, store, state_file)
            return 0

        def publisher_factory():
            from naver_editor import NaverPublisher
            return NaverPublisher(cfg["blog_id"], APP_HOME / "profile", APP_HOME / "logs",
                                  headless=bool(cfg["headless"]))

        runner = Runner(cfg, store, state_file, RunLock(APP_HOME / "run.lock"), publisher_factory, notify)
        events = runner.run(dry_run=args.dry_run, only_path=args.post)
        log.info("끝: %s", ", ".join(events) or "올릴 글 없음")
        return 0
    except StateError as e:
        notify("멈춤", "올리기 기록 파일이 깨져서 멈췄어요. 로그를 확인해 주세요.")
        log.error("%s", e)
        return 2
    except StoreError as e:
        log.error("%s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
