"""로그인 점검: 하루 한 번 기록, 풀리기 3일 전 알림, 풀린 이유 짐작, 풀림은 한 번만 기록."""
import json
from datetime import datetime, timedelta

import login_watch

NOW = datetime(2026, 10, 13, 10, 0)


class FakePub:
    def __init__(self, cookies, ok):
        self.cookies, self.ok = cookies, ok

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def auth_cookies(self):
        return self.cookies

    def check_login(self):
        return self.ok


def ts(days):
    return (NOW + timedelta(days=days)).timestamp()


def run(tmp_path, state, cookies, ok, now=NOW, force=False):
    notes = []
    entry = login_watch.check({"neo_root": str(tmp_path)}, state, lambda: FakePub(cookies, ok),
                              lambda t, m: notes.append(t), now, force=force)
    return entry, notes


def test_daily_record_written_without_cookie_values(tmp_path):
    state = {}
    entry, notes = run(tmp_path, state, {"NID_AUT": ts(30), "NID_SES": ts(30)}, True)
    assert entry["로그인"] == "됨" and entry["남은 날"] == 30 and not notes
    rec = json.loads((tmp_path / "상태" / "로그인_기록.json").read_text(encoding="utf-8"))
    assert rec["기록"][0]["쿠키"]["NID_AUT"].startswith("2026-11-12")
    # 같은 날 다시는 안 봄, 9시 전에도 안 봄
    assert run(tmp_path, state, {}, False)[0] is None
    assert run(tmp_path, {}, {}, False, now=NOW.replace(hour=8))[0] is None


def test_warns_three_days_before_once_a_day(tmp_path):
    state = {}
    _, notes = run(tmp_path, state, {"NID_AUT": ts(2), "NID_SES": ts(40)}, True)
    assert notes == ["로그인 곧 풀려요"]
    _, notes = run(tmp_path, state, {"NID_AUT": ts(2), "NID_SES": ts(40)}, True, force=True)
    assert notes == []


def test_causes():
    g = lambda c: login_watch.guess_cause(c, NOW)
    assert "로그아웃" in g({})
    assert "로그인 상태 유지" in g({"NID_AUT": -1, "NID_SES": -1})
    assert "기간이 끝남" in g({"NID_AUT": ts(-1), "NID_SES": ts(10)})
    assert "로그아웃" in g({"NID_AUT": ts(10), "NID_SES": ts(10)})


def test_logout_forced_once_and_keeps_since(tmp_path):
    state = {}
    run(tmp_path, state, {"NID_AUT": ts(30), "NID_SES": ts(30)}, True)
    later = NOW + timedelta(days=1)
    entry, _ = run(tmp_path, state, {}, False, now=later, force=True)
    assert entry["로그인"] == "풀림" and "유지된 기간" in entry and "로그아웃" in entry["이유 짐작"]
    # 같은 날 5분 뒤 또 force 여도 다시 열지 않음
    assert run(tmp_path, state, {}, False, now=later + timedelta(minutes=5), force=True)[0] is None
