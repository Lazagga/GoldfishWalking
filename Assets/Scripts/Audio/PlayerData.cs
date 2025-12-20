using TMPro;
using UnityEngine;

public class PlayerData : MonoBehaviour
{
    public static PlayerData Instance;

    public int Health = 80;
    public int MaxMoveCount = 2;
    public int MoveCount = 2;

    public TMP_Text HealthText;
    public TMP_Text MoveCountText;

    public bool isBuffed = false;

    private void Awake()
    {
        if (Instance == null)
        {
            Instance = this;
            DontDestroyOnLoad(gameObject);
        }
        else
        {
            Destroy(gameObject);
        }
        HealthText.text = "HP = " + Health.ToString();
        MoveCountText.text = MoveCount.ToString() + " / " + MaxMoveCount.ToString();
    }

    public void ChangeHealth(int val)
    {
        Health += val;
        HealthText.text = "HP = " + Health.ToString();

    }

    public void AddMaxCount()
    {
        MaxMoveCount += 1;
        MoveCount += 1;
        MoveCountText.text = MoveCount.ToString() + " / " + MaxMoveCount.ToString();
    }
}
