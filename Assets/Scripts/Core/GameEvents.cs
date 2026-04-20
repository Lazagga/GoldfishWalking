using System;

/// <summary>
/// 씬 전환 없이 패널 간 통신을 위한 정적 이벤트 버스.
/// 발행자는 Invoke 메서드만 호출. 구독자는 OnEnable/OnDisable에서 등록/해제.
/// </summary>
public static class GameEvents
{
    // 맵 탐색
    public static event Action<int, NodeType> OnNodeSelected;

    // 전투
    public static event Action OnBattleWon;
    public static event Action OnBattleLost;

    // 휴식
    public static event Action OnRestCompleted;

    // 보상
    public static event Action OnRewardCompleted;

    // 성냥 이동 (Matchstick → BattleController/RestController)
    public static event Action OnMatchMoved;

    // 남은 이동 횟수 변경 (BattleController → Matchstick, HUD)
    public static event Action<int> OnMoveCountChanged;

    // --- 발행 ---

    public static void NodeSelected(int id, NodeType type) => OnNodeSelected?.Invoke(id, type);
    public static void BattleWon()                         => OnBattleWon?.Invoke();
    public static void BattleLost()                        => OnBattleLost?.Invoke();
    public static void RestCompleted()                     => OnRestCompleted?.Invoke();
    public static void RewardCompleted()                   => OnRewardCompleted?.Invoke();
    public static void MatchMoved()                        => OnMatchMoved?.Invoke();
    public static void MoveCountChanged(int remaining)     => OnMoveCountChanged?.Invoke(remaining);
}
