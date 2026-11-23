"""끝에서 끝까지(발행 없이) — 예시 코스 조립 → 팩트 게이트 → 검문소 → 발행기 세그먼트.

실제 발행(dry-run 포함)은 맥·네이버 로그인이 있어야 해서 여기서 하지 않는다.
대신 발행기가 읽는 단계까지는 전부 이 시험에서 지나간다 — 형식이 어긋나면 발행 전에 멈춘다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import fact_gate
import neo_source
from blogpost import Post
from course_compose import compose
from course_helpers import sample_course
from queue_state import StateFile

NEO = Path(__file__).resolve().parents[2] / "neo_tools"
EXAMPLE = Path(__file__).resolve().parents[2] / "courses" / "20261123_osan-segyo_example"


def _run_checkpoint(md_path: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(NEO / "검문소.py"), str(md_path)],
                          capture_output=True, text=True)


def test_example_course_passes_fact_gate():
    course = json.loads((EXAMPLE / "course.json").read_text(encoding="utf-8"))
    rep = fact_gate.check(course)
    assert rep["BLOCK"] == 0, rep["블록"]


def test_example_course_composes_and_passes_checkpoint(tmp_path):
    course = json.loads((EXAMPLE / "course.json").read_text(encoding="utf-8"))
    rep = compose(course)
    md = tmp_path / "완성본.md"
    md.write_text(rep.markdown, encoding="utf-8")
    img = tmp_path / "이미지"
    img.mkdir()
    for f in (EXAMPLE / "이미지").iterdir():
        (img / f.name).write_bytes(f.read_bytes())
    r = _run_checkpoint(md, tmp_path)
    assert "걸림 0" in r.stdout, r.stdout
    assert r.returncode == 0


def test_composed_body_turns_into_publishable_segments():
    rep = compose(sample_course())
    errs = []
    segs = neo_source.build_segments(rep.body, errs)
    assert not errs, errs
    kinds = {s.kind for s in segs}
    assert {"html", "place", "shorts", "ad", "link"} <= kinds
    post = Post(path="neo:x", title=rep.title, body=rep.body, tags=rep.tags,
                status="ready", segments=segs)
    assert all(s.text == "" or isinstance(s.text, str) for s in segs)
    # 발행기가 보는 사진 목록도 비어 있지 않다
    assert post.image_paths


def test_ad_only_body_without_disclosure_is_blocked_by_store(tmp_path):
    """제휴 카드가 있는데 고지가 지워진 글은 발행 전에 걸린다(내돈내산·수수료)."""
    rep = compose(sample_course())
    body = rep.body.replace("내돈내산 · 2026년 11월 16일 방문", "방문 기록").replace("수수료", "값")
    errs = []
    neo_source.build_segments(body, errs)
    assert not neo_source.has_disclosure(body)


def test_course_md_loads_through_neo_store(tmp_path):
    """블로그_NEO 폴더에 놓은 코스 완성본이 발행기 입력(Post)으로 그대로 읽히는지."""
    from neo_source import NeoStore
    rep = compose(sample_course())
    root = tmp_path / "블로그_NEO"
    (root / "초안" / "2026-11-23_테스트코스_이미지").mkdir(parents=True)
    (root / "상태").mkdir()
    md = root / "초안" / "2026-11-23_테스트코스_완성본.md"
    md.write_text(rep.markdown.replace("01_대표.jpg", "A.png").replace("02.jpg", "B.png")
                  .replace("03.jpg", "C.png").replace("04.jpg", "D.png"), encoding="utf-8")
    for n in ("A.png", "B.png", "C.png", "D.png"):
        (root / "초안" / "2026-11-23_테스트코스_이미지" / n).write_bytes(
            bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                          "0000000d49444154789c6360f8cf000000030101005d8a1e0b0000000049454e44ae426082"))
    (root / "상태" / "자동발행_대기.json").write_text(json.dumps(
        {"month": "2026년 11월", "posts": [{"id": "c1", "md": "초안/2026-11-23_테스트코스_완성본.md",
                                            "when": "2026-11-23 19:10", "kind": "new"}]},
        ensure_ascii=False), encoding="utf-8")
    (root / "상태" / "검문소_2026-11-23_테스트코스_완성본.json").write_text('{"걸림": 0}', encoding="utf-8")
    store = NeoStore(root)
    files = store.list_post_files()
    post = store.load_post(files[0])
    assert post.errors == [], post.errors
    assert post.tags[-1] == "서준의여행한입"
    assert {s.kind for s in post.segments} >= {"place", "image", "html", "ad", "link", "shorts"}
    assert len(post.image_paths) == 4
