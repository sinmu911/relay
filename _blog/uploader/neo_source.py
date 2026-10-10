"""블로그 섹션(블로그_NEO 폴더)이 만든 완성본을 자동 발행 대상으로 읽는다.

블로그 섹션이 이미 만드는 파일 형식을 그대로 쓴다(형식을 바꾸게 하지 않는다):
  - 자동 발행 목록: 상태/자동발행_대기.json — 월간묶음_*.json 과 같은 모양
        {"month": "2026년 10월",
         "posts": [{"id": "③", "md": "초안/2026-10-07_아부다비하루코스_완성본.md",
                    "when": "10/15(목) 19:10"  또는  "2026-10-15 19:10",
                    "kind": "new", "category": "(선택)", "images": "(선택) 그림 폴더", "retry": "(선택)"}]}
    이 목록에 넣은 글만 자동으로 올린다. 월간묶음(사장님 손 발행용)은 건드리지 않는다 —
    같은 글을 사장님도 손으로 예약하면 두 번 올라가므로 둘 중 하나만 쓴다.
  - 완성본(.md): ===== 제목/본문/태그 ===== 머리줄. 본문 안 【그림 N】 파일명.png · ■ 소제목 · ▶ 인용
    · **굵게** · {파랑: 문구}. '(발행 후 링크)' 자리표시는 뺀다(블로그 섹션 10-09 결정과 같음).
  - 그림 폴더: 완성본 옆 '<날짜>_<주제>_이미지/' (완성본 이름의 '_완성본' 앞부분 + '_이미지')
kind 가 edit(기존 글 본문 교체)인 글은 아직 자동으로 하지 않는다 — 기존 글을 덮어쓰는 일이라 위험해서.
"""
from __future__ import annotations

import hashlib
import html as htmllib
import json
import logging
import os
import re
import shutil
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from blogpost import MAX_TAGS, STATUS_READY, Post, Segment, html_to_text, normalize_title
from github_store import StoreError

log = logging.getLogger(__name__)

KEY_PREFIX = "neo:"
QUEUE_REL = "상태/자동발행_대기.json"
MIRROR_REL = "상태/자동발행_기록.json"
BLUE = "#0075c8"
SECTION_RE = re.compile(r"^={5,}\n([^\n=][^\n]*)\n={5,}$", re.M)   # 블로그 섹션 도구들과 같은 머리줄 규칙
IMAGE_LINE_RE = re.compile(r"^\s*【그림\s*(\w+)】\s*(\S+)\s*$")
PREAMBLE_FOLDER_RE = re.compile(r"폴더\s*`([^`]+)`")
WHEN_SHORT_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})\s*(?:\([^)]*\))?\s*(\d{1,2}):(\d{2})\s*$")
WHEN_FULL_RE = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})")
MONTH_RE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월")
URL_RE = re.compile(r"https?://[^\s<]+")


def nfc(s: str) -> str:
    """맥 파일 이름은 한글 자모가 풀린 꼴(NFD)일 때가 있다. 같은 글이 다른 글로 보이면 두 번 올라가서 맞춘다."""
    return unicodedata.normalize("NFC", s)


def parse_when(value: str, month_hint: str = "") -> Optional[datetime]:
    m = WHEN_FULL_RE.match(value or "")
    if m:
        y, mo, d, h, mi = map(int, m.groups())
    else:
        m = WHEN_SHORT_RE.match(value or "")
        hint = MONTH_RE.search(month_hint or "")
        if not m or not hint:
            return None
        mo, d, h, mi = map(int, m.groups())
        y, hint_month = int(hint.group(1)), int(hint.group(2))
        if mo < hint_month - 6:      # 12월 묶음에 1월 글이 들어간 경우
            y += 1
    try:
        return datetime(y, mo, d, h, mi)
    except ValueError:
        return None


def split_sections(text: str) -> Tuple[str, Dict[str, str]]:
    heads = list(SECTION_RE.finditer(text))
    preamble = text[:heads[0].start()] if heads else text
    secs: Dict[str, str] = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        name = m.group(1).strip().split()[0]          # '태그 (10개)' → '태그'
        secs.setdefault(name, text[m.end():end].strip("\n"))
    return preamble, secs


def render_inline(line: str) -> str:
    out = htmllib.escape(line, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"\{파랑:\s*(.+?)\}", r'<span style="color:%s">\1</span>' % BLUE, out)

    def link(m: "re.Match[str]") -> str:
        url = m.group(0)
        tail = ""
        while url and url[-1] in ").,!?'\"":
            tail = url[-1] + tail
            url = url[:-1]
        return f'<a href="{url}">{url}</a>{tail}'
    return URL_RE.sub(link, out)


