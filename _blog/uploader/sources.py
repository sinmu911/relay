"""글 출처 묶기(글쓰기 화면 GitHub + 블로그 섹션 폴더)와 블로그에 이미 있는 글 확인."""
from __future__ import annotations

import difflib
import logging
import re
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Callable, Dict, List, Optional, Tuple

from github_store import StoreError

log = logging.getLogger(__name__)

FEED_URL = "https://rss.blog.naver.com/{blog_id}.xml"
SIMILAR = 0.92   # 이보다 비슷하면 같은 글로 본다(시리즈 '[두바이 ③]'·'[두바이 ④]'처럼 번호·주제가 다르면 안 걸림)


class MultiStore:
    """여러 출처를 하나처럼 보이게 한다. 한 출처가 고장 나도 다른 출처 글은 계속 올린다."""

    def __init__(self, stores: List):
        self.stores = stores
        self._owner: Dict[str, int] = {}
        self._remote_parts: List[dict] = [{} for _ in stores]

    def _owns(self, i: int, path: str) -> bool:
        owns = getattr(self.stores[i], "owns", None)
        return owns(path) if owns else True

    def list_post_files(self) -> List[dict]:
        out, failed = [], []
        self._owner = {}
        for i, st in enumerate(self.stores):
            try:
                files = st.list_post_files()
            except StoreError as e:
                log.warning("글 출처 %d 을(를) 못 읽음: %s", i, e)
                failed.append(e)
                continue
            for f in files:
                self._owner[f["path"]] = i
                out.append(dict(f, src=i))
        if failed and len(failed) == len(self.stores):
            raise failed[0]
        return out

    def load_post(self, f: dict):
        return self.stores[f["src"]].load_post(f)

    def fetch_images(self, post, dest_dir):
        return self.stores[self._owner[post.path]].fetch_images(post, dest_dir)

    def get_state(self) -> Tuple[dict, list]:
        merged: Dict[str, dict] = {}
        tokens = []
        for i, st in enumerate(self.stores):
            try:
                data, tok = st.get_state()
            except StoreError as e:
                log.warning("출처 %d 의 기록 사본을 못 읽음(맥 기록으로 계속): %s", i, e)
                data, tok = {}, None
            part = {k: v for k, v in (data.get("posts") or {}).items() if self._owns(i, k)}
            self._remote_parts[i] = part
            merged.update(part)
            tokens.append(tok)
        return {"posts": merged}, tokens

    def put_state(self, state: dict, tokens: list) -> None:
        for i, st in enumerate(self.stores):
            part = {k: v for k, v in state.get("posts", {}).items() if self._owns(i, k)}
            if part == self._remote_parts[i]:
                continue
            try:
                st.put_state({"version": 1, "posts": part, "meta": state.get("meta", {})}, tokens[i])
                self._remote_parts[i] = part
            except StoreError as e:
                log.warning("출처 %d 에 기록 사본을 못 씀(올리기 기록은 맥에 안전히 있음): %s", i, e)


def title_key(title: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFC", title).lower())


def find_similar(title: str, titles: List[str], threshold: float = SIMILAR) -> Optional[str]:
    key = title_key(title)
    if not key:
        return None
    for t in titles:
        other = title_key(t)
        if other and (other == key or difflib.SequenceMatcher(None, key, other).ratio() >= threshold):
            return t
    return None


class BlogFeed:
    """네이버 블로그 공개 RSS 로 이미 올라간 글 제목을 본다 — 사장님이 손으로 올린 글을 또 올리지 않게.
    한 번 실행에 한 번만 받는다."""

    def __init__(self, blog_id: str, fetch: Optional[Callable[[str], bytes]] = None, timeout: int = 15):
        self.url = FEED_URL.format(blog_id=blog_id)
        self._fetch = fetch or self._http
        self.timeout = timeout
        self._titles: Optional[List[str]] = None

    def _http(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 naver-blog-uploader"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise StoreError(f"블로그 글 목록(RSS)을 못 받음: {e}") from e

    def titles(self) -> List[str]:
        if self._titles is None:
            raw = self._fetch(self.url)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError as e:
                raise StoreError(f"블로그 글 목록(RSS) 해석 실패: {e}") from e
            self._titles = [(t.text or "").strip() for item in root.iter("item") for t in item.findall("title")]
        return self._titles
