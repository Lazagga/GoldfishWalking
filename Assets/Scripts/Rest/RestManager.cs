using Unity.VisualScripting;
using UnityEngine;
using UnityEngine.SceneManagement;

public class RestManager : MonoBehaviour
{
    public bool didRest = false;
    public GameObject Matchspace;
    public MatchManager manager;

    int value = 0;

    public void OnClick()
    {
        Matchspace.SetActive(true);
        manager.Init(PlayerData.Instance.Health);
    }

    public void OnClose()
    {
        value = manager.GetNumber();
        if (value < 0)
        {
            return;
        }
        Matchspace.SetActive(false);
    }

    public void OnRest()
    {
        if (Matchspace.activeSelf) return;
        didRest = true;
        PlayerData.Instance.ChangeHealth(value);
    }

    public void OnDone()
    {
        //fade
        if (!didRest) PlayerData.Instance.isBuffed = true;
        SceneManager.LoadScene("Map");
    }
}
