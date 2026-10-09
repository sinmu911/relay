#!/bin/bash
# 네이버 블로그 자동 올리기 — 맥 설치/켜기/끄기
#   bash setup_mac.sh install   프로그램 설치(처음 한 번)
#   bash setup_mac.sh login     네이버 로그인(처음 한 번, 로그인 풀렸을 때)
#   bash setup_mac.sh test      시험 실행(발행 직전까지만)
#   bash setup_mac.sh start     5분마다 자동 실행 켜기
#   bash setup_mac.sh stop      자동 실행 끄기
#   bash setup_mac.sh log       최근 기록 보기
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP="${NAVER_BLOG_UPLOADER_HOME:-$HOME/.naver-blog-uploader}"
PY="$APP/venv/bin/python"
LABEL="com.relay.naver-blog-uploader"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

need_install() { [ -x "$PY" ] || { echo "먼저: bash $0 install"; exit 1; }; }

case "${1:-}" in
  install)
    mkdir -p "$APP/logs"
    if [ ! -x "$PY" ]; then python3 -m venv "$APP/venv"; fi
    "$PY" -m pip install -q --upgrade pip
    "$PY" -m pip install -q -r "$HERE/requirements.txt"
    "$PY" -m playwright install chromium
    if [ ! -f "$APP/config.json" ]; then
      cp "$HERE/config.example.json" "$APP/config.json"
      chmod 600 "$APP/config.json"
      echo "설정 파일을 만들었어요 → $APP/config.json"
      echo "  open -e \"$APP/config.json\"  로 열어서 blog_id 와 github_token 을 채우세요."
    fi
    echo "설치 끝. 다음: bash $0 login"
    ;;
  login)
    need_install
    "$PY" "$HERE/naver_upload.py" login
    ;;
  test)
    need_install
    "$PY" "$HERE/naver_upload.py" run --dry-run ${2:+--post "$2"}
    echo "화면 사진: $APP/logs/dryrun-*.png"
    ;;
  start)
    need_install
    mkdir -p "$HOME/Library/LaunchAgents" "$APP/logs"
    sed -e "s#__PYTHON__#$PY#" -e "s#__SCRIPT__#$HERE/naver_upload.py#" -e "s#__LOGS__#$APP/logs#" \
      "$HERE/launchd.plist.template" > "$PLIST"
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    echo "자동 실행 켬(5분마다). 끄기: bash $0 stop"
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