def render_block(lines: List[str]) -> str:
    """사장님이 앱에 붙여넣을 때와 같은 모양: 한 줄 = 한 문단, 빈 줄 = 빈 문단."""
    parts = []
    for line in lines:
        s = line.rstrip()
        if not s.strip():
            parts.append("<p><br></p>")
        elif s.lstrip().startswith(("■", "▶")):   # 소제목·인용구는 굵게(기호는 글에 그대로 보이게 둔다)
            parts.append(f"<p><strong>{render_inline(s.strip())}</strong></p>")
        else:
            parts.append(f"<p>{render_inline(s)}</p>")
    return "".join(parts)


AI_NOTE_RE = re.compile(r"AI\s*(?:도움|로\s*만든|가\s*만든|로\s*정리|생성)")


def build_segments(body: str, errors: List[str]) -> List[Segment]:
    segments: List[Segment] = []
    buf: List[str] = []

    def flush() -> None:
        text = "\n".join(buf)
        text = re.sub(r"[ \t]*\(발행 후 링크\)", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip("\n")
        buf.clear()
        if text.strip():
            html = render_block(text.split("\n"))
            segments.append(Segment(kind="html", html=html, text=html_to_text(html)))

    for line in body.split("\n"):
        m = IMAGE_LINE_RE.match(line)
        if m:
            flush()
            name = m.group(2)
            if "/" in name or "\\" in name or name.startswith("."):
                errors.append(f"그림 파일 이름이 이상해요: {name}")
            else:
                segments.append(Segment(kind="image", image_path=nfc(name)))
            continue
        if re.fullmatch(r"={5,}", line.strip()):
            continue
        if AI_NOTE_RE.search(line):
            continue   # 사장님 방침: 'AI로 정리·AI 그림' 고지 문장은 올리지 않음
        buf.append(line)
    flush()
    return segments


class NeoStore:
    """맥에 동기화된 블로그_NEO 폴더를 글 출처로 쓴다(GitHub 없이)."""

    def __init__(self, root: Path, queue_rel: str = QUEUE_REL, mirror_rel: str = MIRROR_REL,
                 default_category: str = ""):
        self.root = Path(os.path.expanduser(str(root)))
        self.queue_path = self.root / queue_rel
        self.mirror_path = self.root / mirror_rel
        self.default_category = default_category
        self._month = ""

    @staticmethod
    def owns(path: str) -> bool:
        return path.startswith(KEY_PREFIX)

    # ── 목록 ─────────────────────────────────────────────
    def _resolve(self, md: str) -> Optional[Path]:
        """블로그 섹션이 적은 경로(절대·상대·다른 맥 사용자 경로)를 이 맥의 블로그_NEO 안 경로로."""
        md = nfc(str(md or "").strip())
        if not md:
            return None
        p = Path(md)
        if not p.is_absolute():
            p = self.root / p
        elif not p.exists() and "/블로그_NEO/" in md:
            p = self.root / md.split("/블로그_NEO/", 1)[1]
        p = Path(os.path.normpath(str(p)))
        root = Path(os.path.normpath(str(self.root)))
        if p != root and root not in p.parents:
            return None
        return p

    def _key(self, p: Path) -> str:
        return KEY_PREFIX + nfc(p.relative_to(Path(os.path.normpath(str(self.root)))).as_posix())

    def list_post_files(self) -> List[dict]:
        if not self.root.is_dir():
            raise StoreError(f"블로그_NEO 폴더가 없어요: {self.root}")
        if not self.queue_path.exists():
            return []
        try:
            data = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise StoreError(f"자동 발행 목록을 못 읽어요({self.queue_path.name}): {e}") from e
        posts = data.get("posts") if isinstance(data, dict) else None
        if not isinstance(posts, list):
            raise StoreError("자동 발행 목록에 posts 칸이 없어요")
        self._month = str(data.get("month", ""))
        out, seen = [], set()
        for entry in posts:
            if not isinstance(entry, dict):
                continue
            if entry.get("kind", "new") != "new":
                log.info("기존 글 수정(%s)은 자동 발행하지 않아요 — 직접 수정: %s", entry.get("id", ""), entry.get("md", ""))
                continue
            p = self._resolve(entry.get("md", ""))
            key = self._key(p) if p else KEY_PREFIX + "?" + nfc(str(entry.get("md", "")))
            if key in seen:
                log.warning("자동 발행 목록에 같은 글이 두 번 있어요(앞의 것만 씀): %s", key)
                continue
            seen.add(key)
            try:
                raw = p.read_bytes() if p and p.is_file() else b""
            except OSError:
                raw = b""
            sig = json.dumps([entry.get("when"), entry.get("category"), entry.get("images"),
                              entry.get("retry")], ensure_ascii=False).encode("utf-8")
            out.append({"path": key, "sha": hashlib.sha1(raw + b"\0" + sig).hexdigest(), "entry": entry,
                        "file": str(p) if p else ""})
        return out

    # ── 글 한 편 ──────────────────────────────────────────
    def load_post(self, f: dict) -> Post:
        entry = f["entry"]
        post = Post(path=f["path"], status=STATUS_READY, retry=str(entry.get("retry", "") or "").strip())
        post.source = "neo"
        p = Path(f["file"]) if f.get("file") else None
        if not p:
            post.errors.append(f"완성본 경로가 블로그_NEO 밖이거나 비었어요: {entry.get('md', '')}")
            return post
        try:
            text = nfc(p.read_text(encoding="utf-8").lstrip(chr(0xFEFF)).replace("\r\n", "\n"))
        except (OSError, UnicodeDecodeError) as e:
            post.errors.append(f"완성본을 못 읽어요: {p.name} ({e})")
            return post
        when = str(entry.get("when", "") or "")
        category = str(entry.get("category", "") or self.default_category).strip()
        post.content_hash = hashlib.sha256((text + "\0" + when + "\0" + category).encode("utf-8")).hexdigest()
        post.category = category
        post.publish_at = parse_when(when, self._month)
        if post.publish_at is None:
            post.errors.append(f"발행 시각(when)을 못 읽어요: '{when}' (예: 10/15(목) 19:10 또는 2026-10-15 19:10)")

        preamble, secs = split_sections(text)
        if "제목" not in secs or "본문" not in secs:
            post.errors.append("완성본에 ===== 제목 ===== / ===== 본문 ===== 칸이 없어요")
            return post
        title_lines = [line.strip() for line in secs["제목"].split("\n") if line.strip()]
        post.title = normalize_title(title_lines[0]) if title_lines else ""
        if not post.title:
            post.errors.append("제목이 비어 있어요")
        post.tags = []
        for tag in secs.get("태그", "").split():
            tag = tag.lstrip("#").strip()
            if tag and tag not in post.tags:
                post.tags.append(tag)
        if len(post.tags) > MAX_TAGS:
            post.errors.append(f"태그는 {MAX_TAGS}개까지예요 (지금 {len(post.tags)}개)")
        post.body = secs["본문"]
        post.segments = build_segments(post.body, post.errors)
        if not any(s.kind == "html" for s in post.segments):
            post.errors.append("본문 글이 비어 있어요")

        img_dir = self._image_dir(p, entry, preamble)
        post.image_dir = str(img_dir) if img_dir else ""
        if post.image_paths:
            if not img_dir or not img_dir.is_dir():
                post.errors.append(f"그림 폴더가 없어요: {img_dir or '(못 찾음)'}")
            else:
                names = {nfc(n): n for n in os.listdir(img_dir)}
                missing = [n for n in post.image_paths if n not in names]
                if missing:
                    post.errors.append("그림 파일이 없어요: " + ", ".join(missing))
        return post

    def _image_dir(self, md: Path, entry: dict, preamble: str) -> Optional[Path]:
        if entry.get("images"):
            return self._resolve(str(entry["images"]))
        m = PREAMBLE_FOLDER_RE.search(preamble)
        if m:
            cand = self._resolve(str(md.parent / m.group(1).strip().rstrip("/")))
            if cand and cand.is_dir():
                return cand
        prefix = md.stem.split("_완성본")[0]
        return md.parent / f"{prefix}_이미지"

    def fetch_images(self, post: Post, dest_dir: Path) -> Dict[str, Path]:
        src_dir = Path(getattr(post, "image_dir", "") or "")
        names = {nfc(n): n for n in os.listdir(src_dir)} if src_dir.is_dir() else {}
        out: Dict[str, Path] = {}
        for name in post.image_paths:
            if name not in names:
                raise StoreError(f"그림 파일이 없어요: {name}")
            dest = Path(dest_dir) / name
            shutil.copyfile(src_dir / names[name], dest)
            out[name] = dest
        return out

    # ── 기록 사본(블로그 섹션이 읽는 용) ─────────────────────────
    def get_state(self) -> Tuple[dict, Optional[str]]:
        if not self.mirror_path.exists():
            return {}, None
        try:
            data = json.loads(self.mirror_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("블로그_NEO 기록 사본이 깨져 있어 무시해요(맥 기록 기준으로 다시 씀)")
            return {}, None
        return (data if isinstance(data, dict) else {}), None

    def put_state(self, data: dict, sig: Optional[str]) -> None:
        """드라이브 동기화 폴더라 바뀐 게 있을 때만 쓴다(반복 쓰기 금지 규칙)."""
        mine = {k: v for k, v in data.get("posts", {}).items() if self.owns(k)}
        current, _ = self.get_state()
        if current.get("posts") == mine:
            return
        payload = {"version": 1, "posts": mine, "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "_설명": "맥 자동 발행기가 쓰는 기록 사본. 고치지 마세요(원본은 맥 ~/.naver-blog-uploader/state.json)."}
        self.mirror_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.mirror_path.parent), prefix=".자동발행_", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
            os.replace(tmp, self.mirror_path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
