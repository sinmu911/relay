"""글 수정 명령(run_edit): 여러 글 차례로, 어긋난 글만 건너뛰기, 같은 글 두 번 안 고치기."""
import json
from contextlib import contextmanager

import naver_editor
import naver_upload
from queue_state import StateFile


class FakePage:
    def close(self):
        pass


class FakePub:
    def _shot(self, page, kind):
        return None


@contextmanager
def fake_factory():
    yield FakePub()


def setup(tmp_path, monkeypatch, specs, results, publish_ok=True):
    root = tmp_path / "neo"
    (root / "상태").mkdir(parents=True)
    (root / "상태" / "글수정_대기.json").write_text(json.dumps(specs, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(naver_upload, "APP_HOME", tmp_path / "app")
    published = []
    monkeypatch.setattr(naver_editor, "apply_edits", lambda pub, log_no, spec, images: (FakePage(), None, results[spec["id"]]))
    monkeypatch.setattr(naver_editor, "publish_edit",
                        lambda pub, page, frame, log_no: published.append(log_no) or publish_ok)
    return {"neo_root": str(root)}, StateFile(tmp_path / "state.json"), published


def test_multiple_posts_bad_one_skipped(tmp_path, monkeypatch):
    specs = {"edits": [{"id": "a", "log_no": "111111", "replace": []},
                       {"id": "b", "log_no": "222222", "replace": []},
                       {"id": "c", "log_no": "333333", "replace": []}]}
    results = {"a": ["바꿈 1곳: x"], "b": ["안 바뀜: y"], "c": ["바꿈 2곳: z"]}
    cfg, sf, published = setup(tmp_path, monkeypatch, specs, results)
    assert naver_upload.run_edit(cfg, sf, fake_factory, lambda *a: None) == 1
    assert published == ["111111", "333333"]
    assert set(sf.load()["meta"]["edits_done"]) == {"a", "c"}
    published.clear()
    results["b"] = ["바꿈 1곳: y"]
    assert naver_upload.run_edit(cfg, sf, fake_factory, lambda *a: None) == 0
    assert published == ["222222"]                       # 이미 고친 a·c 는 다시 안 함


def test_single_spec_still_works_and_dry_run_never_publishes(tmp_path, monkeypatch):
    spec = {"id": "one", "log_no": "224241636486", "replace": []}
    cfg, sf, published = setup(tmp_path, monkeypatch, spec, {"one": ["바꿈 1곳: x"]})
    assert naver_upload.run_edit(cfg, sf, fake_factory, lambda *a: None, dry_run=True) == 0
    assert published == [] and "edits_done" not in json.dumps(sf.load()["meta"]).replace('"edits_done": {}', "")
    assert naver_upload.run_edit(cfg, sf, fake_factory, lambda *a: None) == 0
    assert published == ["224241636486"]


def test_unconfirmed_publish_is_recorded_so_it_is_not_redone(tmp_path, monkeypatch):
    spec = {"id": "one", "log_no": "224241636486", "replace": []}
    cfg, sf, published = setup(tmp_path, monkeypatch, spec, {"one": ["바꿈 1곳: x"]}, publish_ok=False)
    assert naver_upload.run_edit(cfg, sf, fake_factory, lambda *a: None) == 1
    assert naver_upload.run_edit(cfg, sf, fake_factory, lambda *a: None) == 0
    assert published == ["224241636486"]                 # 두 번째엔 안 누름(글자 두 번 붙는 것 방지)


def test_bad_list_is_refused(tmp_path, monkeypatch):
    cfg, sf, published = setup(tmp_path, monkeypatch, {"edits": [{"id": "a", "log_no": "x"}]}, {})
    assert naver_upload.run_edit(cfg, sf, fake_factory, lambda *a: None) == 1 and published == []


def test_auto_edit_tests_then_waits_for_approval_then_publishes(tmp_path, monkeypatch):
    """자동 실행: 새 수정은 시험만 → 결과 파일 → 지문 승인 뒤에만 발행 → 다시는 안 함."""
    spec = {"id": "b", "log_no": "224241636486", "replace": [{"old": "x", "new": "y"}]}
    cfg, sf, published = setup(tmp_path, monkeypatch, spec, {"b": ["바꿈 1곳: x"]})
    root = tmp_path / "neo"
    assert naver_upload.auto_edit(cfg, sf, fake_factory, lambda *a: None) == "edit_b:시험"
    assert published == []
    res = json.loads((root / "상태" / "글수정_결과.json").read_text(encoding="utf-8"))["results"][0]
    assert res["status"] == "시험 끝(다 됨)" and res["hash"] == naver_upload.edit_spec_hash(spec)
    assert naver_upload.auto_edit(cfg, sf, fake_factory, lambda *a: None) == ""      # 승인 기다림
    assert published == []
    spec["approved"] = "wrong"
    (root / "상태" / "글수정_대기.json").write_text(json.dumps(spec), encoding="utf-8")
    assert naver_upload.auto_edit(cfg, sf, fake_factory, lambda *a: None) == ""      # 틀린 지문은 무시
    spec["approved"] = res["hash"]
    (root / "상태" / "글수정_대기.json").write_text(json.dumps(spec), encoding="utf-8")
    assert naver_upload.auto_edit(cfg, sf, fake_factory, lambda *a: None) == "edit_b:발행"
    assert published == ["224241636486"]
    assert naver_upload.auto_edit(cfg, sf, fake_factory, lambda *a: None) == ""      # 다시는 안 함


def test_auto_edit_changed_content_is_retested_and_bad_test_never_publishes(tmp_path, monkeypatch):
    spec = {"id": "c", "log_no": "224241636486", "replace": [{"old": "x", "new": "y"}]}
    results = {"c": ["안 바뀜: x"]}
    cfg, sf, published = setup(tmp_path, monkeypatch, spec, results)
    root = tmp_path / "neo"
    naver_upload.auto_edit(cfg, sf, fake_factory, lambda *a: None)
    h = naver_upload.edit_spec_hash(spec)
    spec["approved"] = h                                   # 실패한 시험을 승인해도
    (root / "상태" / "글수정_대기.json").write_text(json.dumps(spec), encoding="utf-8")
    assert naver_upload.auto_edit(cfg, sf, fake_factory, lambda *a: None) == ""
    assert published == []                                 # 발행 안 함
    spec["replace"] = [{"old": "x", "new": "z"}]           # 내용을 고치면 다시 시험부터
    (root / "상태" / "글수정_대기.json").write_text(json.dumps(spec), encoding="utf-8")
    assert naver_upload.auto_edit(cfg, sf, fake_factory, lambda *a: None) == "edit_c:시험"
