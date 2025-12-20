using System.Collections.Generic;
using UnityEngine;

public class DigitsManager : MonoBehaviour
{
    public MatchSetting[] Digits;
    public List<int> numDigit = new List<int>();

    public int GapBetweenDigits = 50;

    public void SetDigits(int num)
    {
        while (num > 0)
        {
            numDigit.Add(num % 10);
            num /= 10;
        }
        numDigit.Reverse();

        for (int i = 0; i < Digits.Length; i++)
        {
            if (i < numDigit.Count)
            {
                Digits[i].gameObject.SetActive(true);
                RectTransform rt = Digits[i].GetComponent<RectTransform>();
                rt.anchoredPosition = new Vector2(GapBetweenDigits * (i - (numDigit.Count - 1) / 2.0f), 0);
                Digits[i].Setting(numDigit[i]);
            }
            else
            {
                Digits[i].gameObject.SetActive(false);
            }
        }
    }

    public int GetNumber()
    {
        int result = 0;
        for (int i = 0; i < numDigit.Count; i++)
        {
            int digit = Digits[i].GetNumber();
            if (digit == -1) return -1;
            result = result * 10 + digit;
        }
        return result;
    }
}
