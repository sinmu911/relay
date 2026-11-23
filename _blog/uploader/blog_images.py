"""업로드 전 사진 손질 — 전부 가로 4:3 으로 통일하고, 대표 사진 기준을 본다.

2026-11-19 서준님 확정: 세로 사진이 섞여 있어도 블로그 업로드용 사진은 **전부 가로(4:3)**.
세로 원본은 위아래를 잘라 4:3으로 맞추고, 주 피사체가 잘리는 사진은 뺀다.
2026-11-18 확정(대표 썸네일): 첫 사진 = 대표, 가로 1,200px 이상 원본, 흐림·과노출·역광 금지,
주요 피사체 중앙 60%, 글자·워터마크·콜라주 없음.

여기서는 기계가 판정할 수 있는 것만 본다 — 크기·비율. 흐림·역광·주 피사체 잘림은 사람 눈의 몫이라
'잘라내는 비율이 큰 사진'만 표시해 준다(자동으로 버리지 않는다 — 사진을 빼는 결정은 사람이 한다).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

try:
    from PIL import Image
except Exception:            # Pillow 가 없으면 사진은 손대지 않고 그대로 올린다(발행이 멈추지 않게)
    Image = None

TARGET = 4 / 3
MIN_KEEP = 0.55             # 잘라낸 뒤 남는 면적 비율이 이보다 작으면 손대지 않고 알림(파노라마·극단적 세로)
MIN_WIDTH = 1200            # 대표 사진 가로 최소(2026-11-18)
SIZE_RE = (960, 960)        # 네이버 업로드 권장 상한(가로·세로)


def _size(path: Path) -> Tuple[int, int]:
    with Image.open(path) as im:
        return im.size


def is_landscape_4x3(path: Path, tol: float = 0.02) -> bool:
    if Image is None:
        return True
    try:
        w, h = _size(path)
    except Exception:
        return True
    return w > h and abs(w / max(1, h) - TARGET) <= tol


def plan(path: Path) -> dict:
    """이 사진을 4:3으로 만들 때 무엇을 얼마나 자르는지."""
    out = {"file": path.name, "ok": True, "cropped": False, "keep": 1.0, "note": ""}
    if Image is None:
        out.update(ok=False, note="Pillow 없음 — 원본 그대로 올림")
        return out
    try:
        w, h = _size(path)
    except Exception as e:
        out.update(ok=False, note=f"사진을 못 열어요({type(e).__name__})")
        return out
    out.update(w=w, h=h)
    if w <= 0 or h <= 0:
        out.update(ok=False, note="크기를 못 읽음")
        return out
    if w > h and abs(w / h - TARGET) <= 0.02:
        out.update(keep=1.0)
        return out
    if w >= h * TARGET:                      # 가로가 남음 → 좌우를 자름
        new_w = int(round(h * TARGET))
        keep = new_w / w
        out.update(cropped=True, keep=round(keep, 3), crop="좌우", target_w=new_w, target_h=h)
    else:                                    # 세로가 남음 → 위아래를 자름
        new_h = int(round(w / TARGET))
        keep = new_h / h
        out.update(cropped=True, keep=round(keep, 3), crop="위아래", target_w=w, target_h=new_h)
    if keep < MIN_KEEP:
        out.update(ok=False, note=f"4:3으로 자르면 {int(keep * 100)}%만 남아요 — 사진을 빼거나 직접 자르세요")
    return out


def normalize_4x3(path: Path, out_dir: Path) -> Tuple[Path, dict]:
    """한 장을 가로 4:3으로 만들어 out_dir 에 새 파일로 쓴다(원본은 건드리지 않는다)."""
    info = plan(path)
    if not info.get("ok") or not info.get("cropped"):
        return path, info
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"43_{path.stem}.jpg"
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            w, h = im.size
            if w >= h * TARGET:
                new_w = int(round(h * TARGET)); left = (w - new_w) // 2
                box = (left, 0, left + new_w, h)
            else:
                new_h = int(round(w / TARGET)); top = (h - new_h) // 2
                box = (0, top, w, top + new_h)
            out = im.crop(box)
            if out.width > SIZE_RE[0] and out.width > out.height:
                out = out.resize((SIZE_RE[0], int(round(SIZE_RE[0] / TARGET))), Image.LANCZOS)
            out.save(dst, "JPEG", quality=92, optimize=True)
    except Exception as e:
        info.update(ok=False, note=f"자르기 실패({type(e).__name__}) — 원본 그대로 올림")
        return path, info
    info.update(cropped=True, saved=str(dst), w=Image.open(dst).width, h=Image.open(dst).height)
    return dst, info


def normalize_many(images: Dict[str, Path]) -> Tuple[Dict[str, Path], List[str]]:
    """글의 사진 전부를 4:3으로. 돌려줌: (바뀐 {이름: 경로}, 사람이 볼 알림 목록)."""
    notes: List[str] = []
    out: Dict[str, Path] = {}
    for name, path in images.items():
        new_path, info = normalize_4x3(Path(path), Path(path).parent)
        out[name] = new_path
        if info.get("cropped") and info.get("ok"):
            notes.append(f"사진 4:3 통일: {name} ({info.get('crop')} 자름, {int(info.get('keep', 1) * 100)}% 유지)")
        elif not info.get("ok"):
            notes.append(f"사진 손대지 않음: {name} — {info.get('note')}")
    return out, notes


def check_representative(path: Path) -> List[str]:
    """대표(첫) 사진 기준 — 기계가 볼 수 있는 것만."""
    issues: List[str] = []
    if Image is None:
        return ["Pillow 없음 — 대표 사진 기준을 확인하지 못했어요"]
    try:
        w, h = _size(path)
    except Exception:
        return [f"대표 사진을 못 열어요: {Path(path).name}"]
    if w < MIN_WIDTH:
        issues.append(f"대표 사진 가로 {w}px(1,200px 이상 원본 권장)")
    if h > w:
        issues.append("대표 사진이 세로 — 가로 4:3으로 잘라 올려요")
    return issues


def describe(paths: List[Path]) -> str:
    """화면에 보여줄 한 줄 요약(시험·dry-run 보고용)."""
    if not paths:
        return "사진 없음"
    plans = [plan(Path(p)) for p in paths]
    cropped = sum(1 for p in plans if p.get("cropped"))
    bad = [p for p in plans if not p.get("ok")]
    return f"사진 {len(plans)}장 · 4:3 자름 {cropped}장" + (f" · 손대지 않음 {len(bad)}장" if bad else "")
