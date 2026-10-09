"""login 명령: 창을 닫은 뒤 다시 열어 로그인이 남았는지 확인하고, 안 남았으면 이유를 알려 준다."""
import json

import naver_upload


class FakePub:
    result = True

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def check_login(self):
        return FakePub.result


def run(tmp_path, capsys, status, session_only, logged_in):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"blog_id": "mose_love", "sources": ["neo"], "neo_root": str(tmp_path)}), encoding="utf-8")
    FakePub.result = logged_in
    code = naver_upload.do_login(cfg, login_fn=lambda _p: (status, session_only), publisher_cls=FakePub)
    return code, capsys.readouterr().out


def test_saved_login(tmp_path, capsys):
    code, out = run(tmp_path, capsys, "ok", [], True)
    assert code == 0 and "저장 확인" in out


def test_session_cookie_login_explains_keep_login(tmp_path, capsys):
    code, out = run(tmp_path, capsys, "ok", ["NID_AUT", "NID_SES"], False)
    assert code == 1 and "로그인 상태 유지" in out


def test_timeout_skips_check(tmp_path, capsys):
    code, out = run(tmp_path, capsys, "timeout", [], True)
    assert code == 1 and "시간 안에" in out
