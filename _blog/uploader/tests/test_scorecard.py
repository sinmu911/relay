"""글 성적표: 월간 순위를 하루치로 바꿔 쌓고, 글마다 7일/30일 조회와 검문소 점수를 나란히."""
import json
from datetime import date, datetime

import scorecard

RANK = """--- [틀] x
이전 기간 조회
2026.10.{d}.
조회수 순위 목록
순위 제목 조회수 타입 작성일
1 벳부 묘반 유야 에비스 온천 솔직 후기 | 가족탕 가격·예약·가는 법 (2026) {a} 글 2026.04.05. (일)
2 [두바이 ③] 렌트카로 하루 만에 도는 아부다비 코스 {b} 글 2026.10.11. (토)

=== 링크(다음 수집 주소 고를 때 참고) ===
벳부 묘반 유야 에비스 온천 솔직 후기 | 가족탕 가격·예약·가는 법 ( | https://blog.stat.naver.com/blog/article/224241636486/cv
[두바이 ③] 렌트카로 하루 만에 도는 아부다비 코스 | https://blog.stat.naver.com/blog/article/224437994685/cv
"""


def test_parse_month_rank():
    period, counts = scorecard.parse_month_rank(RANK.format(d="12", a=5, b=3))
    assert period == "2026-10-12"
    assert counts == {"224241636486": 5, "224437994685": 3}


def test_snapshots_become_daily_views_and_month_reset():
    meta = {}
    for d, a in (("12", 5), ("13", 7), ("13", 9)):        # 같은 기준일은 한 번만
        scorecard.add_snapshot(meta, *scorecard.parse_month_rank(RANK.format(d=d, a=a, b=1)))
    assert meta["daily_views"]["224241636486"] == {"2026-10-12": 5, "2026-10-13": 2}
    period, counts = "2026-11-01", {"224241636486": 4}
    scorecard.add_snapshot(meta, period, counts)           # 새 달 숫자는 그대로 하루치
    assert meta["daily_views"]["224241636486"]["2026-11-01"] == 4


def test_update_writes_table_with_checkpoint(tmp_path):
    neo = tmp_path / "neo"
    (neo / "초안").mkdir(parents=True)
    (neo / "상태").mkdir()
    (neo / "초안" / "a_완성본.md").write_text(
        "머리\n=====\n제목\n=====\n[두바이 ③] 렌트카로 하루 만에 도는 아부다비 코스\n\n=====\n본문\n=====\n글\n", encoding="utf-8")
    (neo / "상태" / "검문소_a_완성본.json").write_text(json.dumps({"파일": "a_완성본.md", "걸림": 0, "주의": 2}),
                                                     encoding="utf-8")
    stats = tmp_path / "stats"
    stats.mkdir()
    (stats / "월간조회수순위.txt").write_text(RANK.format(d="19", a=5, b=6), encoding="utf-8")
    posts = [{"log": "224437994685", "title": "[두바이 ③] 렌트카로 하루 만에 도는 아부다비 코스", "date": "2026-10-11"},
             {"log": "224241636486", "title": "벳부 묘반", "date": "2026-04-05"}]       # 60일 넘은 글은 뺌
    meta = {}
    n = scorecard.update(meta, neo, stats, posts, datetime(2026, 10, 20, 9), "mose_love")
    assert n == 1
    row = json.loads((neo / "상태" / "글성적표.json").read_text(encoding="utf-8"))["rows"][0]
    assert row["7일 조회"] == 0 and row["지금까지"] == 6 and row["30일 조회"] is None   # 첫 집계는 기준일(10-19)에 몰림
    assert row["검문소"] == "걸림 0 · 주의 2"
    assert "| 2026-10-11 |" in (neo / "상태" / "글성적표.md").read_text(encoding="utf-8")


def test_feed_posts():
    from sources import BlogFeed
    xml = b"""<rss><channel><item><title>T</title><link>https://blog.naver.com/mose_love/224437994685?fromRss=true</link>
<pubDate>Sat, 11 Oct 2026 19:36:00 +0900</pubDate></item></channel></rss>"""
    assert BlogFeed("x", fetch=lambda u: xml).posts() == [{"log": "224437994685", "title": "T", "date": "2026-10-11"}]
