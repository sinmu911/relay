"""하루 한 번 블로그 통계·애드포스트 화면을 열어 글자와 화면 사진을 블로그_NEO/상태/통계/ 에 남긴다.
읽기만 한다(아무것도 누르거나 바꾸지 않음). 비서실장(클라우드)이 드라이브에서 읽어 분석한다.
드라이브 반복 쓰기를 줄이려고 날짜별로 쌓지 않고 '최신' 한 벌만 덮어쓴다."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

log = logging.getLogger(__name__)

PAGES: List[Tuple[str, str]] = [
    ("블로그통계", "https://admin.blog.naver.com/{blog_id}/stat/today"),
    ("크리에이터어드바이저", "https://creator-advisor.naver.com/naver_blog/{blog_id}/trends"),
    ("애드포스트", "https://adpost.naver.com/"),
]
MAX_TEXT = 30000


def capture(ctx, blog_id: str, out_dir: Path, settle_ms: int = 8000, pages=None) -> Dict[str, str]:
    """ctx: 로그인된 브라우저(persistent context). 돌려주는 값: 이름 → 결과(ok/오류)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results: Dict[str, str] = {}
    for name, url in (pages or PAGES):
        page = ctx.new_page()
        try:
            page.goto(url.format(blog_id=blog_id), wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(settle_ms)          # 숫자가 늦게 그려지는 화면이라 잠깐 기다림
            text = page.inner_text("body")[:MAX_TEXT]
            (out_dir / f"{name}.txt").write_text(f"{page.url}\n\n{text}", encoding="utf-8")
            page.screenshot(path=str(out_dir / f"{name}.png"), full_page=True)
            results[name] = "ok"
        except Exception as e:  # noqa: BLE001 — 한 화면이 안 돼도 나머지는 받는다
            results[name] = f"오류: {str(e)[:150]}"
            log.warning("통계 화면 못 받음 %s: %s", name, e)
        finally:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                pass
    (out_dir / "받은시각.json").write_text(json.dumps(
        {"at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "results": results}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return results
