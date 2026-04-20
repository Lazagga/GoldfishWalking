using System.Collections;
using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Battle 패널 전담 컨트롤러.
/// 씬 전환 대신 GameEvents를 통해 GameFlowController에 결과를 알린다.
/// </summary>
public class GameManager : MonoBehaviour
{
    public static GameManager instance;

    [Header("Player Data")]
    public PlayerRunData playerData;

    [Header("Numbers")]
    public int PlayerNumber, PlayerNumberOriginal;
    public int PlayerMultNumber, PlayerMultNumberOriginal;
    public int EnemyNumber, EnemyNumberOriginal;

    [Header("Enemy")]
    public int maxEnemyHealth;
    private int enemyHealth;

    [Header("UI")]
    public TextMeshProUGUI EnemyHPBar; // 플레이어 HP는 PlayerHUD가 담당
    public Button PlayerEnter, PlayerMultEnter, EnemyEnter, ResetButton, NextTurnButton;

    [Header("Animators")]
    public Animator player, enemy;

    [Header("Match Panels")]
    public Transform matchManagerContainer;
    private List<MatchManager> matchManagers = new();

    private enum PanelTarget { Player, Multiplier, Enemy }
    private PanelTarget currentTarget;

    private int moveCountRemaining;

    private void Awake()
    {
        instance = this;
        foreach (Transform child in matchManagerContainer)
            matchManagers.Add(child.GetComponent<MatchManager>());
    }

    private void OnEnable()
    {
        GameEvents.OnMatchMoved += RecalculateMoveCount;

        PlayerEnter.onClick.AddListener(OpenMatchPanelPlayer);
        PlayerMultEnter.onClick.AddListener(OpenMatchPanelPlayerMult);
        EnemyEnter.onClick.AddListener(OpenMatchPanelEnemy);
        ResetButton.onClick.AddListener(OnReset);
        NextTurnButton.onClick.AddListener(OnEndTurn);

        InitTurn();
    }

    private void OnDisable()
    {
        GameEvents.OnMatchMoved -= RecalculateMoveCount;

        PlayerEnter.onClick.RemoveListener(OpenMatchPanelPlayer);
        PlayerMultEnter.onClick.RemoveListener(OpenMatchPanelPlayerMult);
        EnemyEnter.onClick.RemoveListener(OpenMatchPanelEnemy);
        ResetButton.onClick.RemoveListener(OnReset);
        NextTurnButton.onClick.RemoveListener(OnEndTurn);
    }

    private void InitTurn()
    {
        moveCountRemaining = playerData.maxMoveCount;

        PlayerNumberOriginal = Random.Range(10, 100);
        PlayerNumber = PlayerNumberOriginal;

        PlayerMultNumberOriginal = Random.Range(0, 10);
        PlayerMultNumber = PlayerMultNumberOriginal;

        EnemyNumberOriginal = Random.Range(10, 100);
        EnemyNumber = EnemyNumberOriginal;

        enemyHealth = maxEnemyHealth;

        foreach (var mm in matchManagers) mm.Reset();

        RefreshUI();
        GameEvents.MoveCountChanged(moveCountRemaining);
    }

    private void RefreshUI()
    {
        EnemyHPBar.text = enemyHealth.ToString();
    }

    // --- 이동 횟수 ---

    private void RecalculateMoveCount()
    {
        int used = 0;
        foreach (var mm in matchManagers) used += mm.usedMoveInThisPanel;
        moveCountRemaining = playerData.maxMoveCount - used;
        GameEvents.MoveCountChanged(moveCountRemaining);
    }

    // --- 패널 열기 ---

    public void OpenMatchPanelPlayer()     => OpenPanel(PanelTarget.Player);
    public void OpenMatchPanelPlayerMult() => OpenPanel(PanelTarget.Multiplier);
    public void OpenMatchPanelEnemy()      => OpenPanel(PanelTarget.Enemy);

    private void OpenPanel(PanelTarget target)
    {
        currentTarget = target;
        int idx = (int)target;
        int initNum = target switch
        {
            PanelTarget.Player     => PlayerNumber,
            PanelTarget.Multiplier => PlayerMultNumber,
            PanelTarget.Enemy      => EnemyNumber,
            _                      => 0
        };

        matchManagers[idx].gameObject.SetActive(true);
        matchManagers[idx].Init(initNum);
        NextTurnButton.gameObject.SetActive(false);
    }

    public void CloseMatchPanel()
    {
        int idx = (int)currentTarget;
        int res = matchManagers[idx].GetNumber();
        if (res < 0) return;

        switch (currentTarget)
        {
            case PanelTarget.Player:     PlayerNumber     = res; break;
            case PanelTarget.Multiplier: PlayerMultNumber = res; break;
            case PanelTarget.Enemy:      EnemyNumber      = res; break;
        }

        matchManagers[idx].gameObject.SetActive(false);
        NextTurnButton.gameObject.SetActive(true);
    }

    public void OnReset()
    {
        PlayerNumber     = PlayerNumberOriginal;
        PlayerMultNumber = PlayerMultNumberOriginal;
        EnemyNumber      = EnemyNumberOriginal;

        foreach (var mm in matchManagers) mm.Reset();

        moveCountRemaining = playerData.maxMoveCount;
        GameEvents.MoveCountChanged(moveCountRemaining);
    }

    public void OnEndTurn() => StartCoroutine(Fight());

    private IEnumerator Fight()
    {
        player.SetTrigger("Attack");
        yield return new WaitForSeconds(0.5f);

        enemyHealth -= PlayerNumber;
        EnemyHPBar.text = enemyHealth.ToString();

        if (enemyHealth <= 0)
        {
            GameEvents.BattleWon();
            yield break;
        }

        yield return new WaitForSeconds(1f);

        enemy.SetTrigger("Attack");
        yield return new WaitForSeconds(0.5f);

        playerData.ChangeHealth(-EnemyNumber); // PlayerHUD가 이벤트로 자동 갱신

        if (playerData.health <= 0)
        {
            GameEvents.BattleLost();
            yield break;
        }

        // 다음 턴
        InitTurn();
    }
}
