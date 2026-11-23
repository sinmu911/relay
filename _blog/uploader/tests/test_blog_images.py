"""사진 손질 시험 — 업로드용 사진은 전부 가로 4:3, 대표는 가로 1,200px 이상(2026-11-18·19 확정)."""
from pathlib import Path

from PIL import Image

import blog_images


def _img(path: Path, w: int, h: int):
    Image.new("RGB", (w, h), (200, 200, 200)).save(path, "JPEG", quality=70)
    return path


def test_landscape_4x3_is_untouched(tmp_path):
    p = _img(tmp_path / "a.jpg", 1200, 900)
    assert blog_images.is_landscape_4x3(p)
    info = blog_images.plan(p)
    assert info["ok"] and not info["cropped"]


def test_portrait_is_cropped_to_landscape_4x3(tmp_path):
    p = _img(tmp_path / "portrait.jpg", 900, 1200)
    out, info = blog_images.normalize_4x3(p, tmp_path)
    assert info["ok"] and info["cropped"] and info["crop"] == "위아래"
    with Image.open(out) as im:
        w, h = im.size
    assert w > h and abs(w / h - 4 / 3) < 0.02
    assert Path(out).name.startswith("43_")
    with Image.open(p) as im:            # 원본은 그대로
        assert im.size == (900, 1200)


def test_very_wide_photo_is_reported_not_silently_cut(tmp_path):
    p = _img(tmp_path / "pano.jpg", 2400, 500)
    info = blog_images.plan(p)
    assert not info["ok"] and "빼거나" in info["note"]
    out, info2 = blog_images.normalize_4x3(p, tmp_path)
    assert out == p and not info2["ok"]          # 손대지 않고 원본 그대로


def test_normalize_many_reports_each_photo(tmp_path):
    a = _img(tmp_path / "a.jpg", 1200, 900)
    b = _img(tmp_path / "b.jpg", 1000, 1400)
    out, notes = blog_images.normalize_many({"a": a, "b": b})
    assert set(out) == {"a", "b"}
    assert any("4:3" in n for n in notes) and len(notes) >= 1


def test_representative_needs_1200px_and_landscape(tmp_path):
    small = _img(tmp_path / "small.jpg", 800, 600)
    tall = _img(tmp_path / "tall.jpg", 1200, 1600)
    ok = _img(tmp_path / "ok.jpg", 1600, 1200)
    assert any("1,200px" in m for m in blog_images.check_representative(small))
    assert any("세로" in m for m in blog_images.check_representative(tall))
    assert blog_images.check_representative(ok) == []
