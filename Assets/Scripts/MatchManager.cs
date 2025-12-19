using System.Collections.Generic;
using UnityEngine;

public class MatchManager : MonoBehaviour
{
    public static MatchManager Instance;

    private List<int> Digits = new List<int>();
    public List<GameObject> DigitManagers;
    public List<RectTransform> Rect = new List<RectTransform>();

    public int Length;

    private void Awake()
    {
        Instance = this;
        foreach(GameObject obj in DigitManagers)
        {
            RectTransform rectTransform = obj.GetComponent<RectTransform>();
            Rect.Add(rectTransform);
        }
    }

    public void Setting()
    {
        Digits.Clear();
        int num = GameManager.instance.ChangedNumber;
        while (num > 0)
        {
            Digits.Add(num % 10);
            num /= 10;
        }
        Length = Digits.Count;

        for (int i = 0; i < DigitManagers.Count; i++)
        {
            if (i < Length)
            {
                DigitManagers[i].SetActive(true);
                Rect[i].anchoredPosition = new Vector3(-(Length - 1) * 0.5f / 2 + 0.5f * i, 0, 0);
                DigitManagers[i].GetComponent<DigitManager>().Setting(Digits[i]);
            }
            else DigitManagers[i].SetActive(false);
        }
    }

    public int GetNumber()
    {
        int result = 0;
        for (int i = 0; i < Length; i++)
        {
            result *= 10;
            result += DigitManagers[i].GetComponent<DigitManager>().GetNumber();
            if (DigitManagers[i].GetComponent<DigitManager>().GetNumber() < 0) return -1;
        }
        return result;
    }
}
