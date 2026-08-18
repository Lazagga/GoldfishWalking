# GoldfishWalking 게임 데이터 안내

이 폴더는 몬스터, 몬스터 패턴, 판타지 등 게임 콘텐츠의 JSON 원본을
보관하는 곳입니다.

이 폴더의 JSON이 현재 게임 콘텐츠의 원본입니다. JSON을 저장하면 Unity가
자동으로 검사한 뒤 `Assets/Data/Generated`의 런타임 데이터베이스를 다시
생성합니다. 기존 TSV 자료는 더 이상 importer나 게임에서 사용하지 않습니다.

몬스터 이미지 파일은 `Assets/Art/enemy`에 두고 `presentation.sprite`에는
파일 이름을 적습니다. JSON을 가져오면 Unity가 Sprite, AnimationClip,
AnimatorController를 자동 생성해 런타임 데이터베이스에 직접 연결합니다.
자세한 이미지 규칙은 `Assets/Art/README.md`를 참고합니다.

## 폴더 구성

### `monsters/`

몬스터 데이터가 들어 있습니다. 몬스터 하나당 JSON 파일 하나를
사용합니다.

기존 `Monster.tsv`에 있던 기본 정보와 `MonsterRules.tsv`에 있던 특수
규칙을 하나의 몬스터 파일로 합쳤습니다.

주요 정보:

- 몬스터 ID
- 기획용 이름과 메모
- 액트, 등급, 난이도
- 체력과 힘
- AI 방식
- 사용하는 패턴 목록
- 피해 제한, 흡혈, 카운트다운 같은 고유 규칙

### `patterns/`

몬스터가 전투 중 사용하는 행동 패턴이 들어 있습니다. 패턴 하나당
JSON 파일 하나를 사용합니다.

기존 `Pattern.tsv`와 `PatternRules.tsv`의 내용을 하나로 합쳤습니다.

주요 정보:

- 공격 피해 자릿수
- 공격 횟수와 공격 횟수 자릿수
- 편집 가능 여부
- 전투당 최대 사용 횟수
- 패턴 선택 조건
- 잠금, 분리, 상태이상, 회복 등 실행 효과

### `fantasies/`

판타지 데이터가 들어 있습니다. 판타지 하나당 JSON 파일 하나를
사용합니다.

주요 정보:

- 판타지 ID
- 기획용 이름과 설명
- 등급
- 이미지
- 발동 시점
- 대상
- 실행 효과

### `schemas/`

JSON 작성 규칙을 검사하기 위한 스키마 파일입니다.

기획자가 직접 수정하는 콘텐츠 파일은 아니며, 잘못된 필드 이름이나
자료형, 누락된 필수값을 편집기와 변환 도구가 찾을 때 사용합니다.

### `manifest.json`

현재 JSON 자료의 개수와 참조 검사 결과를 기록합니다.

현재 변환된 데이터:

- 몬스터 39개
- 패턴 38개
- 판타지 60개

## 공통 작성 규칙

### ID는 변경하지 않기

`id`는 다른 데이터가 이 콘텐츠를 찾을 때 사용하는 고유 식별자입니다.
세이브 데이터에서도 사용할 수 있으므로 한 번 사용한 ID는 특별한
마이그레이션 계획 없이 변경하지 않습니다.

```json
"id": "Mob_30202_Knight"
```

ID는 콘텐츠를 구분할 때만 사용합니다. 게임 동작은 ID가 아니라
`operation`과 해당 설정값으로 결정합니다.

### 기획용 이름과 메모

`designerName`은 기획자가 데이터를 검색하고 구분하기 위한 이름입니다.
게임 화면에 그대로 표시되는 이름은 아닙니다.

`designerNote`에는 동작 설명, 주의사항, 밸런스 의도 등을 자유롭게
작성할 수 있습니다.

```json
"designerName": "기사",
"designerNote": "누적 피해가 400에 도달하기 전까지 한 번에 받는 피해를 20으로 제한한다."
```

JSON은 일반 주석을 지원하지 않으므로 설명이 필요할 때는
`designerNote`를 사용합니다.

### 목록은 배열로 작성하기

여러 ID나 값을 쉼표로 이어 붙인 문자열로 작성하지 않습니다.

잘못된 예:

```json
"patterns": "2_Single, KnightSkill, Str_1"
```

올바른 예:

```json
"patterns": [
  "2_Single",
  "KnightSkill",
  "Str_1"
]
```

### 효과는 operation으로 결정하기

효과의 실제 동작은 `operation`에 작성합니다.

```json
{
  "trigger": {
    "event": "immediate"
  },
  "target": {
    "actor": "self"
  },
  "operation": "add_status",
  "type": "strength",
  "amount": 1
}
```

위 효과는 즉시 자신에게 힘 1을 추가한다는 뜻입니다.

