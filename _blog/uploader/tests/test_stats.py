"""통계 화면 저장: 화면 글자·사진을 남기고, 하루 한 번만 돈다."""
import json
from datetime import datetime

import pytest
from playwright.sync_api import sync_playwright

import naver_upload
from queue_state import StateFile
from stats_capture import capture


def test_capture_writes_text_and_shot(tmp_path):
    html = "data:text/html;charset=utf-8,<p>오늘 조회수 123</p>"
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(tmp_path / "prof"), headless=True)
        res = capture(ctx, "me", tmp_path / "out", settle_ms=10, pages=[("통계", html), ("깨짐", "http://127.0.0.1:9/")])
        ctx.close()
    assert res["통계"] == "ok" and res["깨짐"].startswith("오류")
    assert "오늘 조회수 123" in (tmp_path / "out" / "통계.txt").read_text(encoding="utf-8")
    assert (tmp_path / "out" / "통계.png").exists()
    assert json.loads((tmp_path / "out" / "받은시각.json").read_text(encoding="utf-8"))["results"]["통계"] == "ok"


def test_run_stats_once_a_day_after_9(tmp_path, monkeypatch):
    monkeypatch.setattr(naver_upload, "APP_HOME", tmp_path)
    calls = []
    monkeypatch.setattr("stats_capture.capture", lambda ctx, blog, out: calls.append(out) or {"x": "ok"})
    cfg = {"neo_root": str(tmp_path / "neo"), "blog_id": "me", "headless": True}
    sf = StateFile(tmp_path / "state.json")
    run = lambda h, d=10: naver_upload.run_stats(cfg, sf, now_fn=lambda: datetime(2026, 10, d, h), ctx_factory=object)
    assert run(8) is False and calls == []          # 9시 전엔 안 함
    assert run(10) is True and len(calls) == 1
    assert run(15) is False and len(calls) == 1      # 같은 날 또 안 함
    assert run(10, d=11) is True and len(calls) == 2
    assert str(calls[0]).endswith("상태/통계")


def test_capture_reads_iframe_and_links(tmp_path):
    inner = "<p>이번 주 조회수 777</p><a href='https://example.com/report'>리포트</a>"
    import urllib.parse
    html = "data:text/html;charset=utf-8," + urllib.parse.quote(
        f"<p>메뉴</p><iframe srcdoc=\"{inner}\"></iframe>")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(tmp_path / "prof"), headless=True)
        capture(ctx, "me", tmp_path / "out", settle_ms=300, pages=[("통계", html)])
        ctx.close()
    text = (tmp_path / "out" / "통계.txt").read_text(encoding="utf-8")
    assert "이번 주 조회수 777" in text and "https://example.com/report" in text
