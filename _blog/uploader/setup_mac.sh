#!/bin/bash
# 네이버 블로그 자동 올리기 — 설치 뒤엔 한글 없는 경로로: bash ~/.naver-blog-uploader/app/setup_mac.sh <명령>
#   bash setup_mac.sh install   프로그램 설치(처음 한 번, 드라이브 블로그_NEO/도구/자동발행에서)
#   bash setup_mac.sh login     네이버 로그인(처음 한 번, 로그인 풀렸을 때)
#   bash setup_mac.sh test      시험 실행(발행 직전까지만, 예약 시각 무시)
#   bash setup_mac.sh start     5분마다 자동 실행 켜기
#   bash setup_mac.sh stop      자동 실행 끄기
#   bash setup_mac.sh update    드라이브에서 코드만 새로 복사(설정·로그인·기록은 그대로)
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

need_install() { [ -x "$PY" ] && [ -f "$CODE/naver_upload.py" ] || { echo "먼저 설치(install)가 필요해요"; exit 1; }; }

# 설치된 사본(~/.naver-blog-uploader/app)에서 실행하면 원본(드라이브 폴더)은 기억해 둔 곳에서 찾는다
SRC="$HERE"
if [ "$HERE" = "$CODE" ]; then
  SRC="$(cat "$APP/source_dir" 2>/dev/null || true)"
  if [ ! -f "$SRC/naver_upload.py" ]; then
    SRC="$(ls -d "$HOME"/Library/CloudStorage/GoogleDrive-*/*/*_NEO/*/*/setup_mac.sh 2>/dev/null | head -n 1 | xargs -I{} dirname "{}" || true)"
  fi
fi

copy_code() {
  [ -f "$SRC/naver_upload.py" ] || { echo "드라이브의 자동발행 폴더를 못 찾았어요."; exit 1; }
  # 드라이브에서 받은 경우: 파일 지문(MANIFEST.sha256)과 다르면(동기화 덜 됨·깨짐) 설치하지 않는다
  if [ -f "$SRC/MANIFEST.sha256" ]; then
    (cd "$SRC" && shasum -a 256 -c MANIFEST.sha256 --quiet) || {
      echo "파일이 덜 내려왔거나 바뀌었어요. 드라이브 동기화가 끝난 뒤(1~2분) 다시 해 주세요."; exit 1; }
  fi
  mkdir -p "$CODE"
  # 임시 이름으로 복사한 뒤 바꿔치기 — 지금 돌고 있는 이 스크립트 자신을 덮어써도 안 깨지게
  for f in "$SRC"/*.py "$SRC/requirements.txt" "$SRC/launchd.plist.template" "$SRC/setup_mac.sh"; do
    b="$(basename "$f")"
    cp "$f" "$CODE/.tmp-$b" && mv -f "$CODE/.tmp-$b" "$CODE/$b"
  done
  printf '%s\n' "$SRC" > "$APP/source_dir"
  echo "코드 복사 끝 → $CODE"
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
      cp "$SRC/config.example.json" "$APP/config.json"
      chmod 600 "$APP/config.json"
      echo "설정 파일을 만들었어요 → $APP/config.json"
      echo "  open -e \"$APP/config.json\"  로 열어서 neo_root(블로그_NEO 폴더 경로)가 맞는지 확인하세요."
    fi
    echo "설치 끝. 다음: bash ~/.naver-blog-uploader/app/setup_mac.sh login"
    ;;
  update)
    [ -x "$PY" ] || { echo "먼저: bash \"$0\" install"; exit 1; }
    copy_code
    "$PY" -m pip install -q -r "$CODE/requirements.txt"
    echo "코드 갱신 끝(자동 실행 중이면 다음 5분 주기부터 새 코드)"
    echo "이제부터 명령은: bash ~/.naver-blog-uploader/app/setup_mac.sh login|test|start|stop|log|update"
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
