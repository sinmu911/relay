"""자동 업데이트 — 드라이브 자동발행 폴더에 새 코드가 올라오면 5분 자동 실행이 알아서 바꾼다.

사장님 요청(10-12): "맥에서 안 쳐도 되게". 하는 일은 setup_mac.sh update 의 코드 복사와 똑같다.
  - 드라이브 폴더(설치 때 기억한 source_dir)의 MANIFEST.sha256 지문과 파일이 전부 맞을 때만 바꾼다
    (동기화가 덜 끝났으면 손대지 않고 다음 바퀴에).
  - 지금 깔린 코드와 다른 파일만 임시 이름으로 쓴 뒤 바꿔치기한다.
  - requirements.txt 가 바뀌면 pip 로 맞춘다.
  - 바꿨으면 이번 바퀴는 끝내고 다음 바퀴(5분 뒤)부터 새 코드로 돈다.
설정 config.json 의 "self_update": false 로 끌 수 있다.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

log = logging.getLogger(__name__)

# 바꿔도 되는 파일 이름(설정 예시·설명서는 안 건드림, 경로 기호는 막음)
INSTALLABLE_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.(py|txt|template|sh)")
LINE_RE = re.compile(r"([0-9a-f]{64})\s+\*?(\S+)")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pending_files(src: Path, app_dir: Path) -> Dict[str, bytes]:
    """바꿔야 할 파일 {이름: 새 내용}. 드라이브가 지문과 하나라도 안 맞으면 빈 것(이번엔 안 바꿈)."""
    try:
        lines = (src / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    out: Dict[str, bytes] = {}
    for line in lines:
        m = LINE_RE.fullmatch(line.strip())
        if not m or not INSTALLABLE_RE.fullmatch(m.group(2)):
            continue
        want, name = m.groups()
        try:
            cur = (app_dir / name).read_bytes()
        except OSError:
            cur = b""
        if _sha(cur) == want:
            continue
        try:
            data = (src / name).read_bytes()
        except OSError:
            data = b""
        if _sha(data) != want:
            log.info("드라이브 코드가 아직 덜 내려와서 새 코드는 다음에: %s", name)
            return {}
        out[name] = data
    return out


def run(app_home: Path, app_dir: Path) -> List[str]:
    """바꾼 파일 이름들. 바꿀 게 없거나 못 바꾸면 빈 목록."""
    try:
        src = Path((app_home / "source_dir").read_text(encoding="utf-8").strip())
    except OSError:
        return []
    if not src.is_dir() or src.resolve() == app_dir.resolve():
        return []
    files = pending_files(src, app_dir)
    for name, data in files.items():
        tmp = app_dir / f".tmp-{name}"
        tmp.write_bytes(data)
        os.replace(tmp, app_dir / name)
    if "requirements.txt" in files:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(app_dir / "requirements.txt")],
                           timeout=600, check=False)
        except (OSError, subprocess.SubprocessError) as e:
            log.warning("새 requirements 설치 실패(다음에 update 로): %s", e)
    if files:
        log.info("새 코드로 바꿈: %s", ", ".join(sorted(files)))
    return sorted(files)
