---
name: relay-shell-release
description: 중계현황 설치 앱(PWA 껍데기: index.html·app.html·sw.js·manifest.json·아이콘) 변경을 넣고 폰에 재설치 없이 반영할 때 사용. 배포 전 files/check.py 증명 검사 필수.
metadata:
  triggers: ["중계현황 앱", "설치 앱", "아이콘 바꿔", "CHG-", "앱 화면 고쳐", "sw.js", "manifest"]
---
# relay-shell-release

> 상태: **초안(80%)** — 저장소 git 이력·코드에서 추출. 인터뷰(`../_prompts/1-interview.md`) 미실시.
> 아래 `[확인 필요]` 항목은 추정이므로 사용자 답으로 확정할 것.

## 목적
중계현황 설치 앱(GitHub Pages의 PWA 껍데기: index.html·app.html·sw.js·manifest.json·아이콘)에 변경을 넣고, 설치된 폰이 재설치 없이 새 버전을 받게 반영한다.

## 언제 쓰는지
- "중계현황 앱 화면 고쳐줘", "설치 앱에 ○○ 추가해줘", "아이콘 바꿔줘", "CHG-### 반영해줘"
- 대시보드 본체(Apps Script) 수정은 **해당 없음** — 이 저장소엔 자료가 없다(index.html 주석 기준).

## 입력
- 변경 요청 — 사용자 메시지 또는 CHG 번호 [확인 필요: CHG 목록 위치]
- 껍데기 코드 — 저장소 루트 `index.html`(설치·안내 화면), `app.html`(설치 앱 본 화면), `sw.js`, `manifest.json`
- Apps Script 주소 — `index.html`·`app.html` 안 상수 `DASH`, `RELAY` (바꾸지 않는다)
- 알림 공개키 — `VAPID_PUB` (공개키, 비밀 아님. 개인키는 Mac 쪽 — 저장소에 절대 넣지 않음)

## 순서
1. 요청이 껍데기(이 저장소) 일인지, Apps Script 일인지 먼저 가른다. Apps Script면 멈추고 알린다.
2. 바꿀 파일을 고른다. 화면 둘(index.html, app.html)이 같은 걸 갖고 있으면 둘 다 고친다(예: viewport).
3. 고친다. 주석은 기존 방식대로 날짜 + 사용자 말 요약 한 줄 (예: `// 09-30 사용자 '…'`).
4. 아이콘을 바꿨으면 **파일 이름을 새로** 만든다(`-v2` → `-v3`). 같은 이름 덮어쓰기는 설치 앱이 못 받는다.
5. 새 아이콘 이름을 manifest.json·index.html·app.html·sw.js 모두에 반영한다.
6. `python3 playbooks/relay-shell-release/files/check.py` 실행 → 실패 0이 될 때까지 고친다.
7. 커밋: 제목 한 줄, 쉬운 한국어로 "무엇을 + (왜)". CHG가 있으면 앞에 `CHG-###`.
8. 푸시 → GitHub Pages 반영. html/json/js는 sw.js가 늘 새로 받으므로 재설치 불필요.

## 결정
- html/js/json만 바뀌었으면 → 이름 바꾸기 불필요(sw.js가 no-store로 새로 받음).
- 아이콘(png)이 바뀌었으면 → 새 이름 필수(4단계).
- 폰 입력칸 확대 문제 → viewport에 `maximum-scale=1` 유지. 지우지 않는다.
- 사장님(owner) 전용 동작 → Mac 경로 먼저, 실패 시 Google 경로로 (CHG-317 기준) [확인 필요: 일반 규칙인지]
- 파일에 비밀처럼 보이는 값이 생기면 → 커밋하지 않고 멈춘다.

## 완료의 정의
기계 검사(`files/check.py`) — 전부 통과해야 완료:
- [ ] manifest.json이 JSON으로 파싱되고, 적힌 아이콘 파일이 전부 존재
- [ ] index.html·app.html의 로컬 href/src가 전부 실제 파일로 존재
- [ ] 아이콘 참조가 manifest와 같은 버전 (구버전 이름 참조 0개)
- [ ] 두 html 모두 viewport에 `maximum-scale=1`
- [ ] sw.js와 html 안 인라인 스크립트가 `node --check` 문법 통과
- [ ] 개인키·API 키 패턴 0개 (패턴 목록은 check.py의 SECRET)
사람/브라우저 확인 — 자동화 전까지 보고에 "미확인"으로 표시:
- [ ] 폰(설치 앱)에서 열어 변경이 보임 — 스크린샷
- [ ] 알림 켜기/끄기가 오류 없이 동작

## 예외 사례
- 2026-10-01: 아이콘을 같은 이름으로 덮어써서 설치 앱이 새 아이콘을 못 받음 → `-v2` 이름으로 바꿔 해결.
- 2026-10-01: 폰 입력칸을 누르면 화면이 확대됨 → viewport `maximum-scale=1`.
- 2026-10-31 발견(미해결): app.html과 sw.js(알림 아이콘)가 아직 `icon-192.png`(구이름)를 가리킴. check.py가 이걸 잡는다. [확인 필요: v2로 통일할지]
