using UnityEngine;
using TMPro;
using UnityEngine.UI;
using System.Collections;
using System.Collections.Generic;

public class GameManager : MonoBehaviour
{
    public static GameManager instance = null;
    public bool Match;
    public GameObject MatchCursor;

    public GameObject matchPanel;

    public Sprite MatchImage;
    public Sprite EmptyImage;

    public int MoveCount;
    public int MaxMoveCount;
    public TMP_Text MoveCountTxt;

    public int BeginNumber;
    public int ChangedNumber;

    public GameObject BeforeZoom;
    public GameObject AfterZoom;

    public Button PlayerEnter, ResetButton, NextTurnButton;
    public Vector3 dest;

    public List<int> matchSlotsState = new List<int>();

    public float AnimTime;

    private void Awake()
    {
        instance = this;
        Match = false;
    }

    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        PlayerEnter.GetComponent<Button>().onClick.AddListener(OpenMatchPanel);
        NextTurnButton.onClick.AddListener(OnReset);
        ResetButton.onClick.AddListener(OnReset);

        for(int i = 0; i < 14; i++)
        {
            matchSlotsState.Add(0);
        }
    }


    // Update is called once per frame
    void Update()
    {
        if (Input.GetMouseButtonDown(1) && Match)
        {
            Match = false;
        }
        MoveCountTxt.text = MoveCount + " / " + MaxMoveCount;
    }
    public void OpenMatchPanel()
    {
        matchPanel.SetActive(true);
        NextTurnButton.gameObject.SetActive(false);
    }

    public void CloseMatchPanel()
    {
        if(matchPanel.GetComponent<MatchManager>().GetNumber() < 0) return;
        matchPanel.SetActive(false);
    }

    public void OnReset()
    {
        MoveCount = MaxMoveCount;
        ChangedNumber = BeginNumber;
        matchPanel.GetComponent<MatchManager>().SetNumber(BeginNumber);
    }
}
