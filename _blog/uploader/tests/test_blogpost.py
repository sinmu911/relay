from datetime import datetime

from blogpost import parse_post

OK = """---
title:  첫 글: 테스트
status: ready
tags: #화물, 운송 , 화물,
category: 일상
publish_at: 2026-10-10 09:00
---
첫 줄 **굵게**
둘째 줄

![사진](images/a.jpg)

- 목록1
- 목록2
"""


def test_normal_post():
    p = parse_post("_blog/posts/a.md", OK)
    assert p.errors == []
    assert p.title == "첫 글: 테스트"          # 콜론 뒤 값 그대로
    assert p.status == "ready"
    assert p.tags == ["화물", "운송"]          # # 제거·중복 제거·빈 값 제거
    assert p.category == "일상"
    assert p.publish_at == datetime(2026, 10, 10, 9, 0)
    kinds = [s.kind for s in p.segments]
    assert kinds == ["html", "image", "html"]
    assert "<strong>굵게</strong>" in p.segments[0].html and "<br" in p.segments[0].html
    assert p.image_paths == ["images/a.jpg"]
    assert "<li>목록1</li>" in p.segments[2].html


def test_crlf_and_bom_give_same_hash():
    a = parse_post("x.md", OK)
    b = parse_post("x.md", "﻿" + OK.replace("\n", "\r\n"))
    assert a.content_hash == b.content_hash and b.errors == []


def test_missing_front_matter():
    p = parse_post("x.md", "그냥 본문")
    assert p.errors and "머리말" in p.errors[0]


def test_unclosed_front_matter():
    p = parse_post("x.md", "---\ntitle: a\nstatus: ready\n본문")
    assert any("닫는" in e for e in p.errors)


def test_empty_title_and_body():
    p = parse_post("x.md", "---\ntitle:\nstatus: ready\n---\n\n  \n")
    assert any("제목" in e for e in p.errors) and any("본문" in e for e in p.errors)


def test_bad_status_and_date():
    p = parse_post("x.md", "---\ntitle: a\nstatus: 올려\npublish_at: 내일\n---\n본문")
    assert any("status" in e for e in p.errors) and any("예약" in e for e in p.errors)
    assert p.status == ""


def test_status_case_insensitive_and_datetime_local_format():
    p = parse_post("x.md", "---\ntitle: a\nstatus: READY\npublish_at: 2026-10-10T09:30\n---\n본문")
    assert p.errors == [] and p.status == "ready" and p.publish_at == datetime(2026, 10, 10, 9, 30)


def test_image_path_rules():
    body = "---\ntitle: a\nstatus: ready\n---\n![](https://x.com/a.jpg)\n![](../secret.jpg)\n![](images/sub/a.jpg)\n![](images/a.exe)\n![](images/ok.PNG)"
    p = parse_post("x.md", body)
    assert sum("외부 주소" in e for e in p.errors) == 1
    assert sum("경로" in e for e in p.errors) == 3
    assert p.image_paths == ["images/ok.PNG"]


def test_too_many_tags():
    tags = ", ".join(f"t{i}" for i in range(31))
    p = parse_post("x.md", f"---\ntitle: a\nstatus: ready\ntags: {tags}\n---\n본문")
    assert any("태그" in e for e in p.errors)


def test_body_with_hr_line_kept():
    p = parse_post("x.md", "---\ntitle: a\nstatus: ready\n---\n위\n\n---\n\n아래")
    assert p.errors == [] and "아래" in p.segments[-1].text and "<hr" in p.segments[-1].html


def test_image_only_body():
    p = parse_post("x.md", "---\ntitle: a\nstatus: ready\n---\n![](images/a.jpg)")
    assert p.errors == [] and [s.kind for s in p.segments] == ["image"]
