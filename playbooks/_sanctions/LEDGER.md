# 제재 장부 — 거짓·무근거 보고 1건마다 장치 1개

정책(2026-10-31 사용자): "확인 안 하고 아무 소리나 할 때마다 그 부분을 스킬로, 훅으로, 스크립트로 하나씩 묶는다."
규칙: 사건 1줄 = 레이어 진단 + 묶은 장치 경로 + 그 장치를 돌리는 명령. 경로가 저장소 안이면 `validate_playbooks.py`가 존재를 검사한다.
`~/`로 시작하는 경로는 사용자 Mac에 있음 — 이 저장소에서 검증 불가, 상태 칸에 `외부-미확인`.

| 날짜 | 사건 | 레이어 | 종류 | 장치 | 실행 명령 | 상태 |
|---|---|---|---|---|---|---|
| 2026-10-31 | 하객카드 버튼을 두 번 연속 "정상 확인"이라 거짓 보고 | 증명 | 스킬 | ~/.claude/skills/guestcard-report-verified/SKILL.md | (스킬 자동 로드) | 외부-미확인 |
| 2026-10-31 | 같은 사건 | 증명 | 스크립트 | ~/MicLab/common/guestcard_check.py | python3 ~/MicLab/common/guestcard_check.py <카드코드> <토큰> [분] | 외부-미확인 |
| 2026-10-31 | 같은 사건 — 일반화: 근거 없는 정상/완료 보고 | 증명 | 훅 | .claude/hooks/claim_gate.py | (Stop 훅 자동) / 테스트: python3 playbooks/report-verified/files/test_claim_gate.py | 저장소-검증 |
| 2026-10-31 | 같은 사건 — 일반화: 보고 양식 | 프로세스 | 스킬 | playbooks/report-verified/SKILL.md | python3 playbooks/_tools/validate_playbooks.py | 저장소-검증 |
| 2026-10-31 | claim_gate가 '근거:' 형식만 검사 — "근거: 됐음"도 통과 (사용자 지적) | 증명 | 훅 | .claude/hooks/claim_gate.py | python3 playbooks/report-verified/files/test_claim_gate.py | 저장소-검증 |
| 2026-10-31 | 차단 3회 후 조용히 통과 — 버티면 뚫림 (사용자 지적) | 증명 | 훅 | .claude/hooks/skill_router.py | python3 playbooks/report-verified/files/test_claim_gate.py | 저장소-검증 |
| 2026-10-31 | '병합해' 한 마디로 main 반영 가능 (사용자 지적) | 프로세스 | 훅 | .claude/hooks/merge_gate.py | python3 playbooks/_tools/test_merge_gate.py | 저장소-검증 |
| 2026-10-31 | 자동 git pull 시 검토 없이 새 코드가 매 요청 실행 (사용자 지적) | 툴박스 | 스크립트 | playbooks/_tools/install_approved.py | python3 playbooks/_tools/install_approved.py | 저장소-검증 |
