using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

public class MatchSetting : MonoBehaviour
{
    public int[,] DigitRule =
    {
        { 1, 1, 1, 0, 1, 1, 1 },
        { 0, 0, 1, 0, 0, 1, 0 },
        { 1, 0, 1, 1, 1, 0, 1 },
        { 1, 0, 1, 1, 0, 1, 1 },
        { 0, 1, 1, 1, 0, 1, 1 },
        { 1, 1, 0, 1, 0, 1, 1 },
        { 1, 1, 0, 1, 1, 1, 1 },
        { 1, 1, 1, 0, 0, 1, 0 },
        { 1, 1, 1, 1, 1, 1, 1 },
        { 1, 1, 1, 1, 0, 1, 1 }
    };

    public Match[] Matches;

    void Start()
    {
        
    }

    // Update is called once per frame
    void Update()
    {
        
    }

    public void Setting(int num)
    {
        for (int i = 0; i < 7; i++)
        {
            Matches[i].Setting(DigitRule[num, i]);
        }
    }

    public int GetNumber()
    {
        for (int i = 0; i < 10; i ++)
        {
            bool match = true;
            for (int j = 0; j < 7; j++)
            {
                if (DigitRule[i, j] != Matches[j].Filled)
                {
                    match = false;
                    break;
                }
            }
            if (match) return i;
        }

        return -1;
    }
}
