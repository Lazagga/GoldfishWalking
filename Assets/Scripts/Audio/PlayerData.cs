using UnityEngine;

public class PlayerData : MonoBehaviour
{
    public static PlayerData Instance;

    public int Health;
    public int MaxMoveCount;

    public GameObject ItemSlot;

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
    }

    public void ChangeHealth(int val)
    {
        Health += val;
    }

    public void ChangeCount()
    {
        MaxMoveCount += 1;
    }
}
