"""자동 업데이트: 드라이브 지문이 다 맞을 때만, 다른 파일만 바꾼다."""
import hashlib

import self_update


def _setup(tmp_path, files, manifest=None):
    src, app, home = tmp_path / "drive", tmp_path / "app", tmp_path / "home"
    for d in (src, app, home):
        d.mkdir()
    for name, data in files.items():
        (src / name).write_bytes(data)
    lines = manifest if manifest is not None else [
        f"{hashlib.sha256(d).hexdigest()}  {n}" for n, d in files.items()]
    (src / "MANIFEST.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (home / "source_dir").write_text(str(src) + "\n", encoding="utf-8")
    return src, app, home


def test_copies_only_changed_files(tmp_path):
    src, app, home = _setup(tmp_path, {"a.py": b"new", "b.py": b"same", "config.example.json": b"{}"})
    (app / "b.py").write_bytes(b"same")
    (app / "a.py").write_bytes(b"old")
    assert self_update.run(home, app) == ["a.py"]
    assert (app / "a.py").read_bytes() == b"new"
    assert not (app / "config.example.json").exists()          # 설정 예시는 안 건드림
    assert self_update.run(home, app) == []                     # 두 번째엔 바꿀 것 없음


def test_half_synced_drive_changes_nothing(tmp_path):
    src, app, home = _setup(tmp_path, {"a.py": b"new", "b.py": b"new2"})
    (src / "b.py").write_bytes(b"half")                         # 지문과 안 맞음(동기화 중)
    (app / "a.py").write_bytes(b"old")
    assert self_update.run(home, app) == []
    assert (app / "a.py").read_bytes() == b"old"


def test_rejects_path_tricks(tmp_path):
    data = b"x"
    h = hashlib.sha256(data).hexdigest()
    src, app, home = _setup(tmp_path, {"ok.py": data}, manifest=[f"{h}  ../evil.py", f"{h}  ok.py"])
    assert self_update.run(home, app) == ["ok.py"]
    assert not (tmp_path / "evil.py").exists()


def test_no_source_dir_is_quiet(tmp_path):
    (tmp_path / "app").mkdir()
    assert self_update.run(tmp_path, tmp_path / "app") == []
