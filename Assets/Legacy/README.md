# Legacy 보관 영역

이 폴더는 현재 빌드에서 사용하지 않는 이전 씬을 한 차례 회귀 검증 기간 동안만
보관합니다.

- 현재 메인 씬: `Assets/Scenes/GumBwing_Er.unity`
- `Scenes/Game.unity`: 이전 통합 씬
- `Scenes/BattleUILayout.unity`: 이전 전투 UI 배치 실험 씬

새 코드나 데이터는 이 폴더를 참조하면 안 됩니다. 메인 씬의 기능 검증이 끝난 뒤
이전 씬에만 남은 필수 오브젝트가 없음을 확인하고 Git 기록에 의존해 삭제합니다.
