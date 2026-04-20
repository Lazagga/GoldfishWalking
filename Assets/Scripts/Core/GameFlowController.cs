using UnityEngine;

public enum GameState { Map, Battle, Rest, Reward, GameOver }

/// <summary>
/// 게임의 상태 전환을 담당하는 State Machine.
/// 씬 전환 없이 패널 ON/OFF로 화면을 전환한다.
/// </summary>
public class GameFlowController : MonoBehaviour
{
    public static GameFlowController Instance { get; private set; }

    [Header("Player Data")]
    public PlayerRunData playerData;

    [Header("Map")]
    public MapGenerator mapGenerator;
    public MapRunManager mapRunManager;

    [Header("Panels")]
    public GameObject mapPanel;
    public GameObject battlePanel;
    public GameObject restPanel;
    public GameObject rewardPanel;

    public GameState CurrentState { get; private set; }

    private void Awake()
    {
        Instance = this;

        // 모든 패널을 비활성화한 뒤 Start에서 Map으로 진입
        mapPanel.SetActive(false);
        battlePanel.SetActive(false);
        restPanel.SetActive(false);
        rewardPanel.SetActive(false);
    }

    private void OnEnable()
    {
        GameEvents.OnNodeSelected  += HandleNodeSelected;
        GameEvents.OnBattleWon     += OnBattleWon;
        GameEvents.OnBattleLost    += OnBattleLost;
        GameEvents.OnRestCompleted += OnRestCompleted;
        GameEvents.OnRewardCompleted += OnRewardCompleted;
    }

    private void OnDisable()
    {
        GameEvents.OnNodeSelected  -= HandleNodeSelected;
        GameEvents.OnBattleWon     -= OnBattleWon;
        GameEvents.OnBattleLost    -= OnBattleLost;
        GameEvents.OnRestCompleted -= OnRestCompleted;
        GameEvents.OnRewardCompleted -= OnRewardCompleted;
    }

    private void Start()
    {
        playerData.ResetForNewRun();
        GenerateMap();
        TransitionTo(GameState.Map);
    }

    private void GenerateMap()
    {
        var map = mapGenerator.Generate();
        mapRunManager.map = map;
        mapRunManager.currentNodeId = map.startId;
    }

    public void TransitionTo(GameState next)
    {
        ExitState(CurrentState);
        CurrentState = next;
        EnterState(next);
    }

    private void EnterState(GameState state)
    {
        mapPanel.SetActive(state == GameState.Map);
        battlePanel.SetActive(state == GameState.Battle);
        restPanel.SetActive(state == GameState.Rest);
        rewardPanel.SetActive(state == GameState.Reward);

        if (state == GameState.GameOver)
            Application.Quit();
    }

    private void ExitState(GameState state) { }

    // --- 이벤트 핸들러 ---

    private void HandleNodeSelected(int nodeId, NodeType type)
    {
        mapRunManager.currentNodeId = nodeId;

        switch (type)
        {
            case NodeType.Battle:
            case NodeType.Battle2:
            case NodeType.End:
                TransitionTo(GameState.Battle);
                break;
            case NodeType.Rest:
                TransitionTo(GameState.Rest);
                break;
        }
    }

    private void OnBattleWon()     => TransitionTo(GameState.Reward);
    private void OnBattleLost()    => TransitionTo(GameState.GameOver);
    private void OnRestCompleted() => TransitionTo(GameState.Map);
    private void OnRewardCompleted() => TransitionTo(GameState.Map);
}
