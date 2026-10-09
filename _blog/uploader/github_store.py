"""글 저장소(GitHub) 읽기·쓰기. 표준 라이브러리만 써서 맥에 따로 깔 것을 줄였다."""
from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

API = "https://api.github.com"
STATE_COMMIT_MESSAGE = "블로그 올리기 기록 갱신"


class StoreError(Exception):
    pass


class GitHubStore:
    def __init__(self, repo: str, branch: str, token: str, blog_root: str = "_blog",
                 cache_dir: Optional[Path] = None, timeout: int = 20):
        self.repo = repo
        self.branch = branch
        self.token = token
        self.blog_root = blog_root.strip("/")
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.timeout = timeout

    @property
    def posts_dir(self) -> str:
        return f"{self.blog_root}/posts"

    @property
    def state_path(self) -> str:
        return f"{self.blog_root}/state.json"

    def _url(self, repo_path: str, with_ref: bool = True) -> str:
        url = f"{API}/repos/{self.repo}/contents/{urllib.parse.quote(repo_path, safe='/')}"
        if with_ref:
            url += "?ref=" + urllib.parse.quote(self.branch, safe="")
        return url

    def _request(self, method: str, url: str, body: Optional[dict] = None,
                 accept: str = "application/vnd.github+json") -> Tuple[int, bytes]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": accept,
            "User-Agent": "naver-blog-uploader",
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise StoreError(f"GitHub 연결 실패: {e}") from e

    def _json(self, status: int, raw: bytes, what: str):
        if status == 401:
            raise StoreError("GitHub 토큰이 틀렸거나 만료됐어요")
        if status == 403:
            raise StoreError(f"GitHub 권한 없음/요청 한도 초과 ({what})")
        if status >= 400:
            raise StoreError(f"GitHub 오류 {status} ({what})")
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError as e:
            raise StoreError(f"GitHub 응답 해석 실패 ({what})") from e

    def list_post_files(self) -> List[dict]:
        """[{path, sha}] — 이름이 _ 나 . 으로 시작하는 파일(예시·숨김)은 뺀다."""
        status, raw = self._request("GET", self._url(self.posts_dir))
        if status == 404:
            return []
        items = self._json(status, raw, "글 목록")
        if not isinstance(items, list):
            raise StoreError("글 폴더 자리에 파일이 있어요")
        out = []
        for it in items:
            name = it.get("name", "")
            if it.get("type") == "file" and name.endswith(".md") and not name.startswith(("_", ".")):
                out.append({"path": it["path"], "sha": it["sha"]})
        return sorted(out, key=lambda x: x["path"])

    def read_bytes(self, repo_path: str) -> bytes:
        status, raw = self._request("GET", self._url(repo_path), accept="application/vnd.github.raw")
        if status == 404:
            raise StoreError(f"파일이 없어요: {repo_path}")
        if status >= 400:
            self._json(status, raw, repo_path)
        return raw

    def read_post_text(self, repo_path: str, sha: str) -> str:
        """같은 내용(sha)이면 다시 받지 않는다 — 5분마다 도니까 요청 수를 줄인다."""
        cached = self.cache_dir / "posts" / f"{sha}.md" if self.cache_dir else None
        if cached and cached.exists():
            return cached.read_text(encoding="utf-8")
        text = self.read_bytes(repo_path).decode("utf-8")
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(text, encoding="utf-8")
        return text

    def download_image(self, rel_path: str, dest_dir: Path) -> Path:
        dest = Path(dest_dir) / Path(rel_path).name
        dest.write_bytes(self.read_bytes(f"{self.blog_root}/{rel_path}"))
        return dest

    def get_state(self) -> Tuple[dict, Optional[str]]:
        status, raw = self._request("GET", self._url(self.state_path))
        if status == 404:
            return {}, None
        meta = self._json(status, raw, "기록 파일")
        try:
            data = json.loads(base64.b64decode(meta.get("content", "")).decode("utf-8"))
        except ValueError:
            log.warning("저장소의 기록 파일이 깨져 있어 무시해요(맥 기록 기준으로 다시 씀)")
            data = {}
        return (data if isinstance(data, dict) else {}), meta.get("sha")

    def put_state(self, data: dict, sha: Optional[str]) -> Optional[str]:
        """글쓰기 화면이 상태를 보여 주려고 쓰는 사본. 실패해도 올리기는 맥 기록으로 계속 안전하다."""
        content = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        for _ in range(2):
            body = {"message": STATE_COMMIT_MESSAGE, "branch": self.branch,
                    "content": base64.b64encode(content.encode("utf-8")).decode("ascii")}
            if sha:
                body["sha"] = sha
            status, raw = self._request("PUT", self._url(self.state_path, with_ref=False), body)
            if status in (409, 422):  # 그사이 다른 곳에서 바뀜 → 최신 sha 로 한 번 더
                _, sha = self.get_state()
                continue
            return self._json(status, raw, "기록 저장").get("content", {}).get("sha")
        raise StoreError("기록 파일 저장 충돌이 계속돼요")
