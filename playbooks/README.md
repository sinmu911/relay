# playbooks — 일 하나에 매뉴얼 하나

출처: 낭만빌더 「AI 위임 루프: 에이전트 대신 매뉴얼으로 일 넘기기」(2026-09-18).
에이전트를 일마다 새로 만들지 않는다. **일 하나 = 폴더 하나**, 범용 AI가 그 폴더를 읽고 돌린다.

## 레이어 3개
| 레이어 | 파일 | 실패 증상 |
|---|---|---|
| 1. 프로세스 | `SKILL.md` (목적·언제 쓰는지·입력·순서·결정·완료의 정의·예외 사례) | 단계 누락, 순서 틀림, 결정 규칙 없음 |
| 2. 툴박스 | `files/` + `files/INDEX.md`, `examples/` | 이미 있는 걸 다시 지음, 낡은 파일 |
| 3. 증명 | `SKILL.md`의 완료의 정의 + 실행 가능한 검사 스크립트 | 잡을 검증이 없음 |

수정은 채팅이 아니라 폴더에서. 모든 수정은 `notes.md`에 한 줄(최신이 위).

## 사용 순서 (첫 30분)
1. `_prompts/1-interview.md` — 인터뷰로 SKILL.md 뽑기 (새 일감은 `_template/` 복사로 시작)
2. 일 한 번 실행 → 통과한 산출물은 `_prompts/2-save-tool.md`로 툴박스에 저장
3. `_prompts/3-proof.md` — 실패할 수 있는 검증 항목 추가
4. 틀린 결과가 나오면 `_prompts/4-fix-by-layer.md` — 레이어 진단 후 최소 수정
5. 두 번째 실행에서 설명이 얼마나 줄었는지 확인

## 자동 검사
```
python3 playbooks/_tools/validate_playbooks.py      # 모든 매뉴얼 폴더 구조·INDEX·비밀값 검사
python3 playbooks/relay-shell-release/files/check.py # relay 앱 배포 전 증명 검사
```
둘 다 실패하면 종료코드 1. "괜찮아 보인다"는 검증이 아니다.

## 규칙
- 마스터 복사본은 이 저장소 하나. Project/Drive 업로드는 스냅샷 — 교체하고, 두 번째로 추가하지 않는다.
- `files/` 파일명에 날짜·버전 금지 (`examples/`만 날짜 사용). 용도 하나에 파일 하나.
- 비밀번호·API 키·일회성 산출물·미승인 초안은 저장 금지.
- 월 1회: 안 쓴 파일 삭제, `notes.md` 읽고 같은 레이어 반복 실패 확인.

## 매뉴얼 목록
| 폴더 | 일 | 상태 |
|---|---|---|
| `relay-shell-release/` | 중계현황 설치 앱(PWA 껍데기) 변경 반영 | 초안 — 저장소 이력에서 추출, 인터뷰 미실시 |
| `report-verified/` | 모든 노드의 정상/완료 보고 (확인 범위 구분) | 공용 — guestcard-report-verified 일반화 |

## 제재 장치 (거짓 보고 1건 = 장치 1개)
- 장부: `_sanctions/LEDGER.md` — 검사기가 장치 파일 존재까지 확인
- 훅: `.claude/hooks/claim_gate.py` (Stop) — 이번 턴 도구 실행 0회, `근거:` 없음, `미확인` 진술 없음 중 하나라도 있으면 완료 보고를 막음
- 다른 PC/노드에 적용: `.claude/hooks/claim_gate.py`를 복사하고 `~/.claude/settings.json`의 `hooks.Stop`에 같은 명령을 추가

## 스킬 자동 사용 (새 스킬이 생기면 노드가 알아서 쓰게)
1. 새 일감: `_template/` 복사 → SKILL.md 맨 위 frontmatter의 `name`(=폴더명), `description`(언제 쓰는지), `metadata.triggers`(실제로 칠 말)를 채운다.
2. 등록: `python3 playbooks/_tools/sync_skills.py` — `.claude/skills/`에 링크 + `SKILLS.md` 색인. 세션 시작 훅도 자동 실행.
   이 컴퓨터의 모든 세션(다른 저장소 포함)에 걸려면: `--target ~/.claude/skills`
3. 자동 작동:
   - Claude Code가 skills 폴더를 감시 → description이 맞는 요청에 스킬 자동 호출(공식 기능)
   - `skill_announce.py`(SessionStart): 세션마다 스킬 목록 + 새로/바뀐 스킬 알림
   - `skill_router.py`(UserPromptSubmit): 요청에 트리거 말이 있으면 해당 스킬을 쓰라고 주입 + `~/.claude/skill_usage.log` 기록
4. 검사: `validate_playbooks.py`가 frontmatter·트리거·등록 누락을 실패로 잡는다. 끝단 시험: `python3 playbooks/_tools/test_skill_autouse.py`
