#!/bin/bash
# 네이버 블로그 자동 올리기 — 맥 설치/켜기/끄기 (드라이브 블로그_NEO/도구/자동발행 또는 저장소 _blog/uploader 어디서 실행해도 됨)
#   bash setup_mac.sh install   프로그램 설치(처음 한 번)
#   bash setup_mac.sh login     네이버 로그인(처음 한 번, 로그인 풀렸을 때)
#   bash setup_mac.sh test      시험 실행(발행 직전까지만, 예약 시각 무시)
#   bash setup_mac.sh start     5분마다 자동 실행 켜기
#   bash setup_mac.sh stop      자동 실행 끄기
#   bash setup_mac.sh update    코드만 새로 복사(설정·로그인·기록은 그대로)
#   bash setup_mac.sh log       최근 기록 보기
# 코드는 ~/.naver-blog-uploader/app 으로 복사해서 돌린다 — 드라이브 동기화 중에 파일이 반쯤 바뀌어도
# 돌고 있는 프로그램이 안 깨지고, 실행 중 생기는 파일(__pycache__ 등)이 드라이브에 쓰이지 않게.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP="${NAVER_BLOG_UPLOADER_HOME:-$HOME/.naver-blog-uploader}"
CODE="$APP/app"
PY="$APP/venv/bin/python"
LABEL="com.relay.naver-blog-uploader"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

need_install() { [ -x "$PY" ] && [ -f "$CODE/naver_upload.py" ] || { echo "먼저: bash \"$0\" install"; exit 1; }; }

copy_code() {
  mkdir -p "$CODE"
  cp "$HERE"/*.py "$HERE/requirements.txt" "$HERE/launchd.plist.template" "$CODE"/
  echo "코드 복사: $HERE → $CODE"
}

case "${1:-}" in
  install)
    mkdir -p "$APP/logs"
    copy_code
    if [ ! -x "$PY" ]; then python3 -m venv "$APP/venv"; fi
    "$PY" -m pip install -q --upgrade pip
    "$PY" -m pip install -q -r "$CODE/requirements.txt"
    "$PY" -m playwright install chromium
    if [ ! -f "$APP/config.json" ]; then
      cp "$HERE/config.example.json" "$APP/config.json"
      chmod 600 "$APP/config.json"
      echo "설정 파일을 만들었어요 → $APP/config.json"
      echo "  open -e \"$APP/config.json\"  로 열어서 neo_root(블로그_NEO 폴더 경로)가 맞는지 확인하세요."
    fi
    echo "설치 끝. 다음: bash \"$0\" login"
    ;;
  update)
    [ -x "$PY" ] || { echo "먼저: bash \"$0\" install"; exit 1; }
    copy_code
    "$PY" -m pip install -q -r "$CODE/requirements.txt"
    echo "코드 갱신 끝(자동 실행 중이면 다음 5분 주기부터 새 코드)"
    ;;
  login)
    need_install
    "$PY" "$CODE/naver_upload.py" login
    ;;
  test)
    need_install
    "$PY" "$CODE/naver_upload.py" run --dry-run ${2:+--post "$2"}
    echo "화면 사진: $APP/logs/dryrun-*.png"
    ;;
  start)
    need_install
    mkdir -p "$HOME/Library/LaunchAgents" "$APP/logs"
    sed -e "s#__PYTHON__#$PY#" -e "s#__SCRIPT__#$CODE/naver_upload.py#" -e "s#__LOGS__#$APP/logs#" \
      "$CODE/launchd.plist.template" > "$PLIST"
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    echo "자동 실행 켬(5분마다). 끄기: bash \"$0\" stop"
    ;;
  stop)
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "자동 실행 끔"
    ;;
  log)
    tail -n 40 "$APP/logs/uploader.log"
    ;;
  *)
    sed -n '2,9p' "$0"
    exit 1
    ;;
esac
