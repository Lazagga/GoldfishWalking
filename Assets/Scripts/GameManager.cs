using UnityEngine;
using TMPro;
using UnityEngine.UI;
using System.Collections.Generic;
using UnityEngine.SceneManagement;
//using System;


public class GameManager : MonoBehaviour
{
    public static GameManager instance = null;

    public int MoveCount;
    public int MaxMoveCount;
    public TMP_Text MoveCountTxt;

    public int PlayerNumber, PlayerNumberOriginal;

    public int PlayerMultNumber, PlayerMultNumberOriginal;

    public int EnemyNumber, EnemyNumberOriginal;

    public Button PlayerEnter, PlayerMultEnter, EnemyEnter, ResetButton, NextTurnButton;

    public Transform matchManagerContainer;
    private List<MatchManager> matchManagers = new List<MatchManager>();
    private int openMatchManagerIdx = 0;

    public int maxEnemyHealth;
    public int enemyHealth;

    public TextMeshProUGUI PlayerHPBar, EnemyHPBar;

    private void Awake()
    {
        instance = this;

        for(int i = 0; i < matchManagerContainer.childCount; i++)
        {
            matchManagers.Add(matchManagerContainer.GetChild(i).GetComponent<MatchManager>());
        }
    }

    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        PlayerEnter.onClick.AddListener(OpenMatchPanelPlayer);
        PlayerMultEnter.onClick.AddListener(OpenMatchPanelPlayerMult);
        EnemyEnter.onClick.AddListener(OpenMatchPanelEnemy);
        ResetButton.onClick.AddListener(OnReset);
        NextTurnButton.onClick.AddListener(OnEndTurn);

        enemyHealth = maxEnemyHealth;
        PlayerHPBar.text = PlayerData.Instance.Health.ToString();
        EnemyHPBar.text = enemyHealth.ToString();
    }

    // Update is called once per frame
    void Update()
    {
        PlayerData.Instance.MoveCountText.text = MoveCount + " / " + MaxMoveCount;
    }

    public void UpdateMoveCount()
    {
        int sumUsedMove = 0;
        foreach(MatchManager matchManager in matchManagers)
        {
            sumUsedMove += matchManager.usedMoveInThisPanel;
        }
        MoveCount = MaxMoveCount - sumUsedMove;
    }

    public void OpenMatchPanelPlayer()
    {
        MatchManager matchManager = matchManagers[0];
        
        matchManager.gameObject.SetActive(true);
        openMatchManagerIdx = 0;
        matchManager.Init(PlayerNumber);
        NextTurnButton.gameObject.SetActive(false);
    }

    public void OpenMatchPanelPlayerMult()
    {
        MatchManager matchManager = matchManagers[1];
        
        matchManager.gameObject.SetActive(true);
        openMatchManagerIdx = 1;
        matchManager.Init(PlayerMultNumber);
        NextTurnButton.gameObject.SetActive(false);
    }

    public void OpenMatchPanelEnemy()
    {
        MatchManager matchManager = matchManagers[2];
        
        matchManager.gameObject.SetActive(true);
        openMatchManagerIdx = 2;
        matchManager.Init(EnemyNumber);
        NextTurnButton.gameObject.SetActive(false);
    }

    public void CloseMatchPanel()
    {
        MatchManager matchManager = matchManagers[openMatchManagerIdx];

        if(matchManager.GetNumber() < 0) return;

        int res = matchManagers[openMatchManagerIdx].GetNumber();


        switch (openMatchManagerIdx)
        {
            case 0:
                PlayerNumber = res;
                break;
            case 1:
                PlayerMultNumber = res;
                break;
            case 2:
                EnemyNumber = res;
                break;
        }

        matchManager.gameObject.SetActive(false);
        NextTurnButton.gameObject.SetActive(true);
    }

    public void OnReset()
    {
        MoveCount = MaxMoveCount;

        PlayerNumber = PlayerNumberOriginal;

        PlayerMultNumber = PlayerMultNumberOriginal;

        EnemyNumber = EnemyNumberOriginal;

        matchManagers[openMatchManagerIdx].Init(PlayerMultNumber);
        
        foreach(MatchManager matchManager in matchManagers)
        {
            matchManager.Reset();
        }
    }

    public void OnEndTurn()
    {
        if (SceneManager.GetActiveScene().name == "Rest")
        {
            PlayerData.Instance.ChangeHealth(matchManagers[0].GetNumber());
            SceneManager.LoadScene("Map");
        }

        // Debug.Log(PlayerNumber * PlayerMultNumber);

        enemyHealth -= PlayerNumber;
        EnemyHPBar.text = enemyHealth.ToString();

        if(enemyHealth <= 0)
        {
            SceneManager.LoadScene("Map");
        }


        PlayerData.Instance.ChangeHealth(-EnemyNumber);
        PlayerHPBar.text = PlayerData.Instance.Health.ToString();


        if (PlayerData.Instance.Health <= 0)
        {
            PlayerData.Instance.ChangeHealth(-PlayerData.Instance.Health);
            SceneManager.LoadScene("Title");
        }

        PlayerNumberOriginal = Random.Range(10, 100);
        PlayerNumber = PlayerNumberOriginal;

        PlayerMultNumberOriginal = Random.Range(0, 10);
        PlayerMultNumber = PlayerMultNumberOriginal;

        EnemyNumberOriginal = Random.Range(10, 100);
        EnemyNumber = EnemyNumberOriginal;

        foreach(MatchManager matchManager in matchManagers)
        {
            matchManager.Reset();
        }
    }
}
