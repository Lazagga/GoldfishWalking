using UnityEngine;
using TMPro;
using UnityEngine.UI;
using System.Collections;
using System.Collections.Generic;

public class GameManager : MonoBehaviour
{
    public static GameManager instance = null;

    public int MoveCount;
    public int MaxMoveCount;
    public TMP_Text MoveCountTxt;

    public int BeginNumber;
    public int ChangedNumber;

    public int EnemyNumber;

    public Button PlayerEnter, EnemyEnter, ResetButton, NextTurnButton;

    public Transform matchManagerContainer;
    private List<MatchManager> matchManagers = new List<MatchManager>();
    private int openMatchManagerIdx = 0;

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
        EnemyEnter.onClick.AddListener(OpenMatchPanelEnemy);
        NextTurnButton.onClick.AddListener(OnReset);
        ResetButton.onClick.AddListener(OnReset);
    }

    // Update is called once per frame
    void Update()
    {
        MoveCountTxt.text = MoveCount + " / " + MaxMoveCount;
    }
    public void OpenMatchPanelPlayer()
    {
        MatchManager matchManager = matchManagers[0];
        
        matchManager.gameObject.SetActive(true);
        openMatchManagerIdx = 0;
        matchManager.Init(ChangedNumber);
        NextTurnButton.gameObject.SetActive(false);
    }

    public void OpenMatchPanelEnemy()
    {
        MatchManager matchManager = matchManagers[1];
        
        matchManager.gameObject.SetActive(true);
        openMatchManagerIdx = 1;
        matchManager.Init(EnemyNumber);
        NextTurnButton.gameObject.SetActive(false);
    }

    public void CloseMatchPanel()
    {
        MatchManager matchManager = matchManagers[openMatchManagerIdx];

        if(matchManager.GetNumber() < 0) return;

        int res = matchManagers[openMatchManagerIdx].GetNumber();

        if(openMatchManagerIdx == 0)
        {
            ChangedNumber = res;
        }
        else
        {
            EnemyNumber = res;
        }

        matchManager.gameObject.SetActive(false);
        NextTurnButton.gameObject.SetActive(true);
    }

    public void OnReset()
    {
        MoveCount = MaxMoveCount;
        ChangedNumber = BeginNumber;
        
        matchManagers[openMatchManagerIdx].SetNumber(BeginNumber);
    }
}
