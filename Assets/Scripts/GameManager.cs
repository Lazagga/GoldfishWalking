using UnityEngine;
using TMPro;
using UnityEngine.UI;
using System.Collections;

public class GameManager : MonoBehaviour
{
    public static GameManager instance = null;
    public bool Match;
    public GameObject MatchCursor;

    public Sprite MatchImage;
    public Sprite EmptyImage;

    public int MoveCount;
    public int MaxMoveCount;
    public TMP_Text MoveCountTxt;

    public int BeginNumber;
    public int ChangedNumber;

    public GameObject BeforeZoom;
    public GameObject AfterZoom;

    public Button PlayerEnter, EnemyEnter;
    public Vector3 dest;

    public float AnimTime;

    private void Awake()
    {
        instance = this;
        Match = false;
    }

    // Start is called once before the first execution of Update after the MonoBehaviour is created
    void Start()
    {
        PlayerEnter.GetComponent<Button>().onClick.AddListener(CamActionPlayer);
        EnemyEnter.GetComponent<Button>().onClick.AddListener(CamActionEnemy);
    }

    // Update is called once per frame
    void Update()
    {
        /*
        if (Match)
        {
            MatchCursor.SetActive(true);
            MatchCursor.transform.position = Camera.main.ScreenToWorldPoint(Input.mousePosition);
        }
        else MatchCursor.SetActive(false);
        */

        if (Input.GetMouseButtonDown(1) && Match)
        {
            Match = false;
        }
        MoveCountTxt.text = MoveCount + " / " + MaxMoveCount;
    }

    public void CamActionPlayer()
    {
        dest = new Vector3(-4, 0, -10);
        // MatchManager.Instance.Setting();
        StartCoroutine("ZoomIn");
    }

    public void CamActionEnemy()
    {
        dest = new Vector3(4, 0, -10);
        StartCoroutine("ZoomIn");
    }

    public IEnumerator ZoomIn()
    {
        float time = 0;
        while (time < AnimTime)
        {
            time += Time.deltaTime;
            Camera.main.transform.position = Vector3.Lerp(new Vector3(0, 0, -10), dest, time / AnimTime);
            Camera.main.orthographicSize = Mathf.Lerp(5, 0.66f, time / AnimTime);
            if(time / AnimTime > 0.5f)
            {
                BeforeZoom.SetActive(false);
                AfterZoom.SetActive(true);
            }
            yield return null;
        }
        Camera.main.transform.position = dest;
        Camera.main.orthographicSize = 0.66f;
    }

    public IEnumerator ZoomOut()
    {
        float time = 0;
        while (time < AnimTime)
        {
            time += Time.deltaTime;
            Camera.main.transform.position = Vector3.Lerp(dest, new Vector3(0, 0, -10), time / AnimTime);
            Camera.main.orthographicSize = Mathf.Lerp(0.66f, 5, time / AnimTime);
            if (time / AnimTime > 0.5f)
            {
                BeforeZoom.SetActive(true);
                AfterZoom.SetActive(false);
            }
            yield return null;
        }
        Camera.main.transform.position = new Vector3(0, 0, -10);
        Camera.main.orthographicSize = 5;
    }

    public void OnExit()
    {
        int result = MatchManager.Instance.GetNumber();
        if (result < 0) return;//Match Positioning Error
        ChangedNumber = result;
        StartCoroutine("ZoomOut");
    }

    public void OnReset()
    {
        MoveCount = MaxMoveCount;
        ChangedNumber = BeginNumber;
        // MatchManager.Instance.Setting();
    }
}
