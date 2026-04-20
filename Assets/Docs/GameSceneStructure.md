# Game Scene Structure

씬 구성: **Title.unity** + **Game.unity** 두 개.

---

## Hierarchy

```
[GameFlowController]
  - GameFlowController.cs
  - 필드: playerData(SO), mapGenerator, mapRunManager
          mapPanel, battlePanel, restPanel, rewardPanel

[MapRunManager]
  - MapRunManager.cs

[AudioManager]
  - AudioManager.cs (DontDestroyOnLoad, Title→Game 오디오 연속)

[HUD] (Canvas, ScreenSpaceOverlay, sortingOrder=10)
  - PlayerHUD.cs
  - 필드: playerData(SO), healthText, moveCountText
  ├── HealthText  (TMP_Text)
  └── MoveCountText (TMP_Text)

[MapPanel]
  - MapWorldController.cs
  - 필드: cameraController, nodePrefab, linePrefab
          Battle/Rest/Boss 스프라이트
  └── (카메라, 노드·라인 렌더링 오브젝트)

[BattlePanel]  ← 시작 시 비활성
  - GameManager.cs
  - 필드: playerData(SO), EnemyHPBar
          PlayerEnter, PlayerMultEnter, EnemyEnter, ResetButton, NextTurnButton
          player(Animator), enemy(Animator)
          matchManagerContainer
  └── MatchManagerContainer
        ├── MatchPanel_Player   (MatchManager.cs)
        ├── MatchPanel_Mult     (MatchManager.cs)
        └── MatchPanel_Enemy    (MatchManager.cs)

[RestPanel]  ← 시작 시 비활성
  - RestManager.cs
  - 필드: playerData(SO), matchspace, manager(MatchManager)
  └── Matchspace
        └── MatchPanel_Rest   (MatchManager.cs)

[RewardPanel]  ← 시작 시 비활성
  - RewardManager.cs
  - 필드: playerData(SO), Left(Button), Right(Button)

[EventSystem]
  - EventSystem
  - StandaloneInputModule
```

---

## 씬 전환 흐름

```
Title.unity
  OnStart() → SceneManager.LoadScene("Game")

Game.unity
  GameFlowController.Start()
    → playerData.ResetForNewRun()
    → GenerateMap()
    → TransitionTo(GameState.Map)

Map 상태
  노드 클릭 → GameEvents.NodeSelected(id, type)
    → Battle 노드: TransitionTo(GameState.Battle)
    → Rest 노드:   TransitionTo(GameState.Rest)

Battle 상태
  전투 승리 → GameEvents.BattleWon()   → TransitionTo(GameState.Reward)
  전투 패배 → GameEvents.BattleLost()  → TransitionTo(GameState.GameOver)

Rest 상태
  완료 → GameEvents.RestCompleted()  → TransitionTo(GameState.Map)

Reward 상태
  선택 → GameEvents.RewardCompleted() → TransitionTo(GameState.Map)
```

---

## PlayerRunData (ScriptableObject)

위치: `Assets/PlayerRunData.asset`
생성: `Assets > Create > GoldfishWalking > PlayerRunData`

| 필드 | 기본값 | 설명 |
|------|--------|------|
| health | 80 | 현재 HP |
| maxHealth | 80 | 최대 HP |
| maxMoveCount | 2 | 턴당 성냥 이동 횟수 |
| isBuffed | false | 휴식 건너뜀 버프 |

---

## 아키텍처 요약

| 패턴 | 적용 위치 |
|------|----------|
| State Machine | GameFlowController — 씬 대신 패널 전환 |
| Event Bus | GameEvents — 패널 간 직접 참조 제거 |
| ScriptableObject | PlayerRunData — DontDestroyOnLoad 싱글톤 제거 |
| Command | (예정) 성냥 이동 Undo/Reset |
| Strategy | IReward — 보상 타입 확장 |
