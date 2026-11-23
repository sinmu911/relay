# courses/ — 코스형 글 (한 폴더 = 한 편)

```
courses/
  20261123_osan-segyo_example/     ← 예시(샘플 값, 발행 금지)
    course.json                    ← 무엇을 어디서 무엇으로 확인했는지(장소·팩트·리뷰·쇼츠·제휴)
    fact_report.json               ← 팩트 게이트 결과(발행 전 검사 기록)
    완성본.md                       ← 조립 결과(발행기가 읽는 형식, 기존 완성본과 동일)
    이미지/                         ← 【그림 N】 이 가리키는 파일
```

## 만드는 순서

```bash
cd _blog/neo_tools

# 1) 장소 후보를 코스로 묶고 동선을 확인한다 (식당 → 근처 카페/공원)
python3 -c "import json,course_cluster as c; print(c.route_check(json.load(open('../courses/<코스>/course.json'))['places']))"

# 2) 팩트·지도 핀 게이트 (BLOCK 0 이어야 다음으로)
python3 fact_gate.py ../courses/<코스>/course.json

# 3) 본문 조립 + 검문소까지 (발행은 안 함)
python3 course_compose.py ../courses/<코스>/course.json --dry-run
```

`--dry-run` 은 **발행을 누르지 않는다**. 네이버 화면에 실제로 넣어 보는 시험은 맥에서:

```bash
bash setup_mac.sh test      # 또는 python naver_upload.py run --dry-run
```

## 원칙

- `course.json` 에 **없는 사실은 문장으로 만들지 않는다.** 조립기는 그 문장을 빼고 `omitted` 에 남긴다.
  `[확인 필요]` 같은 자리표시도 남기지 않는다(검문소 B1이 걸림으로 잡아 발행을 막는다).
- 이 저장소는 **공개**다. 실제 원고·사진(가족 얼굴, 영수증 원본, 개인정보)은 여기에 커밋하지 않는다.
  원고는 `블로그_NEO`(드라이브)에 두고, 저장소에는 형식이 보이는 **샘플**만 둔다.
- 예시 코스(`20261123_osan-segyo_example`)의 장소·주소·금액은 전부 지어낸 값이다. 그대로 발행하면 안 된다.
