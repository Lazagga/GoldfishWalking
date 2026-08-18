# 게임 이미지 작업 안내

이 폴더의 PNG가 게임에서 사용하는 이미지 원본입니다. 이미지를 `Resources` 폴더에 복사할 필요가 없으며, 런타임 코드도 파일 경로로 이미지를 불러오지 않습니다.

## 폴더

- `enemy/`: 몬스터 스프라이트 시트
- `player/`: 플레이어 대기·공격 프레임
- `shop/`: 상점 인물 이미지
- `ui/`: UI 아틀라스와 장식 이미지
- `Generated/`: Unity가 자동 생성한 AnimationClip과 AnimatorController. 직접 편집하지 않습니다.

## 몬스터 이미지 적용 순서

1. `enemy/`에 PNG를 넣습니다.
2. 몬스터 JSON의 `presentation.sprite`에 PNG 파일 이름을 적습니다. 확장자는 생략해도 됩니다.
3. `idleFrames`에는 대기 애니메이션에 사용할 첫 프레임 수를, `framesPerSecond`에는 재생 속도를 적습니다.
4. Unity 메뉴에서 `GoldfishWalking > Data > Import All Gameplay JSON`을 실행합니다.

가져오기를 실행하면 Unity가 시트를 격자로 자르고, 대기 AnimationClip과 AnimatorController를 생성한 뒤 `MonsterDatabase`에 Sprite와 Controller를 직접 연결합니다.

셀 크기는 몬스터 등급에 따라 자동 결정됩니다.

- 일반: 32×32 px
- 엘리트: 48×48 px
- 보스: 64×64 px

프레임은 왼쪽 위에서 시작해 오른쪽으로 읽고, 다음 줄로 내려갑니다. 이미지 가로·세로 크기는 해당 셀 크기로 정확히 나누어져야 합니다.

## 주의사항

- `Generated/` 파일은 JSON 가져오기 때 갱신되므로 직접 수정하지 않습니다.
- 픽셀 이미지는 Point 필터, 밉맵 없음, 압축 없음으로 자동 설정됩니다.
- 플레이어 대기 이미지는 `mainchar_idle_0000.png`부터 순서대로 읽어 UI용 대기 애니메이션을 자동 생성합니다.
- `ui/20260707_ui.png`는 다음 순서의 8개 UI로 자동 분할됩니다: 다음, 초기화, 닫기, 텍스트 패널, 단일 버튼, 연결형 왼쪽, 연결형 가운데, 연결형 오른쪽.
- UI 아틀라스를 수정한 뒤에는 `GoldfishWalking > Art > Rebuild UI Atlas`를 실행합니다. 메인 씬까지 다시 입히려면 이어서 `Apply Direct Art References To Main Scene`을 실행합니다.
