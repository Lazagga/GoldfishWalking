using System.Collections.Generic;
using UnityEngine;

public class DigitManager : MonoBehaviour
{
    public static DigitManager instance;

    public Match[] Matches;

    private int[,] DigitRule = {{ 1, 1, 1, 0, 1, 1, 1 },
                                { 0, 0, 1, 0, 0, 1, 0 },
                                { 1, 0, 1, 1, 1, 0, 1 },
                                { 1, 0, 1, 1, 0, 1, 1 },
                                { 0, 1, 1, 1, 0, 1, 0 },
                                { 1, 1, 0, 1, 0, 1, 1 },
                                { 1, 1, 0, 1, 1, 1, 1 },
                                { 1, 1, 1, 0, 0, 1, 0 },
                                { 1, 1, 1, 1, 1, 1, 1 },
                                { 1, 1, 1, 1, 0, 1, 1 }};

    private void Awake()
    {
        instance = this;
    }

    public void Setting(int num)
    {
        for (int i = 0; i < 7; i++)
        {
            Matches[i].Setting(DigitRule[num,i]);
        }
    }

    public int GetNumber()
    {
        bool check;
        for (int i = 0; i < 10; i ++)
        {
            check = true;
            for(int j = 0; j < 8; j ++)
            {
                if (Matches[j].Filled != DigitRule[i,j]) check = false;
            }
            if (check) return i;
        }
        return -1;
    }
}