콘텐츠 ID나 표시 이름에 따라 동작이 바뀌도록 작성하지 않습니다.

일반적인 전투 이벤트 없이 수식 값을 계산할 때 적용되는 modifier는
다음 발동 시점을 사용합니다.

```json
"trigger": {
  "event": "value_evaluation"
}
```

### 고정값과 계산값

단순한 고정값은 숫자로 작성합니다.

```json
"amount": 3
```

현재 피해량이나 체력 등을 이용하는 계산값은 `expression` 객체로
작성되어 있습니다.

```json
"amount": {
  "expression": "DamageDealt*0.5"
}
```

문자열 수식은 기존 자료를 빠짐없이 이전하기 위해 임시로 보존한
형식입니다. 이후 기획 도구와 런타임을 만들면서 구조화된 계산식으로
교체할 예정입니다.

### 확률

확률은 백분율로 작성합니다.

```json
"chance": {
  "percent": 50
}
```

`50`은 50%를 의미합니다. `0.5`와 `50`을 혼용하지 않습니다.

### 사용하지 않는 콘텐츠

데이터를 삭제하지 않고 잠시 사용하지 않으려면 `enabled`를
`false`로 설정합니다.

```json
"enabled": false
```

### 화면 표시 문구

`localization`은 향후 문자열 테이블과 연결하기 위한 영역입니다.

```json
"localization": {
  "name": "monster.knight.name",
  "description": "monster.knight.description"
}
```

`designerName`을 플레이어에게 표시되는 최종 이름으로 사용하지
않습니다.

## 패턴 공격 작성 예시

2자리 피해로 한 번 공격하는 패턴:

```json
"attack": {
  "damage": {
    "digits": 2,
    "editable": true
  },
  "hits": {
    "fixed": 1
  }
}
```

2자리 피해와 편집 가능한 1자리 공격 횟수를 사용하는 패턴:

```json
"attack": {
  "damage": {
    "digits": 2,
    "editable": true
  },
  "hits": {
    "digits": 1,
    "editable": true,
    "minimum": 0
  }
}
```

공격하지 않는 패턴은 다음과 같이 작성합니다.

```json
"attack": null
```

## 조건 작성 예시

몬스터가 전투 중 받은 누적 피해가 400 이상인지 검사하는 조건:

```json
"condition": {
  "comparison": {
    "left": {
      "variable": "monster_damage_taken_this_battle"
    },
    "operator": ">=",
    "right": 400
  }
}
```

조건에 사용할 수 있는 변수와 연산자는 이후 전용 기획 도구에서
목록으로 제공할 예정입니다. 현재 지원 여부가 불분명한 새 변수나
연산자를 임의로 추가하면 안 됩니다.

## 현재 적용 상태와 주의사항

최초 JSON은 `Tools/Convert-GameplayTsvToJson.ps1`을 사용해 기존 TSV에서
일괄 변환했습니다. 변환이 끝난 현재는 이 JSON이 새로운 원본입니다.

다음 내용은 이미 반영되어 있습니다.

- 기존 몬스터, 패턴, 판타지 ID 유지
- 몬스터 기본 정보와 특수 규칙 병합
- 패턴 기본 정보와 추가 규칙 병합
- 쉼표로 작성된 패턴 목록을 JSON 배열로 변환
- 기존 효과를 공통 `trigger`, `target`, `operation` 구조로 변환
- 기존 동적 수식을 `expression` 객체로 보존

현재 적용된 기능:

1. JSON 문법과 필수 ID 검사
2. 중복 ID와 누락된 패턴 참조 검사
3. JSON에서 런타임 ScriptableObject 데이터베이스 생성
4. JSON 파일 변경 시 자동 재생성
5. 오류가 있으면 기존 정상 데이터베이스 보존
6. `GoldfishWalking > Data > Import All Gameplay JSON` 수동 가져오기 메뉴

가져오기 결과는 다음 파일에서 확인할 수 있습니다.

```text
Assets/Data/Generated/GameplayJsonImportReport.json
```

JSON에 오류가 있으면 보고서의 `errors`에 원인이 기록되며, 오류가 모두
해결되기 전에는 변경 내용이 런타임 데이터베이스에 적용되지 않습니다.

모든 몬스터 패턴과 판타지 효과의 플레이 모드 회귀 테스트는 계속
진행해야 합니다.

## 이전용 변환 도구 주의사항

아래 명령은 최초 마이그레이션 때 사용한 일회성 도구입니다.

```powershell
& 'Tools/Convert-GameplayTsvToJson.ps1'
```

이 명령은 `monsters`, `patterns`, `fantasies`, `schemas` 안의 기존 JSON
파일을 다시 생성합니다.

현재는 JSON이 원본이므로 이 명령을 실행하면 안 됩니다. JSON에서 수정한
내용이 과거 TSV 자료로 덮어써질 수 있습니다.
