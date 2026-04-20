using UnityEngine;

/// <summary>
/// Rest 패널 전담 컨트롤러.
/// 완료 시 SceneManager 대신 GameEvents.RestCompleted를 발행한다.
/// </summary>
public class RestManager : MonoBehaviour
{
    [Header("Player Data")]
    public PlayerRunData playerData;

    [Header("UI")]
    public GameObject matchspace;
    public MatchManager manager;

    private bool didRest = false;
    private int healValue = 0;

    private void OnEnable()
    {
        didRest = false;
        healValue = 0;
    }

    public void OnClick()
    {
        matchspace.SetActive(true);
        manager.Init(playerData.health);
    }

    public void OnClose()
    {
        int value = manager.GetNumber();
        if (value < 0) return;

        healValue = value;
        matchspace.SetActive(false);
    }

    public void OnRest()
    {
        if (matchspace.activeSelf) return;
        didRest = true;
        playerData.ChangeHealth(healValue);
    }

    public void OnDone()
    {
        if (!didRest) playerData.isBuffed = true;
        GameEvents.RestCompleted();
    }
}
