"""글 파일(.md) 하나를 읽어 네이버에 넣을 형태로 바꾼다.

글 파일 모양:
    ---
    title: 제목
    status: ready          # draft(임시저장) | ready(올리기)
    tags: 태그1, 태그2
    category: 카테고리 이름  # 비우면 블로그 기본 카테고리
    publish_at: 2026-10-10 09:00   # 비우면 바로
    retry: (글쓰기 화면의 [다시 올리기]가 넣는 값)
    ---
    본문(마크다운)

머리말 해석을 직접 짠 이유: YAML 라이브러리는 'title: 1:2' 같은 값이나 따옴표를 멋대로 바꿔서
사장님이 쓴 제목이 달라질 수 있다. 여기선 '첫 번째 콜론 뒤 전부'를 그대로 값으로 쓴다.
"""
from __future__ import annotations

import hashlib
import html as htmllib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import markdown

STATUS_DRAFT = "draft"
STATUS_READY = "ready"
VALID_STATUS = (STATUS_DRAFT, STATUS_READY)
MAX_TAGS = 30  # 네이버 발행 창의 태그 칸 안내문이 '최대 30개'
DATETIME_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S")
KNOWN_KEYS = ("title", "status", "tags", "category", "publish_at", "retry")

# ![설명](images/파일.jpg) — 제목("...") 붙은 형태도 허용
IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+"[^"]*")?\s*\)')
# 사진은 저장소의 images/ 폴더 안 파일만. '..'·절대경로·외부 주소는 막는다(엉뚱한 파일이 올라가는 것 방지)
IMAGE_PATH_RE = re.compile(r"^images/[^/\\]+\.(?:jpe?g|png|gif|webp)$", re.IGNORECASE)
MD_EXTENSIONS = ["nl2br", "sane_lists", "fenced_code", "tables"]  # nl2br: 줄바꿈을 쓴 그대로 살림


@dataclass
class Segment:
    kind: str                # "html" 또는 "image"
    html: str = ""
    text: str = ""           # html 의 글자만(붙여넣기 확인용)
    image_path: str = ""     # 블로그 폴더 기준 경로 (images/xxx.jpg)


@dataclass
class Post:
    path: str
    title: str = ""
    status: str = ""
    tags: List[str] = field(default_factory=list)
    category: str = ""
    publish_at: Optional[datetime] = None
    retry: str = ""
    body: str = ""
    content_hash: str = ""
    errors: List[str] = field(default_factory=list)
    segments: List[Segment] = field(default_factory=list)
    source: str = ""        # 어느 출처에서 왔는지(github / neo)
    image_dir: str = ""     # 블로그_NEO 글의 그림 폴더

    @property
    def image_paths(self) -> List[str]:
        return [s.image_path for s in self.segments if s.kind == "image"]


def normalize_text(raw: str) -> str:
    """BOM·윈도우 줄바꿈 차이로 같은 글이 다른 글로 보이지 않게 맞춘다."""
    return raw.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()


def html_to_text(html: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def html_to_lines(html: str) -> List[str]:
    """붙여넣기가 안 먹을 때 한 줄씩 직접 치기 위한 글자 줄들(서식은 빠짐)."""
    marked = re.sub(r"(?i)<br\s*/?>|</(?:p|li|h[1-6]|pre|blockquote|tr)>", "\n", html)
    text = htmllib.unescape(re.sub(r"<[^>]+>", "", marked))
    return [line.strip() for line in text.split("\n") if line.strip()]


def split_front_matter(text: str):
    """(머리말 dict, 본문, 오류) — 머리말이 없거나 안 닫혔으면 오류."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text, "맨 위에 --- 로 시작하는 머리말(제목·상태)이 없어요"
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            break
    else:
        return {}, text, "머리말을 닫는 --- 줄이 없어요"
    meta = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        key = key.strip().lower()
        if sep and key in KNOWN_KEYS:
            meta[key] = value.strip()
    body = "\n".join(lines[end + 1:])
    return meta, body, ""


def parse_tags(value: str) -> List[str]:
    tags: List[str] = []
    for part in re.split(r"[,，]", value):
        tag = part.strip().lstrip("#").strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def parse_datetime(value: str) -> Optional[datetime]:
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def build_segments(body: str, errors: List[str]) -> List[Segment]:
    """본문을 [글, 사진, 글, ...] 순서 조각으로 나눈다. 사진은 네이버 에디터에 파일로 따로 넣어야 해서."""
    segments: List[Segment] = []
    pos = 0
    for m in IMAGE_RE.finditer(body):
        _append_text(segments, body[pos:m.start()])
        src = m.group(2)
        if src.startswith(("http://", "https://", "//")):
            errors.append(f"외부 주소 사진은 못 올려요(글쓰기 화면의 [사진 넣기]로 넣어 주세요): {src}")
        elif not IMAGE_PATH_RE.match(src):
            errors.append(f"사진 경로가 올바르지 않아요(images/파일.jpg 형식): {src}")
        else:
            segments.append(Segment(kind="image", image_path=src))
        pos = m.end()
    _append_text(segments, body[pos:])
    return segments


def _append_text(segments: List[Segment], chunk: str) -> None:
    if not chunk.strip():
        return
    html = markdown.markdown(chunk.strip("\n"), extensions=MD_EXTENSIONS)
    text = html_to_text(html)
    if text:
        segments.append(Segment(kind="html", html=html, text=text))


def parse_post(path: str, raw: str) -> Post:
    text = normalize_text(raw)
    post = Post(path=path, content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest())
    meta, body, fm_error = split_front_matter(text)
    if fm_error:
        post.errors.append(fm_error)
        return post

    status = meta.get("status", "").lower()
    if status in VALID_STATUS:
        post.status = status
    else:
        post.errors.append(f"status 는 draft 또는 ready 여야 해요 (지금: '{meta.get('status', '')}')")

    post.title = normalize_title(meta.get("title", ""))
    if not post.title:
        post.errors.append("제목(title)이 비어 있어요")

    post.tags = parse_tags(meta.get("tags", ""))
    if len(post.tags) > MAX_TAGS:
        post.errors.append(f"태그는 {MAX_TAGS}개까지예요 (지금 {len(post.tags)}개)")

    post.category = meta.get("category", "").strip()
    post.retry = meta.get("retry", "").strip()

    publish_at = meta.get("publish_at", "").strip()
    if publish_at:
        post.publish_at = parse_datetime(publish_at)
        if post.publish_at is None:
            post.errors.append(f"예약 시간 형식이 틀렸어요(예: 2026-10-10 09:00): {publish_at}")

    post.body = body.strip("\n")
    if not post.body.strip():
        post.errors.append("본문이 비어 있어요")
    else:
        post.segments = build_segments(post.body, post.errors)
        if not post.segments:
            post.errors.append("본문에 올릴 내용이 없어요")
    return post
